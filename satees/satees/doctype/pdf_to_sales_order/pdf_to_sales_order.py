# Copyright (c) 2026, Abdul Hasib and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
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
						sales_id = str(row[0]).split(" ")
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
						item = row[0].split(" ")
						if len(item) > 5:
							current_order["items"].append({
								"item_code":     item[1].split('/')[0],
								"location":      item[-4],
								"qty":           item[-2],
								"delivery_date": item[-3],
							})

		if current_order:
			extracted_orders.append(current_order)

		result = []
		seq = 1
		for order in extracted_orders:
			so_no    = order.get("so_no", "")
			customer = order.get("customer", "")

			so_exists = frappe.db.exists("Sales Order", so_no) if so_no else False

			find_customer = frappe.db.get_all(
				"Customer",
				filters={"customer_name": ["like", f'%{customer}%']},
				fields=["name", "customer_name"],
				limit=1
			) if customer else []

			customer_found = len(find_customer) > 0
			customer_name  = find_customer[0].get("customer_name") if customer_found else customer
			customer_id    = find_customer[0].get("name")          if customer_found else ""

			for item in order.get("items", []):
				item_code    = item.get("item_code")
				raw_location = item.get("location", "")

				find_item = frappe.db.get_all(
					"Item",
					filters={"name": ["like", f'%{item_code}%']},
					fields=["name", "item_name"],
					limit=1
				)

				find_warehouse = frappe.db.get_all(
					"Warehouse",
					filters=[["name", "like", f'%{raw_location}%']],
					fields=["name"],
					limit=1
				)
				if not find_warehouse and raw_location:
					find_warehouse = frappe.db.get_all(
						"Warehouse",
						filters=[["warehouse_name", "like", f'%{raw_location}%']],
						fields=["name"],
						limit=1
					)

				if find_item:
					status      = "Found"
					description = find_item[0].get("item_name") or ""
				else:
					status      = "Missing"
					description = ""

				# Parse delivery date safely
				raw_date = item.get("delivery_date", "")
				try:
					
					parsed_date = (datetime.strptime(raw_date, "%d/%m/%y").date())
				except Exception:
					parsed_date = raw_date  # pass as-is if parsing fails

				result.append({
					"seq":            seq,
					"so_no":          so_no,
					"so_exists":      so_exists,
					"customer":       customer_name,
					"customer_id":    customer_id,
					"customer_found": customer_found,
					"item_code":      item_code,
					"description":    description,
					"raw_location":   raw_location,
					"location":       find_warehouse[0].get("name") if find_warehouse else "Not Found",
					"location_found": len(find_warehouse) > 0,
					"delivery_date":  parsed_date,
					"qty":            item.get("qty"),
					"status":         status,
				})
				seq += 1

		return result


	@frappe.whitelist()
	def search_customer(self, query):
		results = frappe.db.get_all(
			"Customer",
			filters={"customer_name": ["like", f'%{query}%']},
			fields=["name", "customer_name"],
			limit=10
		)
		return results


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
		"delivery_date":    delivery_date,
		"items": [{
			"item_code":     item_code,
			"qty":           qty,
			"delivery_date": delivery_date,
			"warehouse":     warehouse,
		}],
	})

	# Try to use the PDF SO number as document name
	if so_no:
		new_so.name = so_no

	new_so.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"status": "ok", "so_exists": False, "so_no": new_so.name}
