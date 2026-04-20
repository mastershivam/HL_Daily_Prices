from __future__ import annotations

from datetime import date
import logging
import locale
from pathlib import Path

from config import get_debug_mode, get_email_settings, get_push_settings
from html_summary import build_html_summary
from notifications import build_notification_subject, format_push_message, send_email_notification, send_push_notification
from persistence import load_previous_snapshot, update_daily_totals
from price_scraper import fetch_google_finance_quote
from pull_and_collate import create_data_frame


logger = logging.getLogger(__name__)


def configure_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def configure_locale() -> None:
    for loc in ("en_GB.UTF-8", "en_US.UTF-8", "C.UTF-8", "C"):
        try:
            locale.setlocale(locale.LC_ALL, loc)
            logger.debug("Locale set to %s", loc)
            return
        except locale.Error:
            continue
    logger.warning("Could not set locale, using system default")


def write_summary_files(html_summary: str, today_str: str, output_dir: str = "summaries") -> None:
    out_dir = Path(output_dir)
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"daily_summary-{today_str}.html").write_text(html_summary, encoding="utf-8")
    (out_dir / "latest.html").write_text(html_summary, encoding="utf-8")


def main() -> None:
    debug_mode = get_debug_mode()
    configure_logging(debug_mode)
    configure_locale()

    data = create_data_frame(debug=debug_mode)
    logger.debug("Final dataframe:\n%s", data)
    total = float(data["Total Holding Value"].sum())
    today_str = date.today().isoformat()

    update_daily_totals(data, total, today_str)
    previous_total, _ = load_previous_snapshot(today_str, data.index.tolist())
    elix_price_pence = None
    elix_change_pence = None
    elix_change_pct = None
    try:
        elix_quote = fetch_google_finance_quote(exchange="LON", ticker="ELIX")
        elix_price_pence = float(elix_quote["price_pence"])
        if elix_quote["change_pence"] is not None:
            elix_change_pence = float(elix_quote["change_pence"])
        if elix_quote["change_pct"] is not None:
            elix_change_pct = float(elix_quote["change_pct"])
    except Exception as exc:
        logger.warning("Could not fetch ELIX quote: %s", exc)

    html_summary = build_html_summary(
        data,
        total,
        today_str,
        elix_price_pence=elix_price_pence,
        elix_change_pence=elix_change_pence,
        elix_change_pct=elix_change_pct,
    )
    write_summary_files(html_summary, today_str)

    subject = build_notification_subject(today_str)
    push_message = format_push_message(
        total,
        previous_total,
        elix_price_pence=elix_price_pence,
        elix_change_pence=elix_change_pence,
        elix_change_pct=elix_change_pct,
    )

    send_push_notification(get_push_settings(), subject, push_message)
    send_email_notification(get_email_settings(), subject, html_summary)


if __name__ == "__main__":
    main()
