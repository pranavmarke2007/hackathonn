from flask import Flask, jsonify, render_template, request, redirect, session
from calendar_api import (
    check_availability, create_event, get_day_slots,
    suggest_alternatives, get_multi_user_availability,
    find_common_slots, suggest_best_slot, safe_localize
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
CORS(app)
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
    return any(word in text.lower() for word in [
        "meeting", "schedule", "call", "discussion", "availability",
        "available", "slot", "time", "confirm", "join"
    ])


def is_ambiguous(text):
    return not re.search(r'\b\d{1,2}[:\s]?\d{0,2}\s*(am|pm)\b', text.lower())


def is_notification_sender(sender):
    no_reply_patterns = ["noreply", "no-reply", "calendar-noreply", "accounts.google"]
    return any(p in sender.lower() for p in no_reply_patterns)


def participants_key(participants):
    """Canonical sorted key for a set of participants — used for DB deduplication."""
    return "team|" + "|".join(sorted(p.strip().lower() for p in participants if p.strip()))


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

    # session["credentials"] = {
    #     "token":         credentials.token,
    #     "refresh_token": credentials.refresh_token,
    #     "token_uri":     credentials.token_uri,
    #     "client_id":     credentials.client_id,
    #     "client_secret": credentials.client_secret,
    #     "scopes":        credentials.scopes
    # }
    global CREDS
    CREDS = credentials   # 🔥 STORE GLOBALLY

    return redirect("http://localhost:5173/app")
    # 🔥 CHANGE HERE
   


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/")
def home():
    if "credentials" in session:
        try:
            email = get_user_email()
        except:
            email = None
        return render_template("index.html", logged_in=True, user_email=email)
    return render_template("index.html", logged_in=False, user_email=None)


@app.route("/user_info")
def user_info():
    if "credentials" in session:
        try:
            return jsonify({"logged_in": True, "email": get_my_email(session["credentials"])})
        except:
            pass
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
    service  = get_gmail_service(creds_dict)
    my_email = get_my_email(creds_dict)

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
    """Delete a stale per-email record so it gets reprocessed correctly."""
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
    """
    Process one email.
    scheduled_slots: in-memory dict { pkey → {"hour": int, "date_str": str} }
    """
    body    = mail.get("body", "")
    sender  = mail.get("from", "")
    mail_id = mail.get("id", "")

    # Check per-email DB state FIRST to avoid reprocessing.
    # Exception: if the email is a reschedule that was previously misrouted
    # as a team booking (status starts with "🤖"), delete the stale record
    # and fall through to be reprocessed correctly.
    existing_email = get_email_state(mail_id)
    if existing_email:
        saved_status = existing_email.get("status", "")
        # If this is actually a reschedule email, don't serve the stale team status
        if is_reschedule(mail.get("body", "")) and saved_status.startswith("🤖"):
            delete_email_state(mail_id)   # force reprocessing
        else:
            mail["status"] = saved_status
            mail["tag"]    = existing_email.get("tag", "")
            return

    calendar_participants = list(set(extract_emails(body)))
    if my_email and my_email not in calendar_participants:
        calendar_participants.append(my_email)

    # ── RESCHEDULE — checked BEFORE team meeting because reschedule emails
    #    often also contain the word "team" and would be misrouted ─────
    if is_reschedule(body) and len(calendar_participants) > 1:
        mail["tag"] = "📅 Meeting"

        # base_pkey  → key used for the ORIGINAL booking (to find what slot to avoid)
        # reschedule_key → separate key so the reschedule is stored independently
        base_pkey      = participants_key(calendar_participants)
        reschedule_key = "reschedule|" + base_pkey

        # ── in-memory cache: already rescheduled this session ──
        if reschedule_key in scheduled_slots:
            booked_hour = scheduled_slots[reschedule_key]["hour"]
            date_str    = scheduled_slots[reschedule_key]["date_str"]
            status      = f"🔁 Already rescheduled to {booked_hour}:00 on {date_str}"
            mail["status"] = status
            save_email_state(mail_id, status, [], "📅 Meeting")
            return

        # ── DB check: reschedule was persisted in a previous request ──
        existing_reschedule = get_team_state(reschedule_key)
        if existing_reschedule:
            booked_hour = existing_reschedule.get("booked_hour")
            date_str    = existing_reschedule.get("date_str", "")
            status      = existing_reschedule.get("status", f"🔁 Already rescheduled to {booked_hour}:00")
            mail["status"] = status
            scheduled_slots[reschedule_key] = {"hour": booked_hour, "date_str": date_str}
            save_email_state(mail_id, status, [], "📅 Meeting")
            return

        # ── Look up the ORIGINAL booked slot to exclude it ──
        already_booked = None
        if base_pkey in scheduled_slots:
            already_booked = scheduled_slots[base_pkey]["hour"]
        else:
            original = get_team_state(base_pkey)
            if original:
                already_booked = original.get("booked_hour")

        # ── Not yet rescheduled — find a DIFFERENT common slot ──
        try:
            date_str = datetime.now(IST).strftime("%Y-%m-%d")
            common   = find_common_slots(date_str, calendar_participants)

            # Exclude the previously booked slot so we get a different time
            if already_booked is not None:
                common = [h for h in common if h != already_booked]

            best = suggest_best_slot(common)

            if best:
                meeting_dt = IST.localize(
                    datetime.strptime(date_str, "%Y-%m-%d").replace(
                        hour=best, minute=0, second=0, microsecond=0
                    )
                )
                create_event(
                    meeting_dt,
                    attendee_emails=[p for p in calendar_participants if p != my_email]
                )

                if not is_notification_sender(sender):
                    send_email(
                        sender,
                        "Rescheduled Meeting",
                        f"Hi,\n\nYour meeting has been rescheduled.\n\n"
                        f"New time:\n👉 {best}:00 on {date_str}\n\n"
                        f"The old slot ({already_booked}:00) has been replaced.\n\nAI Scheduler"
                    )

                status = (
                    f"🔁 Rescheduled to {best}:00 (was {already_booked}:00)"
                    if already_booked else
                    f"🔁 Rescheduled to {best}:00"
                )
                save_team_state(reschedule_key, status, best, date_str, "📅 Meeting")
                scheduled_slots[reschedule_key] = {"hour": best, "date_str": date_str}
                mail["status"] = status
                save_email_state(mail_id, status, [], "📅 Meeting")

            else:
                status = "❌ No alternative slot for reschedule"
                save_team_state(reschedule_key, status, None, date_str, "📅 Meeting")
                mail["status"] = status
                save_email_state(mail_id, status, [], "📅 Meeting")

        except Exception as e:
            print(f"Reschedule error: {e}\n{traceback.format_exc()}")
            mail["status"] = "⚠️ Reschedule error"

        return

    # ── TEAM MEETING ──────────────────────────────────────────
    if is_team_meeting(body) and len(calendar_participants) > 1:
        mail["tag"] = "📅 Meeting"

        pkey = participants_key(calendar_participants)

        # in-memory cache
        if pkey in scheduled_slots:
            booked_hour = scheduled_slots[pkey]["hour"]
            date_str    = scheduled_slots[pkey]["date_str"]
            status      = f"🤖 Suggested & Booked {booked_hour}:00 on {date_str}"
            mail["status"] = status
            save_email_state(mail_id, status, [], "📅 Meeting")
            return

        # DB check
        existing = get_team_state(pkey)
        if existing:
            booked_hour = existing.get("booked_hour")
            date_str    = existing.get("date_str", "")
            status      = existing.get("status", f"🤖 Already booked {booked_hour}:00")
            mail["status"] = status
            with lock:
                scheduled_slots[pkey] = {"hour": booked_hour, "date_str": date_str}
            save_email_state(mail_id, status, [], "📅 Meeting")
            return

        # Not yet scheduled — find best common slot and book
        try:
            date_str = datetime.now(IST).strftime("%Y-%m-%d")
            common   = find_common_slots(date_str, calendar_participants)
            best     = suggest_best_slot(common)

            if best:
                meeting_dt = IST.localize(
                    datetime.strptime(date_str, "%Y-%m-%d").replace(
                        hour=best, minute=0, second=0, microsecond=0
                    )
                )
                create_event(
                    meeting_dt,
                    attendee_emails=[p for p in calendar_participants if p != my_email]
                )

                if not is_notification_sender(sender):
                    send_email(
                        sender,
                        "Team Meeting Suggestion",
                        f"Hi,\n\nBest common slot for all participants:\n\n"
                        f"👉 {best}:00 on {date_str}\n\n"
                        f"Meeting has been created in your calendar.\n\nAI Scheduler"
                    )

                status = f"🤖 Suggested & Booked {best}:00"
                save_team_state(pkey, status, best, date_str, "📅 Meeting")
                with lock:    
                    scheduled_slots[pkey] = {"hour": best, "date_str": date_str}
                mail["status"] = status
                save_email_state(mail_id, status, [], "📅 Meeting")

            else:
                status = "❌ No common slot found"
                save_team_state(pkey, status, None, date_str, "📅 Meeting")
                mail["status"] = status
                save_email_state(mail_id, status, [], "📅 Meeting")

        except Exception as e:
            print(f"Team meeting error: {e}\n{traceback.format_exc()}")
            mail["status"] = "⚠️ Team scheduling error"

        return

    # ── NORMAL SINGLE-PERSON FLOW ─────────────────────────────

    tag        = "📅 Meeting" if is_meeting_related(body) else "📩 General"
    mail["tag"] = tag

    if not is_meeting_related(body):
        status = "ℹ️ Not a meeting"
        save_email_state(mail_id, status, [], tag)
        mail["status"] = status
        return

    if is_ambiguous(body):
        status = "❓ Ambiguous - no time found"
        save_email_state(mail_id, status, [], tag)
        mail["status"] = status
        return

    match     = re.search(r'(\d{1,2}.*?(am|pm))', body.lower())
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

    if check_availability(meeting_time):
        create_event(meeting_time, attendee_emails=[sender])
        status       = "✅ Scheduled"
        alternatives = []
    else:
        alternatives = suggest_alternatives(meeting_time)

        if alternatives:
            status   = "🟡 Busy (Alternatives sent)"
            alt_text = "\n".join(f"• {a['display']}" for a in alternatives)
            if not is_notification_sender(sender):
                send_email(
                    sender,
                    "Requested Slot Not Available",
                    f"Hi,\n\nThe time you requested is already booked.\n\n"
                    f"Available alternatives:\n{alt_text}\n\n"
                    f"Please reply with your preferred time.\n\nBest,\nAI Scheduler"
                )
        else:
            status       = "🔴 Busy (No alternatives)"
            alternatives = []

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
        return jsonify({"emails": []})

    try:
        emails = fetch_emails_from_gmail({
            "token": CREDS.token,
            "refresh_token": CREDS.refresh_token,
            "token_uri": CREDS.token_uri,
            "client_id": CREDS.client_id,
            "client_secret": CREDS.client_secret,
            "scopes": CREDS.scopes
        })
        print("✅ FETCHED:", emails)

    except Exception as e:
        print(f"FATAL fetch_emails_from_gmail: {e}\n{traceback.format_exc()}")
        return jsonify({"emails": []})

    my_email = None
    try:
        my_email = get_my_email({
            "token": CREDS.token,
            "refresh_token": CREDS.refresh_token,
            "token_uri": CREDS.token_uri,
            "client_id": CREDS.client_id,
            "client_secret": CREDS.client_secret,
            "scopes": CREDS.scopes
        })
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

    return jsonify({
        "emails": emails,
        "today": today_str
    })

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
        print(f"Day slots error: {e}\n{traceback.format_exc()}")
        return jsonify([])


# =========================
# 📅 MONTH OVERVIEW
# =========================

@app.route("/month_overview/<year>/<month>")
def month_overview(year, month):
    if "credentials" not in session:
        return jsonify([])
    try:
        year  = int(year)
        month = int(month)

        start   = IST.localize(datetime(year, month, 1))
        end     = start + timedelta(days=31)
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
            if s:
                busy_days.add(datetime.fromisoformat(s).astimezone(IST).day)
                continue
            s = e['start'].get('date')
            if s:
                busy_days.add(int(s.split('-')[2]))

        return jsonify(list(busy_days))

    except Exception as e:
        print(f"Month overview error: {e}\n{traceback.format_exc()}")
        return jsonify([])


# =========================
# 📌 BOOK SLOT
# =========================

@app.route("/book_slot", methods=["POST"])
def book_slot():
    if "credentials" not in session:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    try:
        data     = request.json
        time_str = data.get("time")
        if not time_str:
            return jsonify({"status": "error", "message": "No time provided"}), 400

        dt = safe_localize(datetime.fromisoformat(time_str))
        create_event(dt)
        return jsonify({"status": "booked"})

    except Exception as e:
        print(f"Book slot error: {e}\n{traceback.format_exc()}")
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
        return jsonify(get_multi_user_availability(date, participants))
    except Exception as e:
        print(f"Multi availability error: {e}")
        return jsonify({})


# =========================
# 🚀 RUN
# =========================

if __name__ == "__main__":
    print("🚀 SERVER STARTING...")
    app.run(debug=True, use_reloader=False)
