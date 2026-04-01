# Copyright (c) 2026, Abdul Hasib and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import json
import pdfplumber
import re
from datetime import datetime


class PdfToSalesOrder(Document):
	def before_insert(self):
		self.extract_pdf_data()

	def after_insert(self):
		"""
		Automatically create Sales Orders for any valid rows immediately after upload.
		"""
		self.create_sales_orders()

	@frappe.whitelist()
	def get_items(self):
		"""
		Public method to trigger extraction manually (e.g. from UI button).
		"""
		return self.extract_pdf_data()

	def extract_pdf_data(self):
		"""
		Extracts text from PDF, parses into raw orders, and calls map_extracted_data.
		"""
		if not self.pdf:
			return []

		try:
			file_doc = frappe.get_doc("File", {"file_name": self.pdf.split('/')[-1]})
			file_path = file_doc.get_full_path()
			
			extracted_orders = []
			current_order = None
			last_customer = ""

			with pdfplumber.open(file_path) as pdf:
				for page in pdf.pages:
					# Find date/time for transaction date
					dt_match = re.search(r'\d{2}/\d{2}/\d{2}\s*\d{1,2}:\d{2}\s*[AP]M', page.extract_text() or "")
					if dt_match:
						self.date = datetime.strptime(dt_match.group(), "%d/%m/%y %I:%M %p").date()
					
					table = page.extract_table()
					if not table:
						continue
					
					for row in table:
						if not row or not row[0]: # safety
							continue
						
						# New Order? Starts with SO-
						if str(row[0]).startswith("SO-"):
							if current_order:
								extracted_orders.append(current_order)
							
							parts = str(row[0]).split() # split by any whitespace
							so_no = parts[0]
							customer_str = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
							
							# Handle multiline customer names across rows
							if customer_str:
								last_customer = customer_str
							else:
								customer_str = last_customer

							current_order = {
								"so_no": so_no,
								"customer": customer_str,
								"items": []
							}

						# Item row? Starts with digit
						elif current_order and str(row[0])[0].isdigit():
							item_parts = row[0].split()
							if len(item_parts) > 5:
								current_order["items"].append({
									"item_code":     item_parts[1].split('/')[0],
									"location":      item_parts[-4],
									"qty":           item_parts[-2],
									"delivery_date": item_parts[-3],
									"description":   " ".join(item_parts[2:-4])
								})

			if current_order:
				extracted_orders.append(current_order)

			return self.map_extracted_data(extracted_orders)

		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "PDF Extraction Failed")
			return []

	@frappe.whitelist()
	def revalidate_lookups(self):
		"""
		Re-run mapping logic based on existing pdf_data.
		"""
		if not self.pdf_data:
			return self.get_items()

		try:
			data = json.loads(self.pdf_data)
			orders_map = {}
			for res in data:
				key = (res['so_no'], res['customer'])
				if key not in orders_map:
					orders_map[key] = {"so_no": res['so_no'], "customer": res['customer'], "items": []}
				
				orders_map[key]['items'].append({
					"item_code":     res['item_code'],
					"location":      res['raw_location'],
					"qty":           res['qty'],
					"delivery_date": res['delivery_date'],
					"description":   res['description']
				})
			
			remapped = self.map_extracted_data(list(orders_map.values()))
			
			# Ensure DB and local doc are in sync
			self.pdf_data = json.dumps(remapped, default=str)
			self.db_set("pdf_data", self.pdf_data)
			
			return remapped
		except Exception as e:
			frappe.log_error(frappe.get_traceback(), "Revalidation Failed")
			return self.get_items()

	def map_extracted_data(self, extracted_orders):
		"""
		Takes a list of extracted order dicts and maps strings to DB records.
		"""
		result = []
		seq = 1
		for order in extracted_orders:
			so_no    = order.get("so_no", "")
			customer = order.get("customer", "").strip()

			so_exists = frappe.db.exists("Sales Order", so_no) if so_no else False

			find_customer = frappe.db.get_all(
				"Customer",
				filters={"name": customer},
				fields=["name", "customer_name"],
				limit=1
			) if customer else []
			if not find_customer and customer:
				find_customer = frappe.db.get_all(
					"Customer",
					filters={"customer_name": ["like", f'%{customer}%']},
					fields=["name", "customer_name"],
					limit=1
				)

			customer_found = len(find_customer) > 0
			customer_name  = find_customer[0].get("customer_name") if customer_found else customer
			customer_id    = find_customer[0].get("name")          if customer_found else ""

			for item in order.get("items", []):
				item_code    = item.get("item_code")
				raw_location = item.get("location", "")

				find_item = frappe.db.get_all(
					"Item",
					filters={"name": item_code},
					fields=["name", "item_name"],
					limit=1
				)
				if not find_item:
					find_item = frappe.db.get_all(
						"Item",
						filters={"name": ["like", f'%{item_code}%']},
						fields=["name", "item_name"],
						limit=1
					)

				find_warehouse = frappe.db.get_all(
					"Warehouse",
					filters={"name": raw_location},
					fields=["name"],
					limit=1
				) if raw_location else []
				if not find_warehouse and raw_location:
					find_warehouse = frappe.db.get_all(
						"Warehouse",
						filters=[["name", "like", f'%{raw_location}%']],
						fields=["name"],
						limit=1
					)

				if find_item:
					status      = "Found"
					description = find_item[0].get("item_name") or ""
					resolved_code = find_item[0].get("name") or ""
				else:
					status      = "Missing"
					description = item.get("description")
					resolved_code = item_code

				# Parse delivery date safely
				raw_date = item.get("delivery_date", "")
				try:
					# Handle both "dd/mm/yy" (from PDF) and "YYYY-MM-DD" (from existing JSON)
					if isinstance(raw_date, str) and "-" in raw_date:
						parsed_date = raw_date
					else:
						# Note: check if format is dd/mm/yy or dd/mm/yyyy
						parsed_date = frappe.utils.getdate(datetime.strptime(raw_date, "%d/%m/%y"))
				except Exception:
					# Fallback for other formats
					parsed_date = frappe.utils.getdate(raw_date) if raw_date else ""

				result.append({
					"seq":            seq,
					"so_no":          so_no,
					"so_exists":      so_exists,
					"customer":       customer_name,
					"customer_id":    customer_id,
					"customer_found": customer_found,
					"item_code":      resolved_code,
					"item_found":     status == "Found",
					"description":    description,
					"raw_location":   raw_location,
					"location":       find_warehouse[0].get("name") if find_warehouse else "Not Found",
					"location_found": len(find_warehouse) > 0,
					"delivery_date":  parsed_date,
					"qty":            item.get("qty"),
					"status":         status,
				})
				seq += 1

		self.pdf_data = json.dumps(result, default=str)
		# Clear the save indicator so the user can see it updated the field
		self.db_set("pdf_data", self.pdf_data)

		status_data = {}
		pdf_data_list = json.loads(self.pdf_data)
		for i in pdf_data_list:
			if i.get("status") == "Missing":
				status_data.setdefault("Missing Items", 0)
				status_data["Missing Items"] += 1
			else:
				status_data.setdefault("Found Items", 0)
				status_data["Found Items"] += 1
		
		
		if len(pdf_data_list)  == status_data.get("Missing Items", 0):
			self.status = "Pending"
		elif len(pdf_data_list)  == status_data.get("Found Items", 0):
			self.status = "Completed"
		else:
			self.status = "Partially Processed"
		
		self.db_set("status", self.status)
		return result
	
	

	@frappe.whitelist()
	def create_sales_orders(self):
		if not self.pdf_data:
			frappe.throw("No data to process. Please extract PDF first.")

		data = json.loads(self.pdf_data)
		# Ensure all required fields are present for processing
		valid_items = []
		for i in data:
			cust_id = i.get("customer_id")
			item_code = i.get("item_code")
			warehouse = i.get("location")
			qty = i.get("qty")
			
			if (cust_id and item_code and qty and warehouse and warehouse != "Not Found" and
				frappe.db.exists("Customer", cust_id) and 
				frappe.db.exists("Item", item_code) and 
				frappe.db.exists("Warehouse", warehouse)):
				valid_items.append(i)

		if not valid_items:
			frappe.msgprint("No valid rows found to create Sales Orders. Ensure Customer, Item Code, and Location (Warehouse) are all resolved for each row.")
			return

		# Group by (customer_id, so_no)
		groups = {}
		for item in valid_items:
			key = (item["customer_id"], item.get("so_no", ""))
			if key not in groups:
				groups[key] = []
			groups[key].append(item)

		summary = []
		for (cust_id, so_no), items in groups.items():
			try:
				so_doc = None
				is_new = False
				
				if so_no and frappe.db.exists("Sales Order", so_no):
					so_doc = frappe.get_doc("Sales Order", so_no)
				else:
					so_doc = frappe.new_doc("Sales Order")
					so_doc.customer = cust_id
					so_doc.transaction_date = self.date or frappe.utils.today()
					if so_no:
						so_doc.name = so_no
						so_doc.set("__newname", so_no)
						so_doc.flags.name_set = True
					is_new = True

				for itm in items:
					# Basic check to avoid redundant items if updating
					existing_item = False
					if not is_new:
						# Simple check: same item code and qty and date
						for existing in so_doc.items:
							if (existing.item_code == itm["item_code"] and 
								abs(frappe.utils.flt(existing.qty) - frappe.utils.flt(itm["qty"])) < 0.001):
								existing_item = True
								break
					
					if not existing_item:
						so_doc.append("items", {
							"item_code":     itm["item_code"],
							"qty":           frappe.utils.flt(itm["qty"]),
							"warehouse":     itm.get("location") if itm.get("location") != "Not Found" else None,
							"delivery_date": frappe.utils.getdate(itm.get("delivery_date")) or so_doc.transaction_date
						})
				
				if is_new or so_doc.has_value_changed("items"):
					so_doc.save(ignore_permissions=True)
					frappe.db.commit()
					action = "Created" if is_new else "Updated"
					summary.append(f"{action} {so_doc.name} for {cust_id} ({len(items)} items)")
				else:
					summary.append(f"No changes for {so_doc.name}")
				
			except Exception as e:
				frappe.log_error(frappe.get_traceback(), "Bulk SO Creation Error")
				summary.append(f"Error processing {so_no or 'New SO'} for {cust_id}: {str(e)}")

		return "\n".join(summary)


