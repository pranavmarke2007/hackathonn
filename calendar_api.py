from datetime import datetime, timedelta
from googleapiclient.discovery import build
import pytz

IST = pytz.timezone("Asia/Kolkata")

CREDS = None

def set_creds(credentials):
    global CREDS
    CREDS = credentials

def get_service():
    if CREDS is None:
        raise RuntimeError("No credentials available — user not logged in")
    return build("calendar", "v3", credentials=CREDS)

def safe_localize(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return IST.localize(dt)
    return dt.astimezone(IST)

# =========================
# ✅ CHECK AVAILABILITY (FIXED)
# =========================

def check_availability(start_time):
    try:
        service    = get_service()
        start_time = safe_localize(start_time)
        end_time   = start_time + timedelta(hours=1)
        now        = datetime.now(IST)

        if start_time <= now:
            return False
        if start_time.hour < 9 or start_time.hour >= 18:
            return False

        events = service.events().list(
            calendarId='primary',
            timeMin=start_time.isoformat(),
            timeMax=end_time.isoformat(),
            singleEvents=True
        ).execute().get('items', [])

        for event in events:

            summary = event.get("summary", "").lower()

            # 🔥 ignore fake AI events
            if "ai scheduled meeting" in summary:
                continue

            s = event['start'].get('dateTime')
            e = event['end'].get('dateTime')

            # 🔥 ignore all-day events
            if not s or not e:
                continue

            existing_start = datetime.fromisoformat(s).astimezone(IST)
            existing_end   = datetime.fromisoformat(e).astimezone(IST)

            if start_time < existing_end and end_time > existing_start:
                return False

        return True

    except Exception as ex:
        print(f"check_availability error: {ex}")
        return False

# =========================
# 📅 CREATE EVENT (SAFE)
# =========================

def create_event(start_time, attendee_emails=None):
    service    = get_service()
    start_time = safe_localize(start_time)
    end_time   = start_time + timedelta(hours=1)

    existing_events = service.events().list(
        calendarId='primary',
        timeMin=start_time.isoformat(),
        timeMax=end_time.isoformat(),
        singleEvents=True
    ).execute().get('items', [])

    for ev in existing_events:
        ev_start = ev['start'].get('dateTime')
        if not ev_start:
            continue
        ev_dt = datetime.fromisoformat(ev_start).astimezone(IST)
        if ev_dt == start_time:
            return

    attendees = [{'email': e} for e in (attendee_emails or []) if e]

    event = {
        'summary': 'AI Scheduled Meeting',
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end':   {'dateTime': end_time.isoformat(),   'timeZone': 'Asia/Kolkata'},
        'attendees': attendees,
    }

    return service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates='all' if attendees else 'none'
    ).execute()

# =========================
# 📅 DAY SLOTS (FIXED)
# =========================

def get_day_slots(service, selected_date):

    start_of_day = IST.localize(datetime.combine(selected_date, datetime.min.time()).replace(hour=9))
    end_of_day   = IST.localize(datetime.combine(selected_date, datetime.min.time()).replace(hour=18))

    events = service.events().list(
        calendarId='primary',
        timeMin=start_of_day.isoformat(),
        timeMax=end_of_day.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute().get('items', [])

    busy_ranges = []

    for event in events:

        summary = event.get("summary", "").lower()

        # 🔥 ignore AI created events
        if "ai scheduled meeting" in summary:
            continue

        s = event['start'].get('dateTime')
        e = event['end'].get('dateTime')

        # 🔥 ignore all-day events
        if not s or not e:
            continue

        start_dt = datetime.fromisoformat(s).astimezone(IST)
        end_dt   = datetime.fromisoformat(e).astimezone(IST)

        busy_ranges.append((start_dt, end_dt))

    slots = []
    current = start_of_day
    now = datetime.now(IST)

    while current < end_of_day:

        slot_end = current + timedelta(hours=1)

        is_past = current <= now

        is_busy = is_past or any(
            start < slot_end and end > current
            for start, end in busy_ranges
        )

        slots.append({
            "time": current.strftime("%H:%M"),
            "busy": is_busy
        })

        current += timedelta(hours=1)

    return slots

# =========================
# 💡 SUGGEST ALTERNATIVES
# =========================

def suggest_alternatives(start_time):
    suggestions = []
    start_time  = safe_localize(start_time)
    base        = start_time.replace(minute=0, second=0, microsecond=0)
    now         = datetime.now(IST)

    for day in range(0, 3):
        current_day = base + timedelta(days=day)
        for hour in range(9, 18):
            new_time = current_day.replace(hour=hour, minute=0, second=0)
            if new_time <= now:
                continue
            if new_time == base:
                continue
            if check_availability(new_time):
                suggestions.append({
                    "datetime": new_time.isoformat(),
                    "display":  new_time.strftime("%d %B %I:%M %p")
                })
            if len(suggestions) >= 5:
                return suggestions

    return suggestions

# =========================
# 👥 MULTI USER AVAILABILITY (UNCHANGED)
# =========================

def get_multi_user_availability(date, participants):
    service = get_service()
    start   = IST.localize(datetime.strptime(date, "%Y-%m-%d"))
    now     = datetime.now(IST)
    result  = {}

    for user in participants:
        user = user.strip()
        if not user:
            continue
        result[user] = []
        for h in range(9, 18):
            slot_start = start.replace(hour=h, minute=0)
            slot_end   = slot_start + timedelta(hours=1)

            if slot_start <= now:
                result[user].append({"hour": h, "status": "busy"})
                continue

            body = {
                "timeMin": slot_start.isoformat(),
                "timeMax": slot_end.isoformat(),
                "timeZone": "Asia/Kolkata",
                "items": [{"id": user}]
            }

            res  = service.freebusy().query(body=body).execute()
            busy = res["calendars"].get(user, {}).get("busy", [])

            result[user].append({
                "hour": h,
                "status": "busy" if busy else "free"
            })

    return result

# =========================
# 👥 COMMON SLOTS (UNCHANGED)
# =========================

def find_common_slots(date, participants):
    if not participants:
        return []

    data   = get_multi_user_availability(date, participants)
    common = []

    for hour in range(9, 18):
        idx = hour - 9

        if all(
            user in data and data[user][idx]["status"] == "free"
            for user in participants if user.strip()
        ):
            common.append(hour)

    return common

# =========================
# ⭐ BEST SLOT (UNCHANGED)
# =========================

def suggest_best_slot(common):
    if not common:
        return None

    preferred = [h for h in common if 11 <= h <= 14]

    return preferred[0] if preferred else common[0]