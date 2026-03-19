
import frappe

def before_insert(doc, method):
    pdf_to_so = frappe.new_doc("Pdf To Sales Order")
    pdf_to_so.pdf = doc.pdf
    pdf_to_so.insert(ignore_permissions=True)
    frappe.db.commit()
