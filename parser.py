from datetime import datetime

def extract_time(text):
    try:
        return datetime.strptime(text.strip(), "%d %B %H:%M")
    except:
        return None