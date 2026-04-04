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
# 🔧 SAFE LOCALIZE
# =========================

def safe_localize(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return IST.localize(dt)
    return dt.astimezone(IST)


# =========================
# ✅ CHECK AVAILABILITY
# =========================

def check_availability(start_time):
    """
    Check if the logged-in user's primary calendar is free at start_time.

    ✅ FIX 1: Reject slots in the past — the Google Calendar API returns no
    conflicts for past times (they're gone), so without this guard a past slot
    would incorrectly appear free and get booked.

    ✅ FIX 2: Reject slots outside working hours (before 9 AM or at/after 6 PM).

    ✅ FIX 3: Handle all-day events — they use a 'date' field, not 'dateTime'.
    The old code skipped them entirely, leaving those days looking free.
    """
    try:
        service    = get_service()
        start_time = safe_localize(start_time)
        end_time   = start_time + timedelta(hours=1)
        now        = datetime.now(IST)

        # Reject past slots
        if start_time <= now:
            return False

        # Reject outside working hours
        if start_time.hour < 9 or start_time.hour >= 18:
            return False

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
                # ✅ FIX 3: All-day event — check if it falls on the same day
                s_date = event['start'].get('date')
                if s_date:
                    event_day = datetime.strptime(s_date, "%Y-%m-%d").date()
                    if start_time.date() == event_day:
                        return False
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
# 📅 CREATE EVENT
# =========================

def create_event(start_time, attendee_emails=None):
    """
    Create a 1-hour calendar event.

    ✅ FIX: Duplicate guard — before inserting, check whether an event already
    exists that starts at the exact same minute. If so, skip creation silently.
    This is the last-line defence against double-booking in case the MongoDB
    guard in app.py is bypassed (e.g. race condition or manual DB wipe).

    ✅ FIX: Only send calendar invites (sendUpdates='all') when there are real
    attendees. Sending with no attendees is a wasted API call and can produce
    empty invite emails.
    """
    service    = get_service()
    start_time = safe_localize(start_time)
    end_time   = start_time + timedelta(hours=1)

    # ── Duplicate guard ──────────────────────────────────────────────────────
    existing_events = service.events().list(
        calendarId='primary',
        timeMin=start_time.isoformat(),
        timeMax=end_time.isoformat(),
        singleEvents=True
    ).execute().get('items', [])

    for ev in existing_events:
        ev_start_str = ev['start'].get('dateTime')
        if not ev_start_str:
            continue
        ev_start_dt = datetime.fromisoformat(ev_start_str).astimezone(IST)
        if ev_start_dt == start_time:
            print(f"create_event: duplicate at {start_time} — skipping.")
            return
    # ─────────────────────────────────────────────────────────────────────────

    attendees = [{'email': e} for e in (attendee_emails or []) if e]

    event = {
        'summary': 'AI Scheduled Meeting',
        'start': {'dateTime': start_time.isoformat(), 'timeZone': 'Asia/Kolkata'},
        'end':   {'dateTime': end_time.isoformat(),   'timeZone': 'Asia/Kolkata'},
        'attendees': attendees,
    }

    created = service.events().insert(
        calendarId='primary',
        body=event,
        sendUpdates='all' if attendees else 'none'
    ).execute()

    print(f"create_event: created '{created.get('summary')}' at {start_time}")


# =========================
# 📅 DAY SLOTS
# =========================

def get_day_slots(date_str):
    """
    Return hourly slots 9 AM–6 PM for date_str, marking each free or busy.

    ✅ FIX: Past slots on today are marked busy so they show as red and cannot
    be clicked. Previously they appeared green because the Calendar API returns
    no events for times that have already passed.
    """
    service      = get_service()
    start_of_day = IST.localize(datetime.strptime(date_str, "%Y-%m-%d"))
    end_of_day   = start_of_day + timedelta(days=1)
    now          = datetime.now(IST)

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
            # All-day event → mark entire working day busy
            s_date = event['start'].get('date')
            if s_date:
                busy_ranges.append((
                    start_of_day.replace(hour=9,  minute=0),
                    start_of_day.replace(hour=18, minute=0)
                ))
            continue

        start = datetime.fromisoformat(s).astimezone(IST)
        end   = datetime.fromisoformat(e).astimezone(IST)
        busy_ranges.append((start, end))

    slots   = []
    current = start_of_day.replace(hour=9, minute=0, second=0, microsecond=0)

    while current.hour < 18:
        slot_end = current + timedelta(hours=1)

        # ✅ FIX: past slots on today → always busy
        is_past = (current <= now)

        is_busy = is_past or any(
            current < b_end and slot_end > b_start
            for b_start, b_end in busy_ranges
        )

        slots.append({
            "display": current.strftime("%I %p"),   # e.g. "11 AM"
            "time":    current.isoformat(),          # ISO string for booking
            "hour":    current.hour,
            "status":  "busy" if is_busy else "free"
        })

        current = slot_end

    return slots


# =========================
# 💡 SUGGEST ALTERNATIVES
# =========================

def suggest_alternatives(start_time):
    """
    Suggest up to 5 free future slots within 3 days of start_time.
    Working hours only (9 AM–6 PM). Skips the originally requested slot.
    """
    suggestions = []
    start_time  = safe_localize(start_time)
    base        = start_time.replace(minute=0, second=0, microsecond=0)
    now         = datetime.now(IST)

    for day in range(0, 3):
        current_day = base + timedelta(days=day)

        for hour in range(9, 18):
            new_time = current_day.replace(hour=hour, minute=0, second=0, microsecond=0)

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
# 👥 MULTI-USER AVAILABILITY
# =========================

def get_multi_user_availability(date, participants):
    """
    Query each participant's calendar via the FreeBusy API.
    Shared calendars for pranavmarke66 and only71951 have already been granted
    to hackathondemo6, so their IDs work directly as calendarId values.

    ✅ FIX: Past slots are always marked busy without querying the API.
    This prevents find_common_slots from suggesting a time that has already passed.
    """
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
            slot_start = start.replace(hour=h, minute=0, second=0, microsecond=0)
            slot_end   = slot_start + timedelta(hours=1)

            # ✅ FIX: past slots are always busy — skip the API call entirely
            if slot_start <= now:
                result[user].append({"hour": h, "status": "busy"})
                continue

            try:
                body = {
                    "timeMin":  slot_start.isoformat(),
                    "timeMax":  slot_end.isoformat(),
                    "timeZone": "Asia/Kolkata",
                    "items":    [{"id": user}]
                }
                res    = service.freebusy().query(body=body).execute()
                busy   = res["calendars"].get(user, {}).get("busy", [])
                status = "busy" if busy else "free"

            except Exception as ex:
                print(f"freebusy error for {user} at {h}:00 → {ex}")
                # Cannot read their calendar → treat as free (don't silently block slot)
                status = "free"

            result[user].append({"hour": h, "status": status})

    return result


# =========================
# 👥 FIND COMMON FREE SLOTS
# =========================

def find_common_slots(date, participants):
    """
    Return list of hours (9–17) where ALL participants are free.
    Because hackathondemo6 is included in participants by app.py, the host's
    own calendar is automatically checked via FreeBusy as well.
    """
    if not participants:
        return []

    data   = get_multi_user_availability(date, participants)
    common = []

    for hour in range(9, 18):
        idx      = hour - 9
        all_free = True

        for user in participants:
            user = user.strip()
            if not user or user not in data:
                continue
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
    """
    Pick the best hour from the common free slots.
    Prefers mid-morning to early afternoon (11 AM–2 PM),
    otherwise falls back to the earliest available hour.
    """
    if not common:
        return None
    preferred = [h for h in common if 11 <= h <= 14]
    return preferred[0] if preferred else common[0]