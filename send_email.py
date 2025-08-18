from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
import os 

def env(name):
    v = os.getenv(name, "")
    return v.strip() if isinstance(v, str) else v
load_dotenv()

# Map envs robustly: support both your local names and GitHub Secrets names
SMTP_HOST = env('SMTP_HOST')
SMTP_PORT = int(env('SMTP_PORT') or "587")
SMTP_USER = env('SMTP_USER') or env('EMAIL_ADDRESS')          # login username
SMTP_PASS = env('SMTP_PASS') or env('EMAIL_APP_PASSWORD')     # app password
EMAIL_FROM = env('EMAIL_FROM') or SMTP_USER or env('EMAIL_ADDRESS')
# Accept comma/space separated recipients
_rcpts = env('EMAIL_TO') or env('EMAIL_RECIPIENTS')
RECIPIENTS = [r.strip() for r in (_rcpts.split(',') if _rcpts else []) if r.strip()]


def assert_env():
    missing = [n for n, v in {
        "SMTP_HOST": SMTP_HOST,
        "SMTP_PORT": SMTP_PORT,
        "SMTP_USER": SMTP_USER,
        "SMTP_PASS": SMTP_PASS,
        "EMAIL_FROM": EMAIL_FROM,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Missing SMTP env vars: {', '.join(missing)}")

def maybe_send_email(subject: str, html_body: str):
    """
    Send the summary via HTML email if SMTP vars are set.
    Supports either:
      - SMTP_* envs (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO)
      - GitHub secrets mapping (EMAIL_ADDRESS, EMAIL_APP_PASSWORD, EMAIL_RECIPIENTS)
    """
    assert_env()
    if not RECIPIENTS:
        # If no recipients provided, default to sending to the sender
        RECIPIENTS.append(EMAIL_FROM)

    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(RECIPIENTS)

    with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT)) as s:
        s.ehlo()
        s.starttls()
        s.ehlo()
        s.login(SMTP_USER, SMTP_PASS)  # Use SMTP_USER/PASS for auth
        s.send_message(msg)