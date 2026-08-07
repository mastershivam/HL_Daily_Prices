import logging
import re
import time

import requests


logger = logging.getLogger(__name__)


def with_retries(fn, retries: int = 2, backoff: float = 1.0, exceptions: tuple = (Exception,)):
    """Call fn() with a small retry/backoff loop for transient failures.

    fn is retried up to `retries` extra times (so `retries + 1` attempts total).
    Sleeps `backoff * attempt_number` seconds between attempts. Re-raises the
    last exception if every attempt fails.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fn()
        except exceptions as exc:  # noqa: PERF203 - retry loop, not a hot path
            last_exc = exc
            if attempt < retries:
                sleep_for = backoff * (attempt + 1)
                logger.debug("Attempt %s failed (%s); retrying in %.1fs", attempt + 1, exc, sleep_for)
                time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc


def get_fx_rate_to_gbp(currency: str) -> float:
    """Fetch a spot FX rate converting 1 unit of `currency` into GBP."""
    if currency == "GBP":
        return 1.0

    def _fetch() -> float:
        response = requests.get(
            f"https://api.frankfurter.dev/v1/latest?base={currency}&symbols=GBP",
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        return float(data["rates"]["GBP"])

    return with_retries(_fetch, retries=2, backoff=1.0, exceptions=(requests.RequestException, KeyError, ValueError))


def get_usd_gbp_rate() -> float:
    """Backward-compatible alias for the common USD->GBP case."""
    return get_fx_rate_to_gbp("USD")


def improved_normalise_key(value: str) -> str:
    if value is None:
        return ""
    normalized = (
        str(value)
        .strip()
        .casefold()
        .replace(" & ", " and ")
        .replace("&", " and ")
        .replace("  ", " ")
        .replace("indexaccumulation", "index accumulation")
        .replace("indexdistribution", "index distribution")
    )
    return re.sub(r"([a-z])class", r"\1 class", normalized)


def parse_price_to_gbp(value: str, is_share: bool) -> float:
    cleaned = str(value).replace(",", "").replace("£", "").replace("$", "").replace("€", "").strip()
    if cleaned.endswith("p"):
        cleaned = cleaned[:-1]
    amount = float(cleaned)
    return amount if is_share else amount / 100.0


def infer_currency(value: str) -> str:
    text = str(value)
    if "€" in text:
        return "EUR"
    if "$" in text:
        return "USD"
    return "GBP"


def infer_is_share(row_type: str | None, url: str | None, fund_name: str) -> bool:
    """Decide whether a scraped price string is already a per-share price in
    pounds (True) rather than a fund price in pence (False).

    Priority order:
    1. An explicit 'type' column value of 'share' (most reliable).
    2. The URL path containing '/shares/' vs '/funds/' (HL's own URL scheme).
    3. Falls back to checking whether the fund name contains the word
       "share" - this is the old heuristic, kept only as a last resort
       because it misfires on funds like "iShares FTSE 100" that contain
       the substring "share" but are priced in pence like any other fund.
    """
    if row_type and str(row_type).strip().lower() == "share":
        return True

    url_text = str(url).lower() if url else ""
    if "/shares/" in url_text:
        return True
    if "/funds/" in url_text:
        return False

    return "share" in str(fund_name).lower()


def convert_value_to_gbp(value: float, currency: str, rate_to_gbp: float) -> float:
    if currency == "GBP":
        return value
    return value * rate_to_gbp
