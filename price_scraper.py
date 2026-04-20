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


def fetch_google_finance_quote(exchange: str, ticker: str) -> dict[str, str | float]:
    symbol = f"{ticker}:{exchange}"
    url = f"https://www.google.com/finance/quote/{ticker}:{exchange}"
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)
    normalized_text = re.sub(r"\s+", " ", text)

    price_match = re.search(rf"{re.escape(symbol)}\s*([0-9]+(?:\.[0-9]+)?)", normalized_text)
    change_match = re.search(r"([+\-][0-9]+(?:\.[0-9]+)?)\s*\(([+\-][0-9]+(?:\.[0-9]+)?)%\)", normalized_text)

    if not price_match:
        raise ValueError(f"Could not parse latest price for {symbol}")

    price = float(price_match.group(1))
    change_value = float(change_match.group(1)) if change_match else None
    change_pct = float(change_match.group(2)) if change_match else None

    return {
        "symbol": symbol,
        "price_pence": price,
        "change_pence": change_value,
        "change_pct": change_pct,
    }
