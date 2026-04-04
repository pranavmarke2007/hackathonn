EMAIL="pranavmarke66@gmail.com"
PASSWORD ="mkysvbcebkcpxgzr"
from datetime import time

# Working hours per weekday (0=Mon, 6=Sun)
WORKING_HOURS = {
    0: (time(9, 0), time(18, 0)),   # Monday
    1: (time(9, 0), time(18, 0)),
    2: (time(9, 0), time(18, 0)),
    3: (time(9, 0), time(18, 0)),
    4: (time(9, 0), time(17, 0)),   # Friday ends earlier
    5: None,                         # Saturday — off
    6: None,                         # Sunday — off
}

# VIP senders get priority (their requests checked first, best slots offered)
VIP_SENDERS = [
    "ceo@company.com",
    "founder@startup.io",
]

# Ambiguous phrases that need a clarifying reply
AMBIGUOUS_PHRASES = [
    "sometime", "whenever", "flexible", "any time", "anytime",
    "next week", "soon", "morning", "afternoon", "evening"
]

DEFAULT_TIMEZONE = "Asia/Kolkata"
MEETING_DURATION_HOURS = 1