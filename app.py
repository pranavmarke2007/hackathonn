from flask import Flask, jsonify, render_template, request, redirect, session
from calendar_api import (
    check_availability, create_event, get_day_slots,
    suggest_alternatives, get_multi_user_availability
)
from db import emails_collection
from email_sender import send_email

import dateparser
import re
import pytz
from config import DEFAULT_TIMEZONE

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

import os

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)
app.secret_key = "supersecret"

IST = pytz.timezone(DEFAULT_TIMEZONE)

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid"
]

flow = Flow.from_client_secrets_file(
    "client_secret.json",
    scopes=SCOPES,
    redirect_uri="http://localhost:5000/callback"
)

# =========================
# 🔑 LOGIN ROUTES
# =========================

@app.route("/login")
def login():
    session.clear()

    auth_url, _ = flow.authorization_url(
        prompt='consent select_account',
        access_type='offline',
        include_granted_scopes='true'
    )

    return redirect(auth_url)


@app.route("/user_info")
def user_info():
    if "credentials" in session:
        return jsonify({
            "logged_in": True,
            "email": get_my_email(session["credentials"])
        })
    return jsonify({
        "logged_in": False,
        "email": ""
    })

@app.route("/callback")
def callback():
    flow.fetch_token(authorization_response=request.url)

    credentials = flow.credentials

    session["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes
    }

    return redirect("/")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/")
def home():
    if "credentials" in session:
        email = get_user_email()
        return render_template("index.html", logged_in=True, user_email=email)
    return render_template("index.html", logged_in=False, user_email=None)

# =========================
# 🔥 GMAIL HELPERS
# =========================

def get_gmail_service(creds_dict):
    creds = Credentials(**creds_dict)
    return build("gmail", "v1", credentials=creds)


def get_my_email(creds_dict):
    service = get_gmail_service(creds_dict)
    profile = service.users().getProfile(userId='me').execute()
    return profile.get("emailAddress")

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
def get_user_email():
    creds = Credentials(**session["credentials"])
    service = build("gmail", "v1", credentials=creds)
    profile = service.users().getProfile(userId='me').execute()
    return profile.get("emailAddress")

def fetch_emails_from_gmail(creds_dict):
    service = get_gmail_service(creds_dict)

    my_email = get_my_email(creds_dict)

    results = service.users().messages().list(
        userId='me',
        labelIds=['INBOX'],   # ✅ only inbox
        maxResults=10
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
        sender_email = ""

        for h in headers:
            if h["name"] == "Subject":
                subject = h["value"]

            if h["name"] == "From":
                sender = h["value"]

                match = re.search(r'<(.+?)>', sender)
                sender_email = match.group(1) if match else sender

        # ❌ skip own emails
        if sender_email.lower() == my_email.lower():
            continue

        emails.append({
            "id": msg["id"],
            "from": sender_email,
            "subject": subject,
            "body": snippet
        })

    return emails


# =========================
# 🔥 DB HELPERS
# =========================

def get_email_state(mail_id):
    return emails_collection.find_one({"mail_id": mail_id})


def save_email_state(mail_id, status, alternatives, tag):
    emails_collection.update_one(
        {"mail_id": mail_id},
        {
            "$set": {
                "status": status,
                "alternatives": alternatives,
                "tag": tag
            }
        },
        upsert=True
    )


# =========================
# 🔥 BETTER KEYWORDS
# =========================

meeting_keywords = [
    "meeting", "schedule", "call",
    "discussion", "meet", "availability",
    "available", "slot", "time", "reschedule",
    "confirm", "join"
]

def is_meeting_related(text):
    return any(word in text.lower() for word in meeting_keywords)

def is_ambiguous(text):
    return not re.search(r'\b\d{1,2}[:\s]?\d{0,2}\s*(am|pm)\b', text.lower())


# =========================
# 🔥 EMAIL PROCESSING
# =========================

@app.route("/emails")
def get_all_emails():

    creds = session.get("credentials")
    if not creds:
        return jsonify([])

    emails = fetch_emails_from_gmail(creds)

    for mail in emails:
        body = mail["body"]
        sender = mail["from"]
        mail_id = mail["id"]

        existing = get_email_state(mail_id)
        if existing:
            mail["status"] = existing.get("status", "")
            mail["tag"] = existing.get("tag", "")
            continue

        tag = "📅 Meeting" if is_meeting_related(body) else "📩 General"
        mail["tag"] = tag

        if not is_meeting_related(body):
            status = "ℹ️ Not a meeting"
            save_email_state(mail_id, status, [], tag)
            mail["status"] = status
            continue

        if is_ambiguous(body):
            status = "❓ Ambiguous"
            save_email_state(mail_id, status, [], tag)
            mail["status"] = status
            continue

        match = re.search(r'(\d{1,2}.*?(am|pm))', body.lower())
        time_text = match.group() if match else body

        meeting_time = dateparser.parse(
            time_text,
            settings={"PREFER_DATES_FROM": "future"}
        )

        if not meeting_time:
            status = "⚠️ Time not detected"
            save_email_state(mail_id, status, [], tag)
            mail["status"] = status
            continue

        meeting_time = IST.localize(meeting_time)

        if check_availability(meeting_time):
            create_event(meeting_time, attendee_emails=[sender])
            status = "✅ Scheduled"
            alternatives = []

        else:
            alternatives = suggest_alternatives(meeting_time)

            if alternatives:
                status = "🟡 Busy (Alternatives sent)"

                alt_text = "\n".join(
                    f"• {a['display']}" for a in alternatives
                )

                send_email(
                    sender,
                    "Requested Slot Not Available",
                    f"""Hi,

                    The time you requested is already booked.

                    Here are some available alternatives:
                    {alt_text}

                    Please reply with your preferred time.

                    Best,
                    AI Scheduler"""
                )

            else:
                status = "🔴 Busy (No alternatives)"

        save_email_state(mail_id, status, alternatives, tag)
        mail["status"] = status

    return jsonify(emails)

# =========================
# 👥 MULTI USER
# =========================

@app.route("/multi_availability/<date>")
def multi_availability(date):
    participants = request.args.get("participants")

    if not participants:
        return jsonify({})

    participants = participants.split(",")

    data = get_multi_user_availability(date, participants)
    return jsonify(data)


# =========================
# 📅 DAY SLOTS
# =========================

@app.route("/day_slots/<date>")
def day_slots(date):
    creds = session.get("credentials")
    return jsonify(get_day_slots(date))

@app.route("/month_overview/<year>/<month>")
def month_overview(year, month):
    from datetime import datetime, timedelta

    year = int(year)
    month = int(month)

    start = IST.localize(datetime(year, month, 1))
    end = start + timedelta(days=31)

    service = build("calendar", "v3", credentials=Credentials(**session["credentials"]))

    events = service.events().list(
        calendarId='primary',
        timeMin=start.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True
    ).execute().get('items', [])

    busy_days = set()

    for e in events:
        s = e['start'].get('dateTime')
        if not s:
            continue
        d = datetime.fromisoformat(s).astimezone(IST).day
        busy_days.add(d)

    return jsonify(list(busy_days))
    @app.route("/book_slot", methods=["POST"])
    def book_slot():
        data = request.json
        dt = datetime.fromisoformat(data["time"])
        create_event(dt)
        return jsonify({"status": "booked"})
# =========================
# 🚀 RUN
# =========================

if __name__ == "__main__":
    print("🚀 SERVER STARTING...")
    app.run(debug=True, use_reloader=False)
    