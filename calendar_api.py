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
    try:
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

    except Exception as ex:
        print(f"check_availability error: {ex}")
        return False  # treat as busy on error to be safe


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
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': 'Asia/Kolkata'
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': 'Asia/Kolkata'
        },
        'attendees': [{'email': e} for e in (attendee_emails or [])],
    }

    service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates='all'
    ).execute()


# =========================
# 📅 DAY SLOTS
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

        # Handle all-day events (no dateTime, only date)
        if not s or not e:
            s_date = event['start'].get('date')
            e_date = event['end'].get('date')
            if s_date:
                # Mark whole day as busy
                busy_ranges.append((
                    start_of_day.replace(hour=9, minute=0),
                    start_of_day.replace(hour=18, minute=0)
                ))
            continue

        start = datetime.fromisoformat(s).astimezone(IST)
        end = datetime.fromisoformat(e).astimezone(IST)
        busy_ranges.append((start, end))

    slots = []
    current = start_of_day.replace(hour=9, minute=0, second=0, microsecond=0)

    while current.hour < 18:
        slot_end = current + timedelta(hours=1)
        is_busy = False

        for b_start, b_end in busy_ranges:
            if current < b_end and slot_end > b_start:
                is_busy = True
                break

        slots.append({
            "display": current.strftime("%I %p"),            # e.g. "09 AM"
            "time": current.isoformat(),                     # ✅ FIX: include ISO time for booking
            "hour": current.hour,
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
    now = datetime.now(IST)

    for day in range(0, 3):
        current_day = base + timedelta(days=day)

        for hour in range(9, 18):
            new_time = current_day.replace(hour=hour, minute=0, second=0, microsecond=0)

            # Skip past times
            if new_time <= now:
                continue

            # Skip the originally requested time
            if new_time == start_time.replace(minute=0, second=0, microsecond=0):
                continue

            if check_availability(new_time):
                suggestions.append({
                    "datetime": new_time.isoformat(),        # ✅ FIX: isoformat instead of raw datetime (JSON-serializable)
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
        user = user.strip()
        if not user:
            continue

        result[user] = []

        for h in range(9, 18):
            slot_start = start.replace(hour=h, minute=0, second=0, microsecond=0)
            slot_end = slot_start + timedelta(hours=1)

            try:
                body = {
                    "timeMin": slot_start.isoformat(),
                    "timeMax": slot_end.isoformat(),
                    "timeZone": "Asia/Kolkata",
                    "items": [{"id": user}]
                }

                res = service.freebusy().query(body=body).execute()
                busy = res["calendars"].get(user, {}).get("busy", [])

                # ✅ FIX: Only use freebusy API result (don't double-check with check_availability
                # which re-queries your own calendar and can give wrong results for other users)
                status = "busy" if busy else "free"

            except Exception as ex:
                print(f"freebusy error for {user} at {h}: {ex}")
                status = "free"  # assume free if we can't query (external user may block access)

            result[user].append({
                "hour": h,
                "status": status
            })

    return result


# =========================
# 👥 FIND COMMON SLOTS
# =========================

def find_common_slots(date, participants):
    if not participants:
        return []

    data = get_multi_user_availability(date, participants)

    common = []

    for hour in range(9, 18):
        idx = hour - 9  # index into each user's list

        all_free = True
        for user in participants:
            user = user.strip()
            if not user:
                continue
            if user not in data:
                continue
            # ✅ FIX: guard against index out of range
            if idx >= len(data[user]):
                all_free = False
                break
            if data[user][idx]["status"] != "free":
                all_free = False
                break

        if all_free:
            common.append(hour)

    return common


# =========================
# ⭐ SUGGEST BEST SLOT
# =========================

def suggest_best_slot(common):
    if not common:
        return None

    # Prefer mid-morning to early afternoon
    preferred = [h for h in common if 11 <= h <= 14]

    return preferred[0] if preferred else common[0]
