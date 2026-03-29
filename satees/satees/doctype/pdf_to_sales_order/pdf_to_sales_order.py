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
		
		try:
			file_doc = frappe.get_doc("File", {"file_name": self.pdf.split('/')[-1]})
			file_path = file_doc.get_full_path()
			
			extracted_orders = []
			current_order = None
			last_date_time = None  # FIX 3: track across pages safely

			with pdfplumber.open(file_path) as pdf:
				for page in pdf.pages:
					date_time = re.search(r'\d{2}/\d{2}/\d{2}\s*\d{1,2}:\d{2}\s*[AP]M', page.extract_text() or "")
					
					self.date = datetime.strptime(date_time.group(), "%d/%m/%y %I:%M %p").date()
					table = page.extract_table()
					if not table:
						continue
					
					customer = ""
					for row in table:
						if not row or not row[0]:  # FIX 1: guard None rows/cells
							continue
						
						### Sales Order Id Find
						if str(row[0]).startswith("SO-"):
							sales_id = str(row[0]).split(" ")
							if current_order:
								extracted_orders.append(current_order)
							if not customer: ## first order row find customer second order not row exit customer use first row customer
								customer = " ".join(sales_id[1:]) if len(sales_id) > 1 else ""
							find_customer = frappe.db.get_all(
								"Customer",
								filters={"customer_name": ["like", f'%{customer}%']},
								fields=["name", "customer_name"]
							)
							
							if len(find_customer) == 1:
								current_order = {
									"so_no": sales_id[0],
									"customer": find_customer[0].name,
									"items": []
								}

						### Item List
						elif current_order and row[0][0].isdigit():  #  row[0] already checked non-None above
							item = row[0].split(" ")
							if len(item) > 5:
								find_item = frappe.db.get_all(
									"Item",
									filters={"name": ["like", f'%{item[1].split('/')[0]}%']},
									fields=["name", "item_name"]
								)
								find_warehouse = frappe.db.get_all(
									"Warehouse",
									filters={"name": ["like", f'%{item[-4]}%']},
									fields=["name"]
								)

								if len(find_item) > 0 and len(find_warehouse) > 0:
									current_order["items"].append({
										"item_code":find_item[0].name,
										"warehouse": find_warehouse[0].name,
										"qty": item[-2],
										"delivery_date": item[-3]
									})

			if current_order:
				extracted_orders.append(current_order)
			
			if extracted_orders:
				self.pdf_data = json.dumps(extracted_orders, default=str)

			if len(extracted_orders) > 0:
				for i in extracted_orders:
					if len(i.get("items")) > 0:
						so = frappe.new_doc("Sales Order")
						so.name = i.get("so_no")
						so.transaction_date = datetime.strptime(date_time.group(), "%d/%m/%y %I:%M %p").date()
						so.customer = i.get("customer")
						for item in i.get("items"):
							delivery_date = datetime.strptime(item.get("delivery_date"), "%d/%m/%y").date()

							so.append("items", {
								"item_code": item.get("item_code"),
								"qty": float(item.get("qty")),
								"delivery_date": delivery_date,
								"warehouse": item.get("warehouse")
							})
						so.insert(ignore_permissions=True)
						frappe.db.commit()

		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="PDF Processing Error")
			return {"status": "error", "message": str(e)}



	@frappe.whitelist()
	def get_items(self):
		if not self.pdf:
			return []

		file_doc = frappe.get_doc("File", {"file_name": self.pdf.split('/')[-1]})
		file_path = file_doc.get_full_path()

		extracted_orders = []
		current_order = None
		last_customer = ""

		with pdfplumber.open(file_path) as pdf:
			for page in pdf.pages:
				table = page.extract_table()
				if not table:
					continue

				for row in table:
					if not row or not row[0]:
						continue

					if str(row[0]).startswith("SO-"):
						sales_id = str(row[0]).split()  # Use split() to handle multiple spaces
						if current_order:
							extracted_orders.append(current_order)

						customer = " ".join(sales_id[1:]).strip() if len(sales_id) > 1 else ""
						if customer:
							last_customer = customer
						else:
							customer = last_customer

						current_order = {
							"so_no": sales_id[0],
							"customer": customer,
							"items": []
						}

					elif current_order and str(row[0])[0].isdigit():
						item = row[0].split()  # Use split()
						des = item[2:-4]
						
						if len(item) > 5:
							current_order["items"].append({
								"item_code":     item[1].split('/')[0],
								"location":      item[-4],
								"qty":           item[-2],
								"delivery_date": item[-3],
								"description": " ".join(des)
							})

		if current_order:
			extracted_orders.append(current_order)

		return self.map_extracted_data(extracted_orders)

	@frappe.whitelist()
	def revalidate_lookups(self):
		"""
		Re-run mapping logic based on existing pdf_data without re-extracting PDF.
		Useful if user created a Customer/Item/Warehouse and wants to update the status.
		"""
		if not self.pdf_data:
			return self.get_items()

		try:
			# The stored pdf_data is a list of results. We need to reconstruct
			# the 'extracted_orders' structure for map_extracted_data.
			results = json.loads(self.pdf_data)
			
			# Group by SO No and Customer
			orders_map = {}
			for res in results:
				key = (res['so_no'], res['customer'])
				if key not in orders_map:
					orders_map[key] = {
						"so_no": res['so_no'],
						"customer": res['customer'],
						"items": []
					}
				orders_map[key]['items'].append({
					"item_code":     res['item_code'], # This might be the resolved code, but that's fine
					"location":      res['raw_location'],
					"qty":           res['qty'],
					"delivery_date": res['delivery_date'],
					"description":   res['description']
				})
			
			extracted_orders = list(orders_map.values())
			return self.map_extracted_data(extracted_orders)
			
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="Revalidation Error")
			return self.get_items() # fallback to full extraction

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
		return result

	@frappe.whitelist()
	def create_sales_orders(self):
		if not self.pdf_data:
			frappe.throw("No data to process. Please extract PDF first.")

		data = json.loads(self.pdf_data)
		valid_items = [
			i for i in data 
			if i.get("customer_id") and i.get("item_code") and i.get("qty")
		]

		if not valid_items:
			frappe.msgprint("No valid rows found to create Sales Orders. Check if Customer and Item Code are resolved for each row.")
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


# ── Standalone whitelisted function ──────────────────────────────────────
@frappe.whitelist()
def handle_so_after_item(
	docname, so_no, so_exists, item_row,
	customer_id="", customer_name=""
):
	"""
	Scenario A: so_exists == 1 → append item to existing Sales Order
	Scenario B: so_exists == 0 → create new Sales Order with the item

	item_row JSON fields: item_code, qty, delivery_date, warehouse
	"""
	import json

	try:
		row = json.loads(item_row) if isinstance(item_row, str) else item_row
	except Exception:
		return {"status": "error", "error": "Invalid item_row JSON"}


	item_code    = row.get("item_code")
	qty          = frappe.utils.flt(row.get("qty") or 1)
	delivery_date = row.get("delivery_date")
	warehouse    = row.get("warehouse") or ""


	# ── Validate item ────────────────────────────────────────────────────
	if not frappe.db.exists("Item", item_code):
		return {"status": "error", "error": f"Item '{item_code}' not found in ERPNext"}

	# ── Scenario A: SO exists → add item ────────────────────────────────
	if int(so_exists):

		if not frappe.db.exists("Sales Order", so_no):
			return {"status": "error", "error": f"Sales Order '{so_no}' not found"}

		so_doc = frappe.get_doc("Sales Order", so_no)


		# Skip if item already present
		if item_code in [i.item_code for i in so_doc.items]:
			return {"status": "ok", "so_exists": True, "so_no": so_no, "note": "Item already in SO"}

		so_doc.append("items", {
			"item_code":     item_code,
			"qty":           qty,
			"delivery_date": datetime.strptime(delivery_date, "%Y-%m-%d").date(),
			"warehouse":     warehouse,
		})
		so_doc.save(ignore_permissions=True)
		frappe.db.commit()
		
		return {"status": "ok", "so_exists": True, "so_no": so_no}

	# ── Scenario B: SO not found → create ───────────────────────────────
	if not customer_id:
		found = frappe.db.get_all(
			"Customer",
			filters={"customer_name": ["like", f"%{customer_name}%"]},
			fields=["name"],
			limit=1,
		)
		if not found:
			return {
				"status": "error",
				"error": f"Customer '{customer_name}' not found. Please create the customer first."
			}
		customer_id = found[0]["name"]
	
	pdf_doc = frappe.get_doc("Pdf To Sales Order", docname)
	new_so = frappe.get_doc({
		"doctype":          "Sales Order",
		"customer":         customer_id,
		"transaction_date": pdf_doc.date,
		"delivery_date":    frappe.utils.getdate(delivery_date),
		"items": [{
			"item_code":     item_code,
			"qty":           qty,
			"delivery_date": frappe.utils.getdate(delivery_date),
			"warehouse":     warehouse,
		}],
	})

	# Try to use the PDF SO number as document name
	if so_no:
		new_so.name = so_no

	new_so.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "ok", "so_exists": False, "so_no": new_so.name}
