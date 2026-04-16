from dotenv import load_dotenv
import os
import requests


def env(name: str) -> str:
    value = os.getenv(name, "")
    return value.strip() if isinstance(value, str) else value


load_dotenv()

NTFY_BASE_URL = env("NTFY_BASE_URL") or "https://ntfy.sh"
NTFY_TOPIC = env("NTFY_TOPIC")
NTFY_TOKEN = env("NTFY_TOKEN")


def maybe_send_push(subject: str, message: str, click_url: str | None = None) -> None:
    """
    Send a push notification via ntfy if NTFY_TOPIC is configured.
    """
    if not NTFY_TOPIC:
        return

    headers = {
        "Title": subject,
        "Priority": "default",
        "Tags": "chart_with_upwards_trend",
    }
    if click_url:
        headers["Click"] = click_url
    if NTFY_TOKEN:
        headers["Authorization"] = f"Bearer {NTFY_TOKEN}"

    response = requests.post(
        f"{NTFY_BASE_URL.rstrip('/')}/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()
