import frappe
from frappe.model.document import Document
import pdfplumber
import re
import json
from datetime import datetime


class PDFtoPurchaseReceipt(Document):
	def before_save(self):
		self.flags.is_backend_save = True
		if self.has_value_changed("supplier_delivery_pdf") or (not getattr(self, "pdf_data", None) and self.supplier_delivery_pdf):
			self.extract_pdf_data()

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

				# Extract Material Request ID (SO No. field, e.g. MAT-MR-2026-00001)
				mr_no = ""
				mr_match = re.search(
					r"(?:SO|MR|Material Request)\s*No\.?\s*[:\-]?\s*(MAT-MR-\d{4}-\d+)",
					text,
					re.IGNORECASE
				)
				if mr_match:
					mr_no = mr_match.group(1).strip()
				else:
					# Fallback: look for MAT-MR pattern anywhere in the text
					mr_fallback = re.search(r"(MAT-MR-[\w-]+)", text)
					if mr_fallback:
						mr_no = mr_fallback.group(1).strip()

				# Extract Date
				if not getattr(self, "date", None):
					date_match = re.search(r'(?i)Date\s*[:]\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', text)
					if date_match:
						date_str = date_match.group(1).replace('-', '/')
						try:
							if len(date_str.split('/')[-1]) == 2:
								self.date = datetime.strptime(date_str, "%d/%m/%y").date()
							else:
								self.date = datetime.strptime(date_str, "%d/%m/%Y").date()
						except ValueError:
							pass
					else:
						dt_match = re.search(r'\d{2}/\d{2}/\d{2}\s*\d{1,2}:\d{2}\s*[AP]M', text)
						if dt_match:
							self.date = datetime.strptime(dt_match.group(), "%d/%m/%y %I:%M %p").date()

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
						"mr_no": mr_no,
						"supplier": supplier_raw,
						"items": current_items
					})
				else:
					# Log all lines for debugging
					frappe.log_error(message="\n".join(lines), title="PDF Debug: All Lines (No Items Found)")
					frappe.msgprint(f"Could not parse items from PDF. Logged all {len(lines)} lines to Error Log.")

		return extracted_receipts

	@frappe.whitelist()
	def extract_pdf_data(self):
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
						"mr_no": rec.get("mr_no", ""),
						"items": []
					}
				grouped_data[do_no]["items"].extend(rec.get("items", []))

			result = []
			pr_to_save_on_doc = self.purchase_receipt

			for do_no, data in grouped_data.items():
				supplier_name = data["supplier_name"]
				mr_no = data.get("mr_no", "")
				items = data["items"]

				# Set Material Request link field on the document
				if mr_no:
					self.material_requiest = mr_no

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
				for itm in items:
					item_code = itm.get("item_code")
					batch_no = itm.get("batch", "")
					uom = itm.get("uom", "")
					
					# Refined lookup: exact match first
					if frappe.db.exists("Item", item_code):
						itm["status"] = "Found"
						# Ensure Match/Batch/UOM if present in PDF
						if batch_no:
							_ensure_batch(item_code, batch_no)
						if uom:
							_ensure_uom(uom)
					# Fallback: check before "/" if not found
					elif "/" in item_code:
						base_code = item_code.split("/")[0].strip()
						if frappe.db.exists("Item", base_code):
							itm["item_code"] = base_code
							itm["status"] = "Found"
							if batch_no:
								_ensure_batch(base_code, batch_no)
							if uom:
								_ensure_uom(uom)
						else:
							itm["status"] = "Not Found"
					else:
						itm["status"] = "Not Found"

				# Build result array for the UI table
				for itm in items:
					result.append({
						"pr_name": "", # Will be filled by sync_pr
						"do_no": do_no if do_no != "NO-DO" else "",
						"material_request": mr_no,
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

				# Append a unique suffix to each batch number.
			# Start from -001 and increment until a batch_id that doesn't exist in DB is found.
			for idx, row in enumerate(result):
				raw_batch = row.get("batch") or ""
				if raw_batch:
					counter = idx + 1
					while True:
						candidate = f"{raw_batch}-{str(counter).zfill(3)}"
						if not frappe.db.exists("Batch", {"batch_id": candidate}):
							break
						counter += 1
					row["batch"] = candidate

			self.pdf_data = json.dumps(result, default=str)
			self.sync_pr()
			return result

		except Exception:
			frappe.log_error(message=frappe.get_traceback(), title="PDF extract_pdf_data Error")
			return []

	@frappe.whitelist()
	def sync_pr(self):
		"""Update Purchase Receipt(s) based on the current pdf_data JSON."""
		try:
			if not self.pdf_data:
				return

			import json
			try:
				items_from_json = json.loads(self.pdf_data)
			except Exception:
				return

			# Group items by DO Number and Supplier
			grouped_by_do = {}
			for item in items_from_json:
				do_no = item.get("do_no") or "NO-DO"
				if do_no not in grouped_by_do:
					grouped_by_do[do_no] = {
						"supplier_name": item.get("supplier"),
						"items": []
					}
				grouped_by_do[do_no]["items"].append(item)

			pr_to_save_on_doc = ""

			for do_no, data in grouped_by_do.items():
				supplier_name = data["supplier_name"]
				items = data["items"]

				# Find Supplier
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

				found_items = [i for i in items if i.get("status") == "Found"]
				
				# Debugging why PR might not be created
				if not found_items or not supplier_id:
					frappe.log_error(
						message=f"PR skipped for DO {do_no}. Found Items: {len(found_items)}, Supplier ID: {supplier_id}",
						title="PDF sync_pr: SKIPPED"
					)

				if found_items and supplier_id:
					pr_name = items[0].get("pr_name")
					
					# Verify pr_name exists, otherwise check DO NO fallback
					if pr_name and not frappe.db.exists("Purchase Receipt", pr_name):
						pr_name = ""
					if not pr_name and do_no != "NO-DO" and frappe.db.exists("Purchase Receipt", do_no):
						pr_name = do_no

					if pr_name:
						pr = frappe.get_doc("Purchase Receipt", pr_name)
					else:
						pr = frappe.new_doc("Purchase Receipt")
						if do_no != "NO-DO":
							pr.name = do_no
						pr.supplier = supplier_id
						pr.posting_date = self.date or datetime.today().date()

					needs_save = False
					
					# Required items from PDF
					required_items = []
					for f_itm in found_items:
						required_items.append({
							"item_code": f_itm.get("item_code"),
							"uom": f_itm.get("uom") or "",
							"qty": float(f_itm.get("qty") or 0),
							"batch_no": f_itm.get("batch") or ""
						})
					
					# Track which existing rows match a required item
					current_items = pr.get("items")
					matched_existing_indices = set()
					final_items_data = []
					
					for req in required_items:
						matched_idx = -1
						for idx, existing in enumerate(current_items):
							if idx in matched_existing_indices:
								continue
							
							# Compare attributes
							if (existing.item_code == req["item_code"] and 
								existing.uom == req["uom"] and 
								abs(float(existing.qty) - req["qty"]) < 0.001 and 
								(existing.batch_no or "") == req["batch_no"]):
								matched_idx = idx
								break
						
						if matched_idx >= 0:
							# Keep existing row to maintain its properties
							final_items_data.append(current_items[matched_idx])
							matched_existing_indices.add(matched_idx)
						else:
							# Add new row from required data
							if req["batch_no"]:
								_ensure_batch(req["item_code"], req["batch_no"])
							if req["uom"]:
								_ensure_uom(req["uom"])
								
							new_row = {
								"item_code": req["item_code"],
								"qty": req["qty"],
								"uom": req["uom"],
								"batch_no": req["batch_no"],
								"schedule_date": pr.posting_date
							}
							final_items_data.append(new_row)
							needs_save = True

					# If the number of items changed, we definitely need a save
					if len(final_items_data) != len(current_items):
						needs_save = True

					if needs_save:
						pr.set("items", final_items_data)

					if needs_save or pr.get("__islocal"):
						if pr.get("__islocal"):
							pr.insert(ignore_permissions=True)
						else:
							pr.save(ignore_permissions=True)
						
						# Link back to this PDF doc on the PR using db_set to bypass
						# link validation (parent doc may not be in DB yet during before_save)
						if self.name and not self.name.startswith("new-"):
							try:
								pr.db_set("custom_pdf_to_purchase_receipt", self.name, update_modified=False)
							except Exception:
								frappe.log_error(message=frappe.get_traceback(), title="PR: set custom_pdf_to_purchase_receipt Error")
						
						# Update pr_name in our internal data if it was missing
						if not pr_to_save_on_doc:
							pr_to_save_on_doc = pr.name
						
						# Update the JSON items with the (potentially new) PR name
						for itm in items:
							itm["pr_name"] = pr.name

			# Finalize updates to self
			if pr_to_save_on_doc and pr_to_save_on_doc != self.purchase_receipt:
				self.purchase_receipt = pr_to_save_on_doc

			# Update status and pdf_data
			status_data = {"Found Items": 0, "Missing Items": 0}
			for item in items_from_json:
				key = "Found Items" if item.get("status") == "Found" else "Missing Items"
				status_data[key] += 1
			
			if len(items_from_json) > 0:
				if status_data["Missing Items"] == len(items_from_json):
					self.status = "Pending"
				elif status_data["Found Items"] == len(items_from_json):
					self.status = "Completed"
				else:
					self.status = "Partially Processed"

			self.pdf_data = json.dumps(items_from_json, default=str)

			if not self.flags.is_backend_save:
				self.db_set("status", self.status)
				self.db_set("pdf_data", self.pdf_data)
				self.db_set("purchase_receipt", self.purchase_receipt)
				if getattr(self, "material_requiest", None):
					self.db_set("material_requiest", self.material_requiest)
		
		except Exception:
			frappe.log_error(message=frappe.get_traceback(), title="PDF sync_pr Error")


def _ensure_batch(item_code, batch_no):
	"""Create a Batch record for item_code if it doesn't already exist."""
	if not batch_no:
		return
	
	# Enable Item Batch Tracking if disabled
	try:
		item_doc = frappe.get_doc("Item", item_code)
		if not item_doc.has_batch_no:
			item_doc.has_batch_no = 1
			item_doc.save(ignore_permissions=True)
	except Exception:
		# Log but don't fail the whole operation
		frappe.log_error(message=frappe.get_traceback(), title=f"Error enabling batch for Item {item_code}")

	if not frappe.db.exists("Batch", {"batch_id": batch_no, "item": item_code}):
		try:
			batch_doc = frappe.new_doc("Batch")
			batch_doc.batch_id = batch_no
			batch_doc.item = item_code
			batch_doc.insert(ignore_permissions=True)
		except Exception:
			# Log but don't fail the whole operation
			frappe.log_error(message=frappe.get_traceback(), title=f"Batch Create Error: {batch_no} / {item_code}")


def _ensure_uom(uom_name):
	"""Create a UOM record if it doesn't already exist."""
	if not uom_name:
		return
	if not frappe.db.exists("UOM", uom_name):
		try:
			uom_doc = frappe.new_doc("UOM")
			uom_doc.uom_name = uom_name
			uom_doc.insert(ignore_permissions=True)
		except Exception:
			# Log but don't fail the whole operation
			frappe.log_error(message=frappe.get_traceback(), title=f"UOM Create Error: {uom_name}")


@frappe.whitelist()
def handle_pr_after_item(docname, do_no, item_row, supplier_name="", batch_no="", old_item_code=""):
	import json
	try:
		row = json.loads(item_row) if isinstance(item_row, str) else item_row
		item_code = row.get("item_code")  # New item code
		uom = row.get("uom")

		parent_doc = frappe.get_doc("PDF to Purchase Receipt", docname)
		if not parent_doc.pdf_data:
			return {"status": "error", "error": "No PDF data found to update."}

		data = json.loads(parent_doc.pdf_data)
		item_updated = False
		
		for d in data:
			# Match by DO and old item code if possible
			match_do = (not do_no) or (d.get("do_no") == do_no)
			match_code = (not old_item_code) or (d.get("item_code") == old_item_code)
			
			if match_do and match_code and d.get("status") != "Found":
				d["item_code"] = item_code
				d["status"] = "Found"

				# Re-generate a unique batch suffix.
				# Strip any existing -NNN suffix first (e.g. '251231-001' → '251231').
				raw_batch = d.get("batch") or ""
				if raw_batch:
					base_batch = re.sub(r"-\d{3,4}$", "", raw_batch)
					counter = 1
					while True:
						candidate = f"{base_batch}-{str(counter).zfill(3)}"
						if not frappe.db.exists("Batch", {"batch_id": candidate}):
							break
						counter += 1
					d["batch"] = candidate

				item_updated = True
				break

		if item_updated:
			parent_doc.pdf_data = json.dumps(data, default=str)
			parent_doc.sync_pr() # This will update/create the Purchase Receipt
			parent_doc.save(ignore_permissions=True)

		return {"status": "ok", "pr_name": parent_doc.purchase_receipt}

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="PDF handle_pr_after_item Error")
		return {"status": "error", "error": str(e)}


@frappe.whitelist()
def handle_pr_after_supplier(docname, supplier_name):
	import json
	try:
		parent_doc = frappe.get_doc("PDF to Purchase Receipt", docname)
		if not parent_doc.pdf_data:
			return {"status": "error", "error": "No PDF data found to update."}

		data = json.loads(parent_doc.pdf_data)
		updated = False
		
		for d in data:
			if d.get("supplier") == supplier_name:
				d["supplier_status"] = "Found"
				updated = True

		if updated:
			parent_doc.pdf_data = json.dumps(data, default=str)
			parent_doc.sync_pr()
			parent_doc.save(ignore_permissions=True)

		return {"status": "ok", "pr_name": parent_doc.purchase_receipt}

	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="PDF handle_pr_after_supplier Error")
		return {"status": "error", "error": str(e)}
