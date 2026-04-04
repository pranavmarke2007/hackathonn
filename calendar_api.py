from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from flask import session
import pytz

IST = pytz.timezone("Asia/Kolkata")


# =========================
# 🔑 SERVICE
# =========================
def get_service():
    creds = Credentials(**session["credentials"])
    return build("calendar", "v3", credentials=creds)


# =========================
# ✅ CHECK AVAILABILITY
# =========================
def check_availability(start_time):
    service = get_service()

    if start_time.tzinfo is None:
        start_time = IST.localize(start_time)

    end_time = start_time + timedelta(hours=1)

    events = service.events().list(
        calendarId='primary',
        timeMin=start_time.isoformat(),
        timeMax=end_time.isoformat(),
        singleEvents=True
    ).execute().get('items', [])

    for event in events:
        s = event['start'].get('dateTime')
        e = event['end'].get('dateTime')

        if not s or not e:
            continue

        existing_start = datetime.fromisoformat(s).astimezone(IST)
        existing_end = datetime.fromisoformat(e).astimezone(IST)

        if start_time < existing_end and end_time > existing_start:
            return False

    return True


# =========================
# 📅 CREATE EVENT
# =========================
def create_event(start_time, attendee_emails=None):
    service = get_service()

    if start_time.tzinfo is None:
        start_time = IST.localize(start_time)

    end_time = start_time + timedelta(hours=1)

    event = {
        'summary': 'AI Scheduled Meeting',
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end': {'dateTime': end_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'attendees': [{'email': e} for e in (attendee_emails or [])],
    }

    service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates='all'
    ).execute()


# =========================
# 🔥 FIXED SLOT FUNCTION
# =========================
def get_day_slots(date_str):
    service = get_service()

    start_of_day = IST.localize(datetime.strptime(date_str, "%Y-%m-%d"))
    end_of_day = start_of_day + timedelta(days=1)

    events = service.events().list(
        calendarId='primary',
        timeMin=start_of_day.isoformat(),
        timeMax=end_of_day.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

    busy_ranges = []

    for event in events:
        s = event['start'].get('dateTime')
        e = event['end'].get('dateTime')

        if not s or not e:
            continue

        start = datetime.fromisoformat(s).astimezone(IST)
        end = datetime.fromisoformat(e).astimezone(IST)

        print("EVENT:", start, "→", end)  # DEBUG

        busy_ranges.append((start, end))

    slots = []
    current = start_of_day.replace(hour=9, minute=0)

    while current.hour < 18:
        slot_end = current + timedelta(hours=1)

        print("SLOT:", current, "→", slot_end)

        is_busy = False

        for b_start, b_end in busy_ranges:
            if current < b_end and slot_end > b_start:
                is_busy = True
                break

        slots.append({
            "display": current.strftime("%I %p"),
            "status": "busy" if is_busy else "free"
        })

        current = slot_end

    return slots

# =========================
# 💡 SUGGEST ALTERNATIVES
# =========================
def suggest_alternatives(start_time):
    suggestions = []

    if start_time.tzinfo is None:
        start_time = IST.localize(start_time)

    base = start_time.replace(minute=0, second=0, microsecond=0)

    for day in range(0, 3):
        current_day = base + timedelta(days=day)

        for hour in range(9, 18):
            new_time = current_day.replace(hour=hour)

            if new_time <= datetime.now(IST):
                continue

            if new_time == start_time:
                continue

            if check_availability(new_time):
                suggestions.append({
                    "datetime": new_time,
                    "display": new_time.strftime("%d %B %I:%M %p")
                })

            if len(suggestions) >= 5:
                return suggestions

    return suggestions
# =========================
# 👥 MULTI USER AVAILABILITY
# =========================
def get_multi_user_availability(date, participants):
    service = get_service()

    start = IST.localize(datetime.strptime(date, "%Y-%m-%d"))
    result = {}

    for user in participants:
        result[user] = []

        for h in range(9, 18):
            slot_start = start.replace(hour=h, minute=0)
            slot_end = slot_start + timedelta(hours=1)

            body = {
                "timeMin": slot_start.isoformat(),
                "timeMax": slot_end.isoformat(),
                "timeZone": "Asia/Kolkata",
                "items": [{"id": user}]
            }

            res = service.freebusy().query(body=body).execute()

            busy = res["calendars"].get(user, {}).get("busy", [])

            status = "busy" if busy else "free"

            result[user].append({
                "hour": h,
                "status": status
            })

    return result