
import frappe

def after_insert(doc, method):
    pdf_to_so = frappe.new_doc("Pdf To Sales Order")
    pdf_to_so.pdf = doc.pdf
    pdf_to_so.twilio_whatsapp_message_log = doc.name
    pdf_to_so.insert(ignore_permissions=True)
    frappe.db.commit()
