# import frappe
# import requests

# TWILIO_SID = "ACadb02ec72c739e0ad0c6834dbda242c8"
# TWILIO_AUTH_TOKEN = "c23fe160ac61077e5424849278b2e096"

# @frappe.whitelist(allow_guest=True)
# def receive_pdf():

#     num_media = int(frappe.form_dict.get("NumMedia", 0))
#     media_url = frappe.form_dict.get("MediaUrl0")
#     media_type = frappe.form_dict.get("MediaContentType0")

#     if num_media == 0:
#         return "No file"

#     if media_type != "application/pdf":
#         return "Not a PDF"

#     response = requests.get(
#         media_url,
#         auth=(TWILIO_SID, TWILIO_AUTH_TOKEN)
#     )

#     if response.status_code != 200:
#         frappe.log_error(response.text, "Twilio Media Download Failed")
#         return "Download failed"

#     file_doc = frappe.get_doc({
#         "doctype": "File",
#         "file_name": "whatsapp_file.pdf",
#         "content": response.content,
#         "is_private": 1
#     })

#     file_doc.insert(ignore_permissions=True)

#     return "OK"


import frappe
import requests
from twilio.rest import Client

TWILIO_SID = "ACadb02ec72c739e0ad0c6834dbda242c8"
TWILIO_AUTH_TOKEN = "c23fe160ac61077e5424849278b2e096"
TWILIO_WHATSAPP = "whatsapp:+14155238886"  # replace your live number with sandbox number

@frappe.whitelist(allow_guest=True)
def receive_pdf():
    sender = frappe.form_dict.get("From")
    if not sender:
        frappe.logger().error("Twilio webhook missing 'From'")
        return "Sender missing"

    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"

    num_media = int(frappe.form_dict.get("NumMedia", 0))
    media_url = frappe.form_dict.get("MediaUrl0")
    media_type = frappe.form_dict.get("MediaContentType0")
    media_filename = frappe.form_dict.get("MediaFilename0") or "whatsapp_file.pdf"

    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

    if num_media == 0 or media_type != "application/pdf":
        client.messages.create(
            from_=TWILIO_WHATSAPP,
            to=sender,
            body="Hello, please send a PDF file instead of text or other file types."
        )
        frappe.logger().error("Received a message, Maybe no file attached or not a pdf file.")
    else:
        # Download file
        response = requests.get(media_url, auth=(TWILIO_SID, TWILIO_AUTH_TOKEN))

        # Save with original filename
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": media_filename,
            "content": response.content,
            "is_private": 1
        })
        file_doc.insert(ignore_permissions=True)

        # Confirmation
        client.messages.create(
            from_=TWILIO_WHATSAPP,
            to=sender,
            body="File received. Thank you."
        )

    # TwiML response
    twiml = """<?xml version="1.0" encoding="UTF-8"?>
<Response></Response>
"""
    frappe.local.response["http_status_code"] = 200
    frappe.local.response["content_type"] = "text/xml"
    frappe.local.response["response"] = twiml