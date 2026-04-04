from flask import Flask, jsonify, render_template, request, redirect, session
from calendar_api import (
    check_availability, create_event, get_day_slots,
    suggest_alternatives, get_multi_user_availability,
    find_common_slots, suggest_best_slot
)
from db import emails_collection
from email_sender import send_email

import dateparser
import re
import pytz
from datetime import datetime, timedelta
from config import DEFAULT_TIMEZONE

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

import os

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"


# =========================
# 🔧 HELPERS
# =========================

def extract_emails(text):
    return re.findall(r'[\w\.-]+@[\w\.-]+', text)


def is_team_meeting(text):
    return "team" in text.lower() or "everyone" in text.lower()


def is_reschedule(text):
    return "reschedule" in text.lower() or "another time" in text.lower()


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
# 🔑 LOGIN
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


@app.route("/user_info")
def user_info():
    if "credentials" in session:
        return jsonify({
            "logged_in": True,
            "email": get_my_email(session["credentials"])
        })
    return jsonify({"logged_in": False, "email": ""})


# =========================
# 📧 GMAIL
# =========================

def get_gmail_service(creds_dict):
    creds = Credentials(**creds_dict)
    return build("gmail", "v1", credentials=creds)


def get_my_email(creds_dict):
    service = get_gmail_service(creds_dict)
    profile = service.users().getProfile(userId='me').execute()
    return profile.get("emailAddress")


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
        labelIds=['INBOX'],
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
        sender_email = ""

        for h in headers:
            if h["name"] == "Subject":
                subject = h["value"]
            if h["name"] == "From":
                match = re.search(r'<(.+?)>', h["value"])
                sender_email = match.group(1) if match else h["value"]

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
# 📦 DB
# =========================

def get_email_state(mail_id):
    return emails_collection.find_one({"mail_id": mail_id})


def save_email_state(mail_id, status, alternatives, tag):
    emails_collection.update_one(
        {"mail_id": mail_id},
        {"$set": {"status": status, "alternatives": alternatives, "tag": tag}},
        upsert=True
    )


# =========================
# 🧠 NLP
# =========================

def is_meeting_related(text):
    return any(word in text.lower() for word in [
        "meeting", "schedule", "call", "discussion", "availability",
        "available", "slot", "time", "confirm", "join"
    ])


def is_ambiguous(text):
    return not re.search(r'\b\d{1,2}[:\s]?\d{0,2}\s*(am|pm)\b', text.lower())


# =========================
# 📬 MAIN EMAIL ROUTE
# =========================

@app.route("/emails")
def get_all_emails():

    if "credentials" not in session:
        return jsonify([])

    try:
        creds = session["credentials"]
        emails = fetch_emails_from_gmail(creds)
    except Exception as e:
        print("Error fetching emails:", e)
        return jsonify([])

    for mail in emails:
        body = mail["body"]
        sender = mail["from"]
        mail_id = mail["id"]

        participants = extract_emails(body)

        # Add self to participants
        try:
            me = get_user_email()
            if me not in participants:
                participants.append(me)
        except Exception as e:
            print("Could not get user email:", e)

        # =========================
        # 👥 TEAM MEETING
        # =========================
        if is_team_meeting(body) and len(participants) > 1:
            try:
                date = datetime.now(IST).strftime("%Y-%m-%d")
                common = find_common_slots(date, participants)
                best = suggest_best_slot(common)

                if best:
                    send_email(
                        sender,
                        "Team Meeting Suggestion",
                        f"Hi,\n\nBest common slot for all participants:\n\n👉 {best}:00\n\nPlease confirm.\n\nAI Scheduler"
                    )
                    mail["status"] = f"🤖 Suggested {best}:00"
                    mail["tag"] = "📅 Meeting"
                else:
                    mail["status"] = "❌ No common slot found"
                    mail["tag"] = "📅 Meeting"
            except Exception as e:
                print("Team meeting error:", e)
                mail["status"] = "⚠️ Team meeting error"
                mail["tag"] = "📅 Meeting"
            continue

        # =========================
        # 🔁 RESCHEDULE
        # =========================
        if is_reschedule(body) and len(participants) > 1:
            try:
                date = datetime.now(IST).strftime("%Y-%m-%d")
                common = find_common_slots(date, participants)
                best = suggest_best_slot(common)

                if best:
                    send_email(
                        sender,
                        "Rescheduled Meeting",
                        f"Hi,\n\nNew suggested time:\n\n👉 {best}:00\n\nAI Scheduler"
                    )
                    mail["status"] = f"🔁 Rescheduled {best}:00"
                    mail["tag"] = "📅 Meeting"
                else:
                    mail["status"] = "❌ No slot for reschedule"
                    mail["tag"] = "📅 Meeting"
            except Exception as e:
                print("Reschedule error:", e)
                mail["status"] = "⚠️ Reschedule error"
                mail["tag"] = "📅 Meeting"
            continue

        # =========================
        # 🧠 NORMAL FLOW
        # =========================
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
            status = "❓ Ambiguous - no time found"
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

        try:
            if check_availability(meeting_time):
                create_event(meeting_time, attendee_emails=[sender])
                status = "✅ Scheduled"
                alternatives = []
            else:
                alternatives = suggest_alternatives(meeting_time)

                if alternatives:
                    status = "🟡 Busy (Alternatives sent)"
                    alt_text = "\n".join(f"• {a['display']}" for a in alternatives)
                    send_email(
                        sender,
                        "Requested Slot Not Available",
                        f"Hi,\n\nThe time you requested is already booked.\n\nHere are some available alternatives:\n{alt_text}\n\nPlease reply with your preferred time.\n\nBest,\nAI Scheduler"
                    )
                else:
                    status = "🔴 Busy (No alternatives)"
                    alternatives = []
        except Exception as e:
            print("Calendar error:", e)
            status = "⚠️ Calendar error"
            alternatives = []

        save_email_state(mail_id, status, alternatives, tag)
        mail["status"] = status

    return jsonify(emails)


# =========================
# 📅 DAY SLOTS
# =========================

@app.route("/day_slots/<date>")
def day_slots(date):
    if "credentials" not in session:
        return jsonify([])
    try:
        return jsonify(get_day_slots(date))
    except Exception as e:
        print("Day slots error:", e)
        return jsonify([])


# =========================
# 📅 MONTH OVERVIEW  ← was missing / broken indentation
# =========================

@app.route("/month_overview/<year>/<month>")
def month_overview(year, month):
    if "credentials" not in session:
        return jsonify([])

    try:
        year = int(year)
        month = int(month)

        start = IST.localize(datetime(year, month, 1))
        end = start + timedelta(days=31)

        service = build(
            "calendar", "v3",
            credentials=Credentials(**session["credentials"])
        )

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
                # all-day event
                s = e['start'].get('date')
                if s:
                    d = int(s.split('-')[2])
                    busy_days.add(d)
                continue
            d = datetime.fromisoformat(s).astimezone(IST).day
            busy_days.add(d)

        return jsonify(list(busy_days))

    except Exception as e:
        print("Month overview error:", e)
        return jsonify([])


# =========================
# 📌 BOOK SLOT  ← was missing in new app.py
# =========================

@app.route("/book_slot", methods=["POST"])
def book_slot():
    if "credentials" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    try:
        data = request.json
        time_str = data.get("time")

        if not time_str:
            return jsonify({"status": "error", "message": "No time provided"}), 400

        dt = IST.localize(datetime.fromisoformat(time_str))
        create_event(dt)
        return jsonify({"status": "booked"})

    except Exception as e:
        print("Book slot error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500


# =========================
# 👥 MULTI USER
# =========================

@app.route("/multi_availability/<date>")
def multi_availability(date):
    if "credentials" not in session:
        return jsonify({})

    participants = request.args.get("participants", "")
    if not participants:
        return jsonify({})

    try:
        participants = [p.strip() for p in participants.split(",") if p.strip()]
        data = get_multi_user_availability(date, participants)
        return jsonify(data)
    except Exception as e:
        print("Multi availability error:", e)
        return jsonify({})


# =========================
# 🚀 RUN
# =========================

if __name__ == "__main__":
    print("🚀 SERVER STARTING...")
    app.run(debug=True, use_reloader=False)
