
import frappe
import requests
from twilio.rest import Client



@frappe.whitelist(allow_guest=True)
def receive_pdf():
    # get twilio settings
    easwari_settings = frappe.get_doc("Easwari Settings")
    TWILIO_SID = f"{easwari_settings.twilio_sid}"
    TWILIO_AUTH_TOKEN = f"{easwari_settings.twilio_auth_token}"
    TWILIO_WHATSAPP = f"whatsapp:{easwari_settings.twilio_whatsapp_number}"

    # Extract payload
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
    
    # Twilio client
    client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

    # Handle non-PDF or no attachment
    if num_media == 0 or media_type != "application/pdf":
        if easwari_settings.disable_whatsapp_response == 0:
            client.messages.create(
                from_=TWILIO_WHATSAPP,
                to=sender,
                body="Hello, please send a PDF file instead of text or other file types."
            )
        frappe.logger().error("Received a message, maybe no file attached or not a PDF.")
        return "No PDF"

    # Download PDF from Twilio MediaUrl
    response = requests.get(media_url, auth=(TWILIO_SID, TWILIO_AUTH_TOKEN))
    if response.status_code != 200:
        frappe.log_error(response.text, "Twilio Media Download Failed")
        return "Download failed"

    # Save the PDF file first
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": media_filename,
        "content": response.content,
        "is_private": 1
    })
    file_doc.insert(ignore_permissions=True)

    # Create Twilio Whatsapp Message Log and attach PDF via file_url
    doc = frappe.get_doc({
        "doctype": "Twilio Whatsapp Message Log",
        "messagesid": frappe.form_dict.get("MessageSid", ""),
        "messagetype": frappe.form_dict.get("MessageType", ""),
        "apiversion": frappe.form_dict.get("ApiVersion", ""),
        "smsmessagesid": frappe.form_dict.get("SmsMessageSid", ""),
        "mediaurl0": media_url or "",
        "nummedia": num_media or "",
        "profilename": frappe.form_dict.get("ProfileName", ""),
        "accountsid": frappe.form_dict.get("AccountSid", ""),
        "from": sender or "",
        "to": frappe.form_dict.get("To", ""),
        "mediacontenttype0": media_type or "",
        "body": frappe.form_dict.get("Body", ""),
        "channelmetadata": frappe.form_dict.get("ChannelMetadata", ""),
        "pdf": file_doc.file_url
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()

    # Send confirmation message
    if easwari_settings.disable_whatsapp_response == 0:
        client.messages.create(
            from_=TWILIO_WHATSAPP,
            to=sender,
            body="File received, Thank You."
        )

    # TwiML response
    frappe.local.response["http_status_code"] = 200
    frappe.local.response["content_type"] = "text/xml"
    frappe.local.response["response"] = """<?xml version="1.0" encoding="UTF-8"?><Response></Response>"""