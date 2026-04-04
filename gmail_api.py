from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


def get_gmail_service(creds_dict):
    creds = Credentials(**creds_dict)
    return build("gmail", "v1", credentials=creds)


def fetch_emails_from_gmail(creds_dict):
    service = get_gmail_service(creds_dict)

    results = service.users().messages().list(
        userId='me',
        maxResults=5
    ).execute()

    messages = results.get('messages', [])
    emails = []

    for msg in messages:
        data = service.users().messages().get(
            userId='me',
            id=msg['id']
        ).execute()

        snippet = data.get("snippet", "")
        headers = data["payload"]["headers"]

        subject = ""
        sender = ""

        for h in headers:
            if h["name"] == "Subject":
                subject = h["value"]
            if h["name"] == "From":
                sender = h["value"]

        emails.append({
            "from": sender,
            "body": snippet
        })

    return emails