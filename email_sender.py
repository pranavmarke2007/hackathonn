import smtplib
from email.mime.text import MIMEText
from config import EMAIL, PASSWORD

def send_email(to, subject, body):

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL
    msg["To"] = to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL, PASSWORD)
        server.sendmail(EMAIL, to, msg.as_string())
        
        