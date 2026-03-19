import frappe
from frappe.model.document import Document
import pdfplumber
import re
from datetime import datetime


class PDFtoPurchaseReceipt(Document):
	def before_insert(self):
		try:
			if not self.supplier_delivery_pdf:
				return

			extracted_receipts = self._get_extracted_data()
			if not extracted_receipts:
				return

			for rec in extracted_receipts:
				items = rec.get("items")
				if not items:
					continue

				# Match Supplier in DB
				supplier_name = rec.get("supplier", "")
				find_supplier = frappe.db.get_all(
					"Supplier",
					filters={"supplier_name": ["like", f"%{supplier_name}%"]},
					fields=["name"],
					limit=1
				)
				if not find_supplier:
					continue

				supplier_id = find_supplier[0].name
				do_no = rec.get("do_no")

				# Create Purchase Receipt for FOUND items only
				found_items = [itm for itm in items if frappe.db.exists("Item", itm.get("item_code"))]
				if not found_items:
					continue

				if do_no and frappe.db.exists("Purchase Receipt", do_no):
					pr = frappe.get_doc("Purchase Receipt", do_no)
				else:
					pr = frappe.new_doc("Purchase Receipt")
					if do_no:
						pr.name = do_no
					pr.supplier = supplier_id
					pr.posting_date = self.date or datetime.today().date()

				for itm in found_items:
					if itm.get("item_code") not in [i.item_code for i in pr.items]:
						pr.append("items", {
							"item_code": itm.get("item_code"),
							"qty": itm.get("qty"),
							"warehouse": "",
							"schedule_date": pr.posting_date
						})

				if pr.items:
					pr.insert(ignore_permissions=True)
					frappe.db.commit()

		except Exception:
			frappe.log_error(message=frappe.get_traceback(), title="PDF Purchase Receipt Processing Error")

	def _get_extracted_data(self):
		file_doc = frappe.get_all("File", filters={"file_url": self.supplier_delivery_pdf}, limit=1)
		if not file_doc:
			return []
		file_path = frappe.get_doc("File", file_doc[0].name).get_full_path()

		extracted_receipts = []

		with pdfplumber.open(file_path) as pdf:
			for page in pdf.pages:
				text = page.extract_text() or ""
				lines = [line.strip() for line in text.split("\n") if line.strip()]

				# Extract DO number
				do_no = ""
				do_match = re.search(r"DO-[\d/]+", text)
				if do_match:
					do_no = do_match.group()

				# Extract supplier name from the line containing SRRI/MILLS/SDN BHD
				supplier_raw = ""
				for line in lines:
					if "SRRI" in line or "MILLS" in line or "SDN BHD" in line:
						supplier_raw = re.split(r'\s{2,}', line)[0].strip()
						break
				if not supplier_raw and len(lines) > 1:
					supplier_raw = lines[1]

				# Parse item rows directly from text lines.
				# Row format: "No ItemCode Description Qty Unit Batch [Remarks]"
				# Example:    "1 D221-THAI-25K PULUT HITAM THAI 25KG 4.00 BAG 260107"
				current_items = []

				# Log ALL lines to Error Log so we can see exact pdfplumber output
				debug_log = []
				for i, ln in enumerate(lines):
					debug_log.append(f"[{i:02d}] {repr(ln)}")
				frappe.log_error(message="\n".join(debug_log), title="PDF All Lines Debug")

				for line in lines:
					# Skip known non-item lines
					if any(kw in line for kw in ["Item Code", "DELIVERY ORDER", "Taken By", "Taken Date", "Total", "Print Date"]):
						continue
					if re.match(r"^(No\s|Date\s|Page\s|Delivery Date)", line):
						continue

					parts = line.split()
					if len(parts) < 6:
						continue
					if not parts[0].isdigit():
						continue

					def is_number(s):
						try:
							float(s.replace(',', ''))
							return True
						except ValueError:
							return False

					# Match pattern: ... Qty UOM Batch [Price]
					# Qty must be a number, UOM should not be a pure number.
					if len(parts) >= 5 and is_number(parts[-3]) and not is_number(parts[-2]):
						qty = float(parts[-3].replace(',', ''))
						uom = parts[-2]
						batch = parts[-1]
						desc_end = -3
					elif len(parts) >= 6 and is_number(parts[-4]) and not is_number(parts[-3]) and is_number(parts[-1]):
						qty = float(parts[-4].replace(',', ''))
						uom = parts[-3]
						batch = parts[-2]
						desc_end = -4
					else:
						continue

					no = parts[0]
					raw_code = parts[1]
					desc_parts = parts[2:desc_end]
					
					# Smart un-weaving: find if raw_code starts with an existing Item Code in DB
					# This perfectly splits overlapping text like "D241-25KG/BAGHALBA"
					matched_code = frappe.db.sql("""
						SELECT name FROM `tabItem`
						WHERE %s LIKE concat(name, '%%')
						ORDER BY LENGTH(name) DESC LIMIT 1
					""", (raw_code,))
					
					if matched_code:
						item_code = matched_code[0][0]
						leftover = raw_code[len(item_code):]
						# Move the leftover (often garbage or description start) into the description
						description = (leftover + " " + " ".join(desc_parts)).strip()
						# Clean up common overlap artifacts like stray slashes
						if description.startswith("/"):
							description = description[1:].strip()
					else:
						# Fallback basic un-weaver for common format
						if "/BAG" in raw_code and not raw_code.endswith("/BAG"):
							idx = raw_code.find("/BAG") + 4
							leftover = raw_code[idx:]
							item_code = raw_code[:idx]
							description = leftover + " " + " ".join(desc_parts)
						else:
							item_code = raw_code
							description = " ".join(desc_parts)

					current_items.append({
						"no": no,
						"item_code": item_code,
						"description": description,
						"qty": qty,
						"uom": uom,
						"batch": batch,
						"remarks": ""
					})

				if current_items:
					extracted_receipts.append({
						"do_no": do_no,
						"supplier": supplier_raw,
						"items": current_items
					})
				else:
					# Log all lines for debugging
					frappe.log_error(message="\n".join(lines), title="PDF Debug: All Lines (No Items Found)")
					frappe.msgprint(f"Could not parse items from PDF. Logged all {len(lines)} lines to Error Log.")

		return extracted_receipts

	@frappe.whitelist()
	def get_items(self):
		try:
			if not self.supplier_delivery_pdf:
				return []

			extracted_receipts = self._get_extracted_data()
			result = []

			for rec in extracted_receipts:
				do_no = rec.get("do_no", "")
				supplier = rec.get("supplier", "")

				# Check if PR exists for this DO number
				pr_name = ""
				if do_no:
					pr_name = frappe.db.get_value("Purchase Receipt", {"name": do_no}, "name") or ""

				for itm in rec.get("items", []):
					item_code = itm.get("item_code")
					item_exists = frappe.db.exists("Item", item_code)

					result.append({
						"pr_name": pr_name,
						"do_no": do_no,
						"no": itm.get("no"),
						"item_code": item_code,
						"description": itm.get("description"),
						"qty": itm.get("qty"),
						"uom": itm.get("uom", ""),
						"batch": itm.get("batch"),
						"remarks": itm.get("remarks", ""),
						"status": "Found" if item_exists else "Not Found",
						"supplier": supplier
					})

			return result

		except Exception:
			frappe.log_error(message=frappe.get_traceback(), title="PDF get_items Error")
			return []


@frappe.whitelist()
def handle_pr_after_item(docname, do_no, item_row, supplier_name=""):
	import json
	try:
		row = json.loads(item_row) if isinstance(item_row, str) else item_row
		item_code = row.get("item_code")
		qty = float(row.get("qty") or 1)

		if not frappe.db.exists("Item", item_code):
			return {"status": "error", "error": f"Item '{item_code}' not found."}

		# Find Supplier
		find_supplier = frappe.db.get_all(
			"Supplier",
			filters={"supplier_name": ["like", f"%{supplier_name}%"]},
			limit=1
		)
		supplier_id = find_supplier[0].name if find_supplier else ""

		if do_no and frappe.db.exists("Purchase Receipt", do_no):
			pr = frappe.get_doc("Purchase Receipt", do_no)
		else:
			pr = frappe.new_doc("Purchase Receipt")
			if do_no:
				pr.name = do_no
			pr.supplier = supplier_id
			pr.posting_date = frappe.get_doc("PDF to Purchase Receipt", docname).date or datetime.today().date()

		if item_code not in [i.item_code for i in pr.items]:
			pr.append("items", {
				"item_code": item_code,
				"qty": qty,
				"schedule_date": pr.posting_date
			})

		pr.insert(ignore_permissions=True)
		frappe.db.commit()
		return {"status": "ok", "pr_name": pr.name}

	except Exception as e:
		return {"status": "error", "error": str(e)}
