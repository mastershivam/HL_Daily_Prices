from __future__ import annotations

from datetime import date
import logging
import locale
from pathlib import Path

from config import get_debug_mode, get_email_settings, get_push_settings, get_watchlist_tickers
from html_summary import build_html_summary
from notifications import build_notification_subject, format_push_message, send_email_notification, send_push_notification
from persistence import load_history_totals, load_previous_snapshot, update_daily_totals
from price_scraper import fetch_share_quote
from pull_and_collate import create_data_frame
from regular_investments import apply_regular_investments, apply_to_dataframe, update_daily_prices
from transactions import compute_positions, load_transactions


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


def fetch_watchlist_quotes(tickers: tuple[str, ...]) -> list[dict]:
    """Fetch reference-ticker quotes to show alongside the portfolio total.
    These aren't holdings (no units are tracked for them) and don't affect
    the total - previously this was a single ticker ("ELIX.L") hardcoded
    here; any number can now be configured via WATCHLIST_TICKERS."""
    quotes = []
    for ticker in tickers:
        try:
            quote = fetch_share_quote(ticker)
            quotes.append(
                {
                    "symbol": ticker,
                    "price_pence": float(quote["price_pence"]),
                    "change_pence": float(quote["change_pence"]) if quote["change_pence"] is not None else None,
                    "change_pct": float(quote["change_pct"]) if quote["change_pct"] is not None else None,
                }
            )
        except Exception as exc:
            logger.warning("Could not fetch watchlist quote for %s: %s", ticker, exc)
    return quotes


def _cost_basis_by_fund() -> dict[str, float]:
    try:
        transactions = load_transactions()
        positions = compute_positions(transactions)
    except Exception as exc:
        logger.warning("Could not load transactions.csv for cost-basis tracking: %s", exc)
        return {}
    return {
        row["fund"]: row["cost_basis_gbp"]
        for _, row in positions.iterrows()
        if row["cost_basis_known"]
    }


def _run(debug_mode: bool, push_settings) -> None:
    data, failed_funds = create_data_frame(debug=debug_mode)
    logger.debug("Final dataframe:\n%s", data)
    today_str = date.today().isoformat()

    # Record any regular (direct-debit) buys that have dealt since the last
    # run, so units.csv keeps up with HL without hand-editing. A problem
    # here (e.g. a typo in investment_plan.csv) must never stop the daily
    # summary - it's reported in the push instead.
    regular_investments: list[dict] = []
    plan_error: str | None = None
    try:
        regular_investments = apply_regular_investments(data)
        if regular_investments:
            data = apply_to_dataframe(data, regular_investments)
    except Exception as exc:
        logger.exception("Could not apply regular investments")
        plan_error = str(exc)

    total = float(data["Total Holding Value"].sum())

    update_daily_totals(data, total, today_str)
    try:
        update_daily_prices(data, today_str)
    except Exception:
        logger.exception("Could not update daily_prices.csv")
    previous_total, previous_by_fund = load_previous_snapshot(today_str, data.index.tolist())

    # If funds vanished from history and different ones appeared in the same
    # run, it's very likely a fund was renamed by hand in units.csv rather
    # than actually sold - that silently orphans its history column.
    if previous_by_fund:
        vanished = set(previous_by_fund.keys()) - set(data.index)
        appeared = set(data.index) - set(previous_by_fund.keys())
        if vanished and appeared:
            logger.warning(
                "Possible fund rename detected - %s no longer appear, %s are new. "
                "If you renamed a fund in units.csv, its history was NOT carried over; "
                "use `python rename_fund.py \"old name\" \"new name\"` instead next time.",
                sorted(vanished),
                sorted(appeared),
            )

    history_totals = load_history_totals()
    cost_basis_by_fund = _cost_basis_by_fund()
    watchlist_quotes = fetch_watchlist_quotes(get_watchlist_tickers())

    html_summary = build_html_summary(
        data,
        total,
        today_str,
        previous_total=previous_total,
        previous_by_fund=previous_by_fund,
        watchlist_quotes=watchlist_quotes,
        failed_funds=failed_funds,
        history_totals=history_totals,
        cost_basis_by_fund=cost_basis_by_fund,
        regular_investments=regular_investments,
        plan_error=plan_error,
    )
    write_summary_files(html_summary, today_str)

    subject = build_notification_subject(today_str)
    push_message = format_push_message(
        total,
        previous_total,
        watchlist_quotes=watchlist_quotes,
        failed_funds=failed_funds,
        regular_investments=regular_investments,
        plan_error=plan_error,
    )

    send_push_notification(push_settings, subject, push_message)
    send_email_notification(get_email_settings(), subject, html_summary)


def main() -> None:
    debug_mode = get_debug_mode()
    configure_logging(debug_mode)
    configure_locale()
    push_settings = get_push_settings()

    try:
        _run(debug_mode, push_settings)
    except Exception as exc:
        # Previously a failed run just... didn't happen, with no signal
        # beyond checking GitHub Actions. Now you get told about it.
        logger.exception("Daily portfolio run failed")
        try:
            send_push_notification(
                push_settings,
                "Portfolio update FAILED",
                f"The daily run failed and no summary was produced: {exc}",
            )
        except Exception:
            logger.exception("Also failed to send the failure notification")
        raise


if __name__ == "__main__":
    main()
