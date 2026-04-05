from flask import Flask, jsonify, render_template, request, redirect, session
from calendar_api import (
    check_availability, create_event, get_day_slots,
    suggest_alternatives, get_multi_user_availability,
    find_common_slots, suggest_best_slot, safe_localize,
    set_creds, get_service   # ← NEW: import set_creds & get_service
)
from db import emails_collection
from email_sender import send_email
from flask_cors import CORS
import threading
import dateparser
import re
import pytz
import traceback
from datetime import datetime, timedelta
from config import DEFAULT_TIMEZONE

CREDS = None

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
import os

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)
CORS(app, supports_credentials=True, origins=["http://localhost:5173", "http://127.0.0.1:5173"])
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
# 🔧 TEXT HELPERS
# =========================

def extract_emails(text):
    return re.findall(r'[\w\.-]+@[\w\.-]+', text)

def is_team_meeting(text):
    return "team" in text.lower() or "everyone" in text.lower()

def is_reschedule(text):
    return "reschedule" in text.lower() or "another time" in text.lower()

def is_meeting_related(text):
    keywords = [
        "schedule meeting",
        "set up a meeting",
        "let's meet",
        "meeting at",
        "call at",
        "join meeting",
        "availability for meeting"
    ]
    text = text.lower()
    return any(k in text for k in keywords)
def is_ambiguous(text):
    return not re.search(r'\b\d{1,2}[:\s]?\d{0,2}\s*(am|pm)\b', text.lower())

def is_notification_sender(sender):
    no_reply_patterns = ["noreply", "no-reply", "calendar-noreply", "accounts.google"]
    return any(p in sender.lower() for p in no_reply_patterns)

def participants_key(participants):
    return "team|" + "|".join(sorted(p.strip().lower() for p in participants if p.strip()))


# =========================
# 🔑 LOGIN / OAUTH
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

    global CREDS
    CREDS = credentials

    # ✅ Also store in calendar_api module so all calendar functions work
    set_creds(credentials)

    print(f"✅ OAuth complete — token: {credentials.token[:20]}...")
    return redirect("http://localhost:5173/app")


@app.route("/logout")
def logout():
    global CREDS
    CREDS = None
    set_creds(None)
    session.clear()
    return redirect("http://localhost:5173")


@app.route("/")
def home():
    return render_template("index.html", logged_in=False, user_email=None)


# =========================
# 🔍 AUTH STATUS (for frontend to check)
# =========================

@app.route("/auth_status")
def auth_status():
    global CREDS
    if CREDS is not None:
        try:
            email = get_my_email_from_creds(CREDS)
            return jsonify({"logged_in": True, "email": email})
        except Exception as e:
            print(f"auth_status error: {e}")
    return jsonify({"logged_in": False, "email": ""})


# =========================
# 🗓️ CHECK CALENDAR (debug/verify events were created)
# =========================

@app.route("/check_calendar")
def check_calendar():
    """Returns upcoming AI Scheduled Meetings so frontend can confirm creation."""
    global CREDS
    if CREDS is None:
        return jsonify({"error": "not_logged_in", "events": []})
    try:
        service = get_service()
        now_ist = datetime.now(IST).isoformat()
        events  = service.events().list(
            calendarId='primary',
            timeMin=now_ist,
            maxResults=20,
            singleEvents=True,
            orderBy='startTime'
        ).execute().get('items', [])

        result = []
        for ev in events:
            result.append({
                "id":       ev.get("id"),
                "summary":  ev.get("summary", "(no title)"),
                "start":    ev['start'].get('dateTime') or ev['start'].get('date'),
                "end":      ev['end'].get('dateTime')   or ev['end'].get('date'),
                "link":     ev.get("htmlLink", ""),
                "attendees":[a.get("email") for a in ev.get("attendees", [])]
            })

        return jsonify({"events": result, "count": len(result)})
    except Exception as e:
        print(f"check_calendar error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e), "events": []})


# =========================
# 📧 GMAIL HELPERS
# =========================

def get_gmail_service(creds):
    return build("gmail", "v1", credentials=creds)

def get_my_email_from_creds(creds):
    service = get_gmail_service(creds)
    profile = service.users().getProfile(userId='me').execute()
    return profile.get("emailAddress")

def get_my_email():
    """Legacy helper used by routes that still check session — now uses global CREDS."""
    global CREDS
    if CREDS is None:
        return None
    return get_my_email_from_creds(CREDS)


def fetch_emails_from_gmail(creds):
    service  = get_gmail_service(creds)
    my_email = get_my_email_from_creds(creds)

    results  = service.users().messages().list(
        userId='me', labelIds=['INBOX'], maxResults=10
    ).execute()
    messages = results.get('messages', [])
    emails   = []

    for msg in messages:
        try:
            data    = service.users().messages().get(userId='me', id=msg['id']).execute()
            snippet = data.get("snippet", "")
            headers = data["payload"]["headers"]
            subject      = ""
            sender_email = ""
            for h in headers:
                if h["name"] == "Subject":
                    subject = h["value"]
                if h["name"] == "From":
                    match        = re.search(r'<(.+?)>', h["value"])
                    sender_email = match.group(1) if match else h["value"]
            if sender_email.lower() == my_email.lower():
                continue
            emails.append({
                "id":      msg["id"],
                "from":    sender_email,
                "subject": subject,
                "body":    snippet,
                "status":  "",
                "tag":     ""
            })
        except Exception as e:
            print(f"Error reading message {msg['id']}: {e}")
            continue

    return emails


# =========================
# 📦 DB
# =========================

def get_email_state(mail_id):
    try:
        return emails_collection.find_one({"mail_id": mail_id})
    except Exception as e:
        print(f"DB read error: {e}")
        return None

def save_email_state(mail_id, status, alternatives, tag):
    try:
        emails_collection.update_one(
            {"mail_id": mail_id},
            {"$set": {"status": status, "alternatives": alternatives, "tag": tag}},
            upsert=True
        )
    except Exception as e:
        print(f"DB write error: {e}")

def delete_email_state(mail_id):
    try:
        emails_collection.delete_one({"mail_id": mail_id})
    except Exception as e:
        print(f"DB delete error: {e}")

def get_team_state(pkey):
    try:
        return emails_collection.find_one({"mail_id": pkey})
    except Exception as e:
        print(f"DB team read error: {e}")
        return None

def save_team_state(pkey, status, booked_hour, date_str, tag):
    try:
        emails_collection.update_one(
            {"mail_id": pkey},
            {"$set": {
                "status":       status,
                "booked_hour":  booked_hour,
                "date_str":     date_str,
                "tag":          tag,
                "alternatives": []
            }},
            upsert=True
        )
    except Exception as e:
        print(f"DB team write error: {e}")


# =========================
# 📬 EMAIL PROCESSING
# =========================

def _process_single_email(mail, my_email, scheduled_slots, lock):

    body    = mail.get("body", "")
    sender  = mail.get("from", "")
    mail_id = mail.get("id", "")

    tag = "📅 Meeting" if is_meeting_related(body) else "📩 General"
    mail["tag"] = tag

    # ❌ NOT A MEETING
    if not is_meeting_related(body):
        status = "ℹ️ Not a meeting"
        save_email_state(mail_id, status, [], tag)
        mail["status"] = status
        return

    # ❓ AMBIGUOUS
    if is_ambiguous(body):
        status = "❓ Ambiguous - no time found"
        save_email_state(mail_id, status, [], tag)
        mail["status"] = status
        return

    # ⏰ EXTRACT TIME
    match = re.search(r'(\d{1,2}.*?(am|pm))', body.lower())
    time_text = match.group() if match else body

    meeting_time = dateparser.parse(
        time_text,
        settings={"PREFER_DATES_FROM": "future", "TIMEZONE": "Asia/Kolkata"}
    )

    if not meeting_time:
        status = "⚠️ Time not detected"
        save_email_state(mail_id, status, [], tag)
        mail["status"] = status
        return

    meeting_time = safe_localize(meeting_time)

    # =========================
    # ✅ CHECK AVAILABILITY
    # =========================

    if check_availability(meeting_time):

        # ❌ DO NOT CREATE EVENT AUTOMATICALLY
        # create_event(meeting_time, attendee_emails=[sender])

        status = "🟢 Slot Available"

        if not is_notification_sender(sender):
            send_email(
                sender,
                "Slot Available",
                f"Hi,\n\nThe requested time {meeting_time.strftime('%I:%M %p')} is available.\n\nReply YES to confirm booking.\n\nAI Scheduler"
            )

        alternatives = []

    else:
        alternatives = suggest_alternatives(meeting_time)

        if alternatives:
            status = "🟡 Busy (Alternatives sent)"

            alt_text = "\n".join(f"• {a['display']}" for a in alternatives)

            if not is_notification_sender(sender):
                send_email(
                    sender,
                    "Requested Slot Not Available",
                    f"Hi,\n\nThe time you requested is already booked.\n\nAvailable alternatives:\n{alt_text}\n\nPlease reply with your preferred time.\n\nAI Scheduler"
                )
        else:
            status = "🔴 Busy (No alternatives)"

    save_email_state(mail_id, status, alternatives, tag)
    mail["status"] = status


# =========================
# 📬 EMAILS ROUTE
# =========================

@app.route("/emails")
def get_all_emails():
    global CREDS

    if CREDS is None:
        print("❌ No credentials found")
        return jsonify({"emails": [], "today": datetime.now(IST).strftime("%Y-%m-%d")})

    try:
        emails = fetch_emails_from_gmail(CREDS)
        print(f"✅ Fetched {len(emails)} emails")
    except Exception as e:
        print(f"FATAL fetch_emails_from_gmail: {e}\n{traceback.format_exc()}")
        return jsonify({"emails": [], "today": datetime.now(IST).strftime("%Y-%m-%d")})

    my_email = None
    try:
        my_email = get_my_email_from_creds(CREDS)
    except Exception as e:
        print(f"Could not get user email: {e}")

    scheduled_slots = {}
    threads = []
    lock = threading.Lock()

    for mail in emails:
        t = threading.Thread(
            target=_process_single_email,
            args=(mail, my_email, scheduled_slots, lock)
        )
        t.start()
        threads.append(t)

    for t in threads:
        t.join()

    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    return jsonify({"emails": emails, "today": today_str})


# =========================
# 📅 DAY SLOTS  ← Fixed: uses global CREDS, no session check
# =========================

@app.route("/day_slots/<date>")
def day_slots(date):
    global CREDS
    if CREDS is None:
        print("❌ day_slots: no credentials")
        return jsonify([])
    try:
        slots = get_day_slots(date)
        print(f"✅ day_slots for {date}: {len(slots)} slots")
        return jsonify(slots)
    except Exception as e:
        print(f"day_slots error: {e}\n{traceback.format_exc()}")
        return jsonify([])


# =========================
# 📅 MONTH OVERVIEW  ← Fixed: uses global CREDS, no session check
# =========================

@app.route("/month_overview/<year>/<month>")
def month_overview(year, month):
    global CREDS
    if CREDS is None:
        print("❌ month_overview: no credentials")
        return jsonify([])
    try:
        year  = int(year)
        month = int(month)

        start   = IST.localize(datetime(year, month, 1))
        end     = start + timedelta(days=31)
        service = get_service()

        events = service.events().list(
            calendarId='primary',
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True
        ).execute().get('items', [])

        busy_days = set()
        for e in events:
            s = e['start'].get('dateTime')
            if s:
                busy_days.add(datetime.fromisoformat(s).astimezone(IST).day)
                continue
            s = e['start'].get('date')
            if s:
                busy_days.add(int(s.split('-')[2]))

        print(f"✅ month_overview {year}/{month}: {len(busy_days)} busy days")
        return jsonify(list(busy_days))

    except Exception as e:
        print(f"month_overview error: {e}\n{traceback.format_exc()}")
        return jsonify([])


# =========================
# 📌 BOOK SLOT  ← Fixed: uses global CREDS
# =========================

@app.route("/book_slot", methods=["POST"])
def book_slot():
    global CREDS
    if CREDS is None:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    try:
        data     = request.json
        time_str = data.get("time")
        if not time_str:
            return jsonify({"status": "error", "message": "No time provided"}), 400
        dt = safe_localize(datetime.fromisoformat(time_str))
        created = create_event(dt)
        return jsonify({"status": "booked", "event": created.get("htmlLink") if created else None})
    except Exception as e:
        print(f"book_slot error: {e}\n{traceback.format_exc()}")
        return jsonify({"status": "error", "message": str(e)}), 500


# =========================
# 👥 MULTI USER
# =========================

@app.route("/multi_availability/<date>")
def multi_availability(date):
    global CREDS
    if CREDS is None:
        return jsonify({})
    participants = request.args.get("participants", "")
    if not participants:
        return jsonify({})
    try:
        participants = [p.strip() for p in participants.split(",") if p.strip()]
        return jsonify(get_multi_user_availability(date, participants))
    except Exception as e:
        print(f"Multi availability error: {e}")
        return jsonify({})


# =========================
# 🚀 RUN
# =========================

if __name__ == "__main__":
    print("🚀 SERVER STARTING on http://localhost:5000")
    app.run(debug=True, use_reloader=False)
