import logging
from pathlib import Path

import pandas as pd

from price_scraper import fetch_share_quote, price_scraper_fund
from transactions import resolve_units_path
from utilities import convert_value_to_gbp, get_fx_rate_to_gbp, improved_normalise_key, infer_currency, infer_is_share, parse_price_to_gbp


logger = logging.getLogger(__name__)
# Historically this was a fixed Path("HL_Daily_Prices_Data") / "units.csv",
# which meant a local run failed unless that directory existed even though a
# plain units.csv already sat in the repo root. resolve_units_path() prefers
# the private data-repo copy when present (automation) and falls back to the
# local units.csv otherwise, resolved fresh on every call rather than once
# at import time.
VALID_TYPES = {"fund", "share"}


def load_units_dataframe(units_path: Path | None = None) -> pd.DataFrame:
    units_path = units_path or resolve_units_path()
    units_df = pd.read_csv(units_path)
    units_df = units_df.dropna(how="all")

    if "fund" not in units_df.columns:
        raise ValueError("units.csv must contain a 'fund' column for matching.")

    missing_columns = [column for column in ("units", "url") if column not in units_df.columns]
    if missing_columns:
        raise ValueError(f"units.csv is missing required columns: {', '.join(missing_columns)}")

    units_df = units_df.dropna(subset=["fund", "units", "url"]).copy()

    duplicate_funds = units_df.loc[units_df["fund"].duplicated(), "fund"].unique().tolist()
    if duplicate_funds:
        raise ValueError(
            f"units.csv has duplicate fund name(s), which would silently double-count value: {', '.join(duplicate_funds)}"
        )

    numeric_units = pd.to_numeric(units_df["units"], errors="coerce")
    if numeric_units.isna().any() or (numeric_units <= 0).any():
        bad_rows = units_df.loc[numeric_units.isna() | (numeric_units <= 0), "fund"].tolist()
        raise ValueError(f"units.csv has zero, negative, or non-numeric units for: {', '.join(bad_rows)}")

    if "type" in units_df.columns:
        row_types = units_df["type"].dropna().astype(str).str.strip().str.lower()
        bad_types = set(row_types) - VALID_TYPES
        if bad_types:
            raise ValueError(f"units.csv 'type' column must be 'fund' or 'share', found: {', '.join(sorted(bad_types))}")
    else:
        units_df["type"] = "fund"

    units_df["key"] = units_df["fund"].apply(improved_normalise_key)
    return units_df


def _scrape_share_row(yahoo_symbol: str) -> dict[str, str | None]:
    """Adapt a yfinance quote into the same shape price_scraper_fund
    returns, so share rows (type='share') flow through the rest of the
    pipeline identically to HL-scraped funds. This is the generalised
    replacement for a single hardcoded reference ticker: any row in
    units.csv can now be priced via yfinance instead of HL scraping."""
    quote = fetch_share_quote(yahoo_symbol)
    sell_pounds = quote["price_pence"] / 100.0

    change_value = None
    change_pct = None
    if quote["change_pence"] is not None:
        change_value = f"{quote['change_pence'] / 100.0:+.4f}"
    if quote["change_pct"] is not None:
        change_pct = f"{quote['change_pct']:+.2f}%"

    return {
        "title": yahoo_symbol,
        "sell": f"£{sell_pounds:.4f}",
        "buy": None,
        "change_value": change_value,
        "change_pct": change_pct,
    }


def scrape_fund_rows(units_df: pd.DataFrame, debug: bool = False) -> tuple[list[dict[str, object]], list[str]]:
    temp_data: list[dict[str, object]] = []
    failed_funds: list[str] = []

    if debug:
        logger.debug("Processing %s funds from units.csv", len(units_df))
        logger.debug("Funds: %s", units_df["fund"].tolist())

    for index, row in units_df.iterrows():
        fund_name = row["fund"]
        url = row["url"]
        row_type = str(row.get("type") or "fund").strip().lower()
        try:
            if debug:
                logger.debug("Scraping %s/%s: %s (%s)", index + 1, len(units_df), fund_name, row_type)
            data = _scrape_share_row(url) if row_type == "share" else price_scraper_fund(url)
            if debug:
                logger.debug("Scrape result for %s: %s", fund_name, data)
            if not isinstance(data, dict) or "title" not in data or not data["title"]:
                logger.warning("Failed to scrape %s - no title found", fund_name)
                failed_funds.append(str(fund_name))
                continue
            data["key"] = improved_normalise_key(data["title"])
            data["url"] = url
            data["fund_name"] = fund_name
            data["type"] = row_type
            temp_data.append(data)
        except Exception as exc:
            logger.warning("Error scraping %s (%s): %s", fund_name, url, exc)
            failed_funds.append(str(fund_name))
            continue

    if not temp_data:
        raise ValueError("No funds were successfully scraped. Check your URLs and network connection.")

    if debug:
        logger.debug("Successfully scraped %s out of %s funds", len(temp_data), len(units_df))

    return temp_data, failed_funds


def normalise_merged_dataframe(merged_data_df: pd.DataFrame) -> pd.DataFrame:
    merged_data_df = merged_data_df.copy()
    merged_data_df["currency"] = merged_data_df["sell"].map(infer_currency)

    row_types = merged_data_df["type"] if "type" in merged_data_df.columns else [None] * len(merged_data_df)
    urls = merged_data_df["url"] if "url" in merged_data_df.columns else [None] * len(merged_data_df)
    share_mask = [
        infer_is_share(row_type, url, name)
        for row_type, url, name in zip(row_types, urls, merged_data_df.index)
    ]

    merged_data_df["sell"] = [
        parse_price_to_gbp(price, is_share=is_share)
        for price, is_share in zip(merged_data_df["sell"], share_mask)
    ]
    merged_data_df["value"] = merged_data_df["units"] * merged_data_df["sell"]

    # Only hit the FX API for currencies actually present - previously a USD
    # rate was fetched on every single run even for an all-GBP portfolio.
    needed_currencies = sorted(set(merged_data_df["currency"]) - {"GBP"})
    fx_rates = {currency: get_fx_rate_to_gbp(currency) for currency in needed_currencies}
    merged_data_df["value"] = [
        convert_value_to_gbp(value, currency, fx_rates.get(currency, 1.0))
        for value, currency in zip(merged_data_df["value"], merged_data_df["currency"])
    ]
    merged_data_df.loc[merged_data_df["currency"] != "GBP", "currency"] = "GBP"

    return merged_data_df.drop(columns=["title"])


def create_data_frame(debug: bool = False) -> tuple[pd.DataFrame, list[str]]:
    units_df = load_units_dataframe()
    scraped_rows, failed_funds = scrape_fund_rows(units_df, debug=debug)

    fund_data_df = pd.DataFrame(scraped_rows).set_index("url")
    merged_data_df = units_df.set_index("url").join(fund_data_df, how="left", rsuffix="_src")

    if "fund" in merged_data_df.columns:
        merged_data_df = merged_data_df.set_index("fund")

    newly_failed = merged_data_df[merged_data_df["title"].isna()]
    if not newly_failed.empty:
        logger.warning("%s funds failed to scrape and will be excluded", len(newly_failed))
        for fund in newly_failed.index:
            logger.warning("Excluded fund: %s", fund)
            if fund not in failed_funds:
                failed_funds.append(str(fund))

    merged_data_df = merged_data_df.dropna(subset=["title", "sell"])
    if merged_data_df.empty:
        raise ValueError("No funds have valid scraped data. All scraping attempts failed.")

    merged_data_df = normalise_merged_dataframe(merged_data_df)
    merged_data_df = merged_data_df.rename(
        {
            "units": "Units",
            "sell": "Sell Price",
            "buy": "Buy Price",
            "change_value": "Change Value",
            "change_pct": "Percentage Change",
            "url": "URL",
            "currency": "Currency",
            "value": "Total Holding Value",
        },
        axis=1,
    )
    merged_data_df.index.name = "Fund/Share"
    return merged_data_df, failed_funds
