#!/usr/bin/env python
"""Record an investment top-up without hand-editing units.csv.

    python invest.py --seed
        One-time: turn your current units.csv into opening-balance
        transactions in transactions.csv. Run this once before using
        the commands below.

    python invest.py "Baillie Gifford Japanese" --amount 500
        Fetches the live price, works out how many units that buys,
        appends a transaction, and regenerates units.csv.

    python invest.py "Baillie Gifford Japanese" --units 12.34 --price 40.52
        Record an exact fill (e.g. from your HL contract note) instead of
        using the live scraped price.

The fund must already have a row in units.csv (fund,units,url[,type]) so
invest.py knows which URL/ticker to price it against.
"""
from __future__ import annotations

import argparse

import pandas as pd

from price_scraper import fetch_share_quote, price_scraper_fund
from transactions import (
    append_transaction,
    resolve_transactions_path,
    resolve_units_path,
    seed_transactions_from_units,
    sync_units_csv_from_transactions,
)
from utilities import parse_price_to_gbp


def _lookup_fund(fund_name: str) -> tuple[str, str]:
    units_path = resolve_units_path()
    if not units_path.exists():
        raise SystemExit(f"No units.csv found at {units_path}.")
    units_df = pd.read_csv(units_path)
    match = units_df[units_df["fund"].str.strip().str.lower() == fund_name.strip().lower()]
    if match.empty:
        raise SystemExit(
            f"'{fund_name}' not found in {units_path}. "
            "Add it there first (fund,units,url[,type]) so invest.py knows which URL/ticker to price it against."
        )
    row = match.iloc[0]
    row_type = str(row["type"]).strip().lower() if "type" in row and pd.notna(row["type"]) else "fund"
    return row["url"], row_type or "fund"


def _live_price_gbp(url: str, row_type: str) -> float:
    if row_type == "share":
        quote = fetch_share_quote(url)
        return quote["price_pence"] / 100.0
    scraped = price_scraper_fund(url)
    if not scraped.get("sell"):
        raise SystemExit(f"Could not fetch a live price from {url}; pass --price to record it manually.")
    return parse_price_to_gbp(scraped["sell"], is_share=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an investment top-up as a transaction.")
    parser.add_argument("fund", nargs="?", help="Fund name exactly as it appears in units.csv")
    parser.add_argument("--amount", type=float, help="Amount invested, in GBP")
    parser.add_argument("--units", type=float, help="Units bought (alternative to --amount)")
    parser.add_argument("--price", type=float, help="Price paid per unit in GBP (skips the live price fetch)")
    parser.add_argument("--date", help="Transaction date, YYYY-MM-DD (defaults to today)")
    parser.add_argument("--note", default="", help="Optional note")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="One-time: create transactions.csv from the current units.csv",
    )
    args = parser.parse_args()

    if args.seed:
        seeded = seed_transactions_from_units()
        print(f"Seeded {len(seeded)} opening transaction(s) into {resolve_transactions_path()}")
        return

    if not args.fund:
        parser.error("fund name is required unless --seed is used")
    if args.amount is None and args.units is None:
        parser.error("provide --amount or --units")

    url, row_type = _lookup_fund(args.fund)

    price = args.price if args.price is not None else _live_price_gbp(url, row_type)
    units = args.units if args.units is not None else round(args.amount / price, 4)
    amount = args.amount if args.amount is not None else units * price

    append_transaction(
        fund=args.fund,
        url=url,
        units=units,
        price_gbp=price,
        amount_gbp=amount,
        txn_date=args.date,
        note=args.note,
    )
    sync_units_csv_from_transactions()
    print(f"Recorded {units:.4f} units of '{args.fund}' @ £{price:.4f} (£{amount:.2f}). units.csv updated.")


if __name__ == "__main__":
    main()
