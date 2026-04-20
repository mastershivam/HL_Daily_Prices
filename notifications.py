from __future__ import annotations

from email.mime.text import MIMEText
import logging
import smtplib

import requests

from config import EmailSettings, PushSettings


logger = logging.getLogger(__name__)


def build_notification_subject(today_str: str) -> str:
    return f"Daily Portfolio Summary - {today_str}"


def format_push_message(
    total: float,
    previous_total: float | None,
    elix_price_pence: float | None = None,
    elix_change_pence: float | None = None,
    elix_change_pct: float | None = None,
) -> str:
    message = f"Portfolio total: GBP {total:,.2f}"
    if previous_total is None:
        base_message = message
    else:
        diff = total - previous_total
        if previous_total == 0:
            base_message = f"{message} ({diff:+,.2f})"
        else:
            pct = (diff / previous_total) * 100.0
            base_message = f"{message} ({diff:+,.2f}, {pct:+.2f}%)"

    if elix_price_pence is None:
        return base_message

    change_text = ""
    if elix_change_pence is not None:
        change_text = f" ({elix_change_pence:+.2f}p DoD"
        if elix_change_pct is not None:
            change_text += f", {elix_change_pct:+.2f}%"
        change_text += ")"
    elif elix_change_pct is not None:
        change_text = f" ({elix_change_pct:+.2f}% DoD)"
    return f"{base_message}\nLON:ELIX: {elix_price_pence:.2f}p{change_text}"


def send_push_notification(settings: PushSettings, subject: str, message: str, click_url: str | None = None) -> None:
    if not settings.enabled:
        logger.debug("Push notification skipped because no topic is configured")
        return

    headers = {
        "Title": subject,
        "Priority": "default",
        "Tags": "chart_with_upwards_trend",
    }
    if click_url:
        headers["Click"] = click_url
    if settings.token:
        headers["Authorization"] = f"Bearer {settings.token}"

    response = requests.post(
        f"{settings.base_url.rstrip('/')}/{settings.topic}",
        data=message.encode("utf-8"),
        headers=headers,
        timeout=15,
    )
    response.raise_for_status()


def send_email_notification(settings: EmailSettings, subject: str, html_body: str) -> None:
    if not settings.enabled:
        logger.debug("Email notification skipped because SMTP is not configured")
        return

    missing = [
        name
        for name, value in {
            "SMTP_HOST": settings.host,
            "SMTP_PORT": settings.port,
            "SMTP_USER": settings.user,
            "SMTP_PASS": settings.password,
            "EMAIL_FROM": settings.sender,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing SMTP env vars: {', '.join(missing)}")

    recipients = list(settings.recipients) if settings.recipients else [settings.sender]
    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.sender
    msg["To"] = ", ".join(recipients)

    with smtplib.SMTP(settings.host, int(settings.port)) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(settings.user, settings.password)
        smtp.send_message(msg)
