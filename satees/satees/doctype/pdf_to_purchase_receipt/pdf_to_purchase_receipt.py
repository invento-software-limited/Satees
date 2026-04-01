import frappe
from frappe.model.document import Document
import pdfplumber
import re
from datetime import datetime


class PDFtoPurchaseReceipt(Document):
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

				# Extract supplier name dynamically (usually the first line below the top header)
				supplier_raw = ""
				for line in lines:
					# Skip the main title
					if "DELIVERY ORDER" in line.upper() or line.startswith("DO-"):
						continue
					
					# First substantial line is the supplier.
					# It might overlap with 'Date :' on the right due to PDF columns.
					# We strip any trailing parentheses or anything from 'Date' onwards.
					match = re.search(r"^(.*?)(?:\(?NO\..*?\)?|\(.*?\)?|\s+Date\s*:|\s+Date:)", line, re.IGNORECASE)
					if match:
						supplier_raw = match.group(1).strip()
					else:
						# If no date attached, take the first visual column (split by 2+ spaces)
						supplier_raw = re.split(r'\s{2,}', line)[0].strip()
					
					if len(supplier_raw) > 2:
						break

				# Fallback regex strip just in case
				supplier_raw = re.sub(r'\(.*?\)', '', supplier_raw).strip()

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
					try:
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
					except (IndexError, ValueError):
						continue

					no = parts[0]
					raw_code = parts[1]
					desc_start_idx = 2
					
					# Fragmentation fix: If next part starts with '-' or is something like '15KG/BAG'
					# check if it belongs to the Item Code.
					if len(parts) > 3:
						next_part = parts[2]
						if next_part.startswith("-") or any(uom in next_part.upper() for uom in ["/BAG", "/CTN", "/BOX", "KG", "GRAM"]):
							raw_code = raw_code + next_part
							desc_start_idx = 3

					desc_parts = parts[desc_start_idx:desc_end]
					
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
						elif "/BAG" in raw_code:
							# Case: "D899-W-15KG/BAG" fully in raw_code
							item_code = raw_code
							description = " ".join(desc_parts)
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
			if not extracted_receipts:
				return []

			# Consolidate all items across multiple pages if they belong to the same DO/Supplier
			# For now, we assume one PDF = one logical receipt unless DO numbers differ.
			# But usually, it is safer to group by DO Number.
			
			grouped_data = {}
			for rec in extracted_receipts:
				do_no = rec.get("do_no", "NO-DO")
				if do_no not in grouped_data:
					grouped_data[do_no] = {
						"supplier_name": rec.get("supplier", ""),
						"items": []
					}
				grouped_data[do_no]["items"].extend(rec.get("items", []))

			result = []
			pr_to_save_on_doc = self.purchase_receipt

			for do_no, data in grouped_data.items():
				supplier_name = data["supplier_name"]
				items = data["items"]

				# Locate Supplier ID
				supplier_id = ""
				if supplier_name:
					find_supplier = frappe.db.get_all(
						"Supplier",
						filters={"supplier_name": ["like", f"%{supplier_name}%"]},
						fields=["name"],
						limit=1
					)
					if find_supplier:
						supplier_id = find_supplier[0].name

				# Check for existing PR
				pr_name = ""
				# 1. Check if we already have a PR linked to this Doc
				if pr_to_save_on_doc and frappe.db.exists("Purchase Receipt", pr_to_save_on_doc):
					pr_name = pr_to_save_on_doc
				# 2. Check if a PR already exists with the DO number as name
				elif do_no != "NO-DO" and frappe.db.exists("Purchase Receipt", do_no):
					pr_name = do_no
				
				# Identify items already in DB vs missing
				found_items = []
				for itm in items:
					item_code = itm.get("item_code")
					batch_no = itm.get("batch", "")
					
					# Refined lookup: exact match first
					if frappe.db.exists("Item", item_code):
						itm["status"] = "Found"
						# Auto-create Batch if present in PDF and not yet in system
						if batch_no:
							_ensure_batch(item_code, batch_no)
						found_items.append(itm)
					# Fallback: check before "/" if not found
					elif "/" in item_code:
						base_code = item_code.split("/")[0].strip()
						if frappe.db.exists("Item", base_code):
							itm["item_code"] = base_code
							itm["status"] = "Found"
							if batch_no:
								_ensure_batch(base_code, batch_no)
							found_items.append(itm)
						else:
							itm["status"] = "Not Found"
					else:
						itm["status"] = "Not Found"

				# Auto-create/update PR if we have a supplier and items
				if found_items and supplier_id:
					if pr_name:
						pr = frappe.get_doc("Purchase Receipt", pr_name)
					else:
						pr = frappe.new_doc("Purchase Receipt")
						if do_no != "NO-DO":
							pr.name = do_no
						pr.supplier = supplier_id
						pr.posting_date = self.date or datetime.today().date()
					
					needs_save = False
					existing_combos = {
						(i.item_code, i.batch_no or "") for i in pr.items
					}
					for f_itm in found_items:
						combo = (f_itm.get("item_code"), f_itm.get("batch") or "")
						if combo not in existing_combos:
							pr.append("items", {
								"item_code": f_itm.get("item_code"),
								"qty": f_itm.get("qty"),
								"uom": f_itm.get("uom"),
								"batch_no": f_itm.get("batch") or "",
								"schedule_date": pr.posting_date
							})
							needs_save = True
					
					if needs_save or pr.get("__islocal"):
						if pr.get("__islocal"):
							pr.insert(ignore_permissions=True)
						else:
							pr.save(ignore_permissions=True)
						
						frappe.db.commit()
						pr_name = pr.name
						
						if not pr_to_save_on_doc:
							pr_to_save_on_doc = pr_name

				# Build result array for the UI table
				for itm in items:
					result.append({
						"pr_name": pr_name,
						"do_no": do_no if do_no != "NO-DO" else "",
						"no": itm.get("no"),
						"item_code": itm.get("item_code"),
						"description": itm.get("description"),
						"qty": itm.get("qty"),
						"uom": itm.get("uom", ""),
						"batch": itm.get("batch"),
						"remarks": itm.get("remarks", ""),
						"status": itm.get("status"),
						"supplier": supplier_name,
						"supplier_status": "Found" if supplier_id else "Not Found"
					})

			if pr_to_save_on_doc and pr_to_save_on_doc != self.purchase_receipt:
				self.purchase_receipt = pr_to_save_on_doc
				self.save()
				frappe.db.commit()
			
			status_data = {}
			for i in result:
				if i.get("status") == "Not Found":
					status_data.setdefault("Missing Items", 0)
					status_data["Missing Items"] += 1
				else:
					status_data.setdefault("Found Items", 0)
					status_data["Found Items"] += 1

			if len(result) == status_data.get("Missing Items", 0):
				self.status = "Pending"
			elif len(result) == status_data.get("Found Items", 0):
				self.status = "Completed"
			else:
				self.status = "Partially Processed"
			self.db_set("status", self.status)

			return result

		except Exception:
			frappe.log_error(message=frappe.get_traceback(), title="PDF get_items Error")
			return []


def _ensure_batch(item_code, batch_no):
	"""Create a Batch record for item_code if it doesn't already exist."""
	if not batch_no:
		return
	if not frappe.db.exists("Batch", {"batch_id": batch_no, "item": item_code}):
		try:
			batch_doc = frappe.new_doc("Batch")
			batch_doc.batch_id = batch_no
			batch_doc.item = item_code
			batch_doc.insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			# Log but don't fail the whole operation
			frappe.log_error(message=frappe.get_traceback(), title=f"Batch Create Error: {batch_no} / {item_code}")


@frappe.whitelist()
def handle_pr_after_item(docname, do_no, item_row, supplier_name="", batch_no=""):
	import json
	try:
		row = json.loads(item_row) if isinstance(item_row, str) else item_row
		item_code = row.get("item_code")

		if not frappe.db.exists("Item", item_code):
			return {"status": "error", "error": f"Item '{item_code}' not found."}

		# Create Batch for the newly created item if batch_no was in the PDF
		if batch_no:
			_ensure_batch(item_code, batch_no)

		# Re-run full get_items() on the PDF doc — this re-parses the PDF,
		# finds ALL items (including the one just created), and upserts all
		# of them into the Purchase Receipt using the item+batch combo check.
		parent_doc = frappe.get_doc("PDF to Purchase Receipt", docname)
		result = parent_doc.get_items()

		pr_name = ""
		if result:
			pr_name = result[0].get("pr_name", "")

		return {"status": "ok", "pr_name": pr_name}

	except Exception as e:
		return {"status": "error", "error": str(e)}
