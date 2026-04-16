import logging
import re

import requests


logger = logging.getLogger(__name__)


def get_usd_gbp_rate() -> float:
    response = requests.get(
        "https://api.frankfurter.dev/v1/latest?base=USD&symbols=GBP",
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return float(data["rates"]["GBP"])


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
    cleaned = str(value).replace(",", "").replace("£", "").replace("$", "").strip()
    if cleaned.endswith("p"):
        cleaned = cleaned[:-1]
    amount = float(cleaned)
    return amount if is_share else amount / 100.0


def infer_currency(value: str) -> str:
    return "USD" if "$" in str(value) else "GBP"


def convert_value_to_gbp(value: float, currency: str, usd_gbp_rate: float) -> float:
    if currency == "USD":
        return value * usd_gbp_rate
    return value
