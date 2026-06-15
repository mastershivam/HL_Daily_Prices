from __future__ import annotations

import re
import requests
from bs4 import BeautifulSoup


def fetch_fund_html(url: str) -> str:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.text


def parse_fund_html(html: str) -> dict[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")

    price_pattern = r"([$£]?[0-9,]+\.\d{2}p?)"
    text = soup.get_text(" ", strip=True)

    sell = re.search(rf"Sell:\s*{price_pattern}", text)
    buy = re.search(rf"Buy:\s*{price_pattern}", text)
    chg = re.search(r"Change:\s*([+\-]?\d+(?:\.\d+)?p?)\s*\(\s*([-+]?[\d\.]+%)\s*\)", text)

    title = None
    og = soup.select_one('meta[property="og:title"]')
    if og and og.get("content"):
        title = og["content"].strip()
    if not title:
        h1 = soup.select_one("h1")
        if h1:
            title = h1.get_text(strip=True)
    if not title and soup.title:
        title = soup.title.get_text(strip=True)

    return {
        "title": title,
        "sell": sell.group(1) if sell else None,
        "buy": buy.group(1) if buy else None,
        "change_value": chg.group(1) if chg else None,
        "change_pct": chg.group(2) if chg else None,
    }


def price_scraper_fund(url: str) -> dict[str, str | None]:
    return parse_fund_html(fetch_fund_html(url))


def fetch_share_quote(yahoo_symbol: str) -> dict[str, str | float | None]:
    """Fetch a listed share quote via yfinance, normalised to pence.

    LSE quotes are usually reported in GBp (pence); a feed reporting GBP
    (pounds) is scaled up by 100 so the rest of the app can assume pence.
    yfinance is imported lazily so the rest of the module stays usable
    (and testable) without the dependency installed.
    """
    import yfinance as yf

    fast_info = yf.Ticker(yahoo_symbol).fast_info
    last_price = fast_info.get("lastPrice")
    previous_close = fast_info.get("previousClose")
    currency = fast_info.get("currency") or ""

    if last_price is None:
        raise ValueError(f"Could not fetch latest price for {yahoo_symbol}")

    scale = 100.0 if currency == "GBP" else 1.0  # GBp/GBX are already pence
    price_pence = float(last_price) * scale

    change_pence = None
    change_pct = None
    if previous_close:
        previous_pence = float(previous_close) * scale
        change_pence = price_pence - previous_pence
        if previous_pence:
            change_pct = (change_pence / previous_pence) * 100.0

    return {
        "symbol": yahoo_symbol,
        "price_pence": price_pence,
        "change_pence": change_pence,
        "change_pct": change_pct,
    }
