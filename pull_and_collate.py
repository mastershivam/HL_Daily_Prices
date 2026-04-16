import logging
from pathlib import Path

import pandas as pd

from price_scraper import price_scraper_fund
from utilities import convert_value_to_gbp, get_usd_gbp_rate, improved_normalise_key, infer_currency, parse_price_to_gbp


logger = logging.getLogger(__name__)
UNITS_PATH = Path("HL_Daily_Prices_Data") / "units.csv"


def load_units_dataframe(units_path: Path = UNITS_PATH) -> pd.DataFrame:
    units_df = pd.read_csv(units_path)
    units_df = units_df.dropna(how="all")

    if "fund" not in units_df.columns:
        raise ValueError("units.csv must contain a 'fund' column for matching.")

    missing_columns = [column for column in ("units", "url") if column not in units_df.columns]
    if missing_columns:
        raise ValueError(f"units.csv is missing required columns: {', '.join(missing_columns)}")

    units_df = units_df.dropna(subset=["fund", "units", "url"]).copy()
    units_df["key"] = units_df["fund"].apply(improved_normalise_key)
    return units_df


def scrape_fund_rows(units_df: pd.DataFrame, debug: bool = False) -> list[dict[str, object]]:
    temp_data: list[dict[str, object]] = []

    if debug:
        logger.debug("Processing %s funds from units.csv", len(units_df))
        logger.debug("Funds: %s", units_df["fund"].tolist())

    for index, row in units_df.iterrows():
        fund_name = row["fund"]
        url = row["url"]
        try:
            if debug:
                logger.debug("Scraping %s/%s: %s", index + 1, len(units_df), fund_name)
            data = price_scraper_fund(url)
            if debug:
                logger.debug("Scrape result for %s: %s", fund_name, data)
            if not isinstance(data, dict) or "title" not in data or not data["title"]:
                logger.warning("Failed to scrape %s - no title found", fund_name)
                continue
            data["key"] = improved_normalise_key(data["title"])
            data["url"] = url
            data["fund_name"] = fund_name
            temp_data.append(data)
        except Exception as exc:
            logger.warning("Error scraping %s (%s): %s", fund_name, url, exc)
            continue

    if not temp_data:
        raise ValueError("No funds were successfully scraped. Check your URLs and network connection.")

    if debug:
        logger.debug("Successfully scraped %s out of %s funds", len(temp_data), len(units_df))

    return temp_data


def normalise_merged_dataframe(merged_data_df: pd.DataFrame) -> pd.DataFrame:
    merged_data_df = merged_data_df.copy()
    merged_data_df["currency"] = merged_data_df["sell"].map(infer_currency)
    share_mask = merged_data_df.index.str.contains("share", case=False)
    merged_data_df["sell"] = [
        parse_price_to_gbp(price, is_share=is_share)
        for price, is_share in zip(merged_data_df["sell"], share_mask)
    ]
    merged_data_df["value"] = merged_data_df["units"] * merged_data_df["sell"]

    usd_gbp_rate = get_usd_gbp_rate()
    merged_data_df["value"] = [
        convert_value_to_gbp(value, currency, usd_gbp_rate)
        for value, currency in zip(merged_data_df["value"], merged_data_df["currency"])
    ]
    merged_data_df.loc[merged_data_df["currency"] == "USD", "currency"] = "GBP"

    return merged_data_df.drop(columns=["title"])


def create_data_frame(debug: bool = False) -> pd.DataFrame:
    units_df = load_units_dataframe()
    scraped_rows = scrape_fund_rows(units_df, debug=debug)

    fund_data_df = pd.DataFrame(scraped_rows).set_index("url")
    merged_data_df = units_df.set_index("url").join(fund_data_df, how="left", rsuffix="_src")

    if "fund" in merged_data_df.columns:
        merged_data_df = merged_data_df.set_index("fund")

    failed_funds = merged_data_df[merged_data_df["title"].isna()]
    if not failed_funds.empty:
        logger.warning("%s funds failed to scrape and will be excluded", len(failed_funds))
        for fund in failed_funds.index:
            logger.warning("Excluded fund: %s", fund)

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
    return merged_data_df
