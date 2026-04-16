from config import get_email_settings
from notifications import send_email_notification


def maybe_send_email(subject: str, html_body: str) -> None:
    send_email_notification(get_email_settings(), subject, html_body)
