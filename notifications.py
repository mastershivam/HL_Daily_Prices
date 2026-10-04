from __future__ import annotations

from email.mime.text import MIMEText
import logging
import smtplib

import requests

from config import EmailSettings, PushSettings


logger = logging.getLogger(__name__)


def build_notification_subject(today_str: str) -> str:
    return f"Daily Portfolio Summary - {today_str}"


def _format_watchlist_line(quote: dict) -> str:
    symbol = quote.get("symbol")
    price_pence = quote.get("price_pence")
    change_pence = quote.get("change_pence")
    change_pct = quote.get("change_pct")

    change_text = ""
    if change_pence is not None:
        change_text = f" ({change_pence:+.2f}p DoD"
        if change_pct is not None:
            change_text += f", {change_pct:+.2f}%"
        change_text += ")"
    elif change_pct is not None:
        change_text = f" ({change_pct:+.2f}% DoD)"
    return f"LON:{symbol}: {price_pence:.2f}p{change_text}"


def format_push_message(
    total: float,
    previous_total: float | None,
    elix_price_pence: float | None = None,
    elix_change_pence: float | None = None,
    elix_change_pct: float | None = None,
    watchlist_quotes: list[dict] | None = None,
    failed_funds: list[str] | None = None,
    regular_investments: list[dict] | None = None,
    plan_error: str | None = None,
) -> str:
    message = f"Portfolio total: GBP {total:,.2f}"
    invested_today = sum(float(b["amount_gbp"]) for b in (regular_investments or []))
    if previous_total is None:
        base_message = message
    else:
        # Money paid in isn't performance - strip it out of the DoD move.
        diff = total - previous_total - invested_today
        if previous_total == 0:
            base_message = f"{message} ({diff:+,.2f})"
        else:
            pct = (diff / previous_total) * 100.0
            base_message = f"{message} ({diff:+,.2f}, {pct:+.2f}%)"
        if invested_today:
            base_message += f" excl. GBP {invested_today:,.2f} invested"

    lines = [base_message]

    # Back-compat: a caller can still pass the old single-ticker params.
    quotes = list(watchlist_quotes) if watchlist_quotes else []
    if not quotes and elix_price_pence is not None:
        quotes = [
            {
                "symbol": "ELIX",
                "price_pence": elix_price_pence,
                "change_pence": elix_change_pence,
                "change_pct": elix_change_pct,
            }
        ]
    for quote in quotes:
        lines.append(_format_watchlist_line(quote))

    if regular_investments:
        parts = ", ".join(f"{b['label']} {b['amount_gbp']:,.0f} ({b['month']})" for b in regular_investments)
        lines.append(f"💷 Recorded regular investment: GBP {invested_today:,.2f} - {parts}")
        if any("approximate" in b.get("price_source", "") for b in regular_investments):
            lines.append("⚠ Some buys used today's price (no history for the dealing date) - units are approximate")
    if plan_error:
        lines.append(f"⚠ Regular investments not applied: {plan_error}")

    if failed_funds:
        lines.append(f"⚠ Could not price {len(failed_funds)} holding(s): {', '.join(failed_funds)}")

    return "\n".join(lines)


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
