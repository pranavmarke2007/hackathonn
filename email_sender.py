import base64
from email.mime.text import MIMEText
from calendar_api import get_service

def send_email(to, subject, body):

    service = get_service()  # uses logged-in user's creds

    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()