import imaplib
import email
from config import EMAIL, PASSWORD

def fetch_emails():
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(EMAIL, PASSWORD)
    mail.select("inbox")

    status, data = mail.search(None, "ALL")
    email_ids = data[0].split()[-5:]

    result = []

    for eid in email_ids[::-1]:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        subject = msg["subject"]
        sender = msg["from"]

        body = ""

        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body = part.get_payload(decode=True).decode(errors="ignore")
                        break
                    except:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode(errors="ignore")
            except:
                pass

        result.append({
            "subject": subject,
            "from": sender,
            "body": body
        })

    mail.logout()
    return result