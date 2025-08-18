import re
import requests
from bs4 import BeautifulSoup

def price_scraper_fund(url):
    
    html = requests.get(url, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    price_pattern = r"([$£]?[0-9,]+\.\d{2}p?)"
    text = soup.get_text(" ", strip=True)
    
    sell = re.search(rf"Sell:\s*{price_pattern}", text)
    buy  = re.search(rf"Buy:\s*{price_pattern}", text)
    chg  = re.search(r"Change:\s*([+\-]?\d+(?:\.\d+)?p?)\s*\(([-+]?[\d\.]+%)\)", text)

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
        "buy":  buy.group(1) if buy else None,
        "change_value": chg.group(1) if chg else None,
        "change_pct":   chg.group(2) if chg else None,
    }