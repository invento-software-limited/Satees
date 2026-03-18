
import frappe
def before_insert(doc, method):
    # file_doc = frappe.get_doc("File", {"file_name": doc.pdf.split('/')[-1]})
    # file_path = file_doc.get_full_path()
    pdf_to_so = frappe.new_doc("Pdf To Sales Order")
    pdf_to_so.pdf = doc.pdf
    pdf_to_so.insert(ignore_permissions=True)
