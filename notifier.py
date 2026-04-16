from config import get_push_settings
from notifications import send_push_notification


def maybe_send_push(subject: str, message: str, click_url: str | None = None) -> None:
    send_push_notification(get_push_settings(), subject, message, click_url=click_url)
