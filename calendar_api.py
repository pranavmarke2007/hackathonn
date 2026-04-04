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
    Also checks that the slot is in the future and within working hours (9–18 IST).
    """
    try:
        service = get_service()
        start_time = safe_localize(start_time)
        end_time = start_time + timedelta(hours=1)

        # ✅ FIX: reject slots in the past
        now = datetime.now(IST)
        if start_time <= now:
            return False

        # ✅ FIX: reject slots outside working hours
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

            # ✅ FIX: handle all-day events — they have 'date' not 'dateTime'
            if not s or not e:
                s_date = event['start'].get('date')
                if s_date:
                    # All-day event on same day → slot is busy
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
    ✅ FIX: skip duplicate creation — if an 'AI Scheduled Meeting' already
    exists at this exact slot, do not create another one.
    """
    service    = get_service()
    start_time = safe_localize(start_time)
    end_time   = start_time + timedelta(hours=1)

    # ── Duplicate guard ──────────────────────────────────────────
    existing = service.events().list(
        calendarId='primary',
        timeMin=start_time.isoformat(),
        timeMax=end_time.isoformat(),
        singleEvents=True
    ).execute().get('items', [])

    for ev in existing:
        ev_start = ev['start'].get('dateTime')
        if not ev_start:
            continue
        ev_start_dt = datetime.fromisoformat(ev_start).astimezone(IST)
        # If any existing event starts at the exact same minute → skip
        if ev_start_dt == start_time:
            print(f"create_event: duplicate detected at {start_time}, skipping.")
            return
    # ─────────────────────────────────────────────────────────────

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
        sendUpdates='all' if attendees else 'none'   # ✅ FIX: don't send emails if no attendees
    ).execute()

    print(f"create_event: created '{created.get('summary')}' at {start_time}")


# =========================
# 📅 DAY SLOTS
# =========================

def get_day_slots(date_str):
    """
    Return hourly slots 9 AM–6 PM for date_str, marking each as busy or free.
    ✅ FIX: past slots on today are marked busy so they can't be booked.
    """
    service = get_service()

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
            # All-day event → mark whole working day busy
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

        # ✅ FIX: mark past slots as busy so they show red and can't be booked
        is_past = current <= now

        is_busy = is_past or any(
            current < b_end and slot_end > b_start
            for b_start, b_end in busy_ranges
        )

        slots.append({
            "display": current.strftime("%I %p"),   # e.g. "11 AM"
            "time":    current.isoformat(),          # for booking
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
    Suggest up to 5 free future slots near start_time.
    ✅ FIX: also excludes slots outside working hours explicitly.
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
# (uses shared calendars already added to hackathondemo6 account)
# =========================

def get_multi_user_availability(date, participants):
    """
    Query each participant's calendar via the FreeBusy API.
    Works because hackathondemo6 has been granted access to
    pranavmarke66 and only71951 shared calendars.

    ✅ FIX: past slots are always marked busy so find_common_slots
    never picks an already-passed hour for the team meeting.
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

            # ✅ FIX: past slots are always busy — don't even query the API
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
                # Can't read their calendar → assume free (don't block the slot)
                status = "free"

            result[user].append({"hour": h, "status": status})

    return result


# =========================
# 👥 FIND COMMON FREE SLOTS
# =========================

def find_common_slots(date, participants):
    """
    Return list of hours where ALL participants are free.
    ✅ FIX: also excludes hours that are already busy on the host's own
    calendar, so the booked slot is always actually free for the organiser.
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
    Pick the best hour from common free slots.
    Prefers 11 AM–2 PM (inclusive), otherwise takes the earliest available.
    """
    if not common:
        return None
    preferred = [h for h in common if 11 <= h <= 14]
    return preferred[0] if preferred else common[0]