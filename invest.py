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

    python invest.py --sync-from-image holdings.png
        Reconcile units.csv against a screenshot of your HL holdings page
        using local OCR - no login automation, no Claude/cloud call, no
        credentials stored anywhere. Prints a preview by default; add
        --apply to actually write the changes. Cost basis for any top-up
        found this way is left unknown (OCR gives units, not price paid) -
        use the --amount/--units form above for accurate cost tracking.

The fund must already have a row in units.csv (fund,units,url[,type]) so
invest.py knows which URL/ticker to price it against.
"""
from __future__ import annotations

import argparse

import pandas as pd

from price_scraper import fetch_share_quote, price_scraper_fund
from transactions import (
    append_transaction,
    apply_reconciliation,
    reconcile_holdings,
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


def _sync_from_image(image_path: str, apply_changes: bool, cutoff: float) -> None:
    from holdings_ocr import parse_holdings_from_words, run_ocr

    units_path = resolve_units_path()
    if not units_path.exists():
        raise SystemExit(f"No units.csv found at {units_path}.")
    if apply_changes and not resolve_transactions_path().exists():
        raise SystemExit(
            f"{resolve_transactions_path()} doesn't exist yet. units.csv is always derived by summing "
            "transactions.csv, so applying a reconciliation now would reset units to just the screenshot "
            "delta rather than adding to what you already hold. Run `python invest.py --seed` once first."
        )
    known_funds = pd.read_csv(units_path)["fund"].tolist()
    if not known_funds:
        raise SystemExit(f"{units_path} has no funds yet - add them there first so there's something to match against.")

    try:
        words = run_ocr(image_path)
    except ImportError as exc:
        raise SystemExit(
            "OCR dependencies aren't installed. Run: pip install pytesseract pillow, "
            "and make sure the tesseract binary is installed too (e.g. `brew install tesseract`)."
        ) from exc
    except FileNotFoundError as exc:
        raise SystemExit(f"Couldn't open image file: {image_path}") from exc
    except Exception as exc:
        raise SystemExit(
            f"OCR failed on {image_path}: {exc}\n"
            "If this is about the 'tesseract' binary, install it separately from the pytesseract "
            "python package (e.g. `brew install tesseract` on macOS)."
        ) from exc

    holdings = parse_holdings_from_words(words, known_funds, cutoff=cutoff)
    if not holdings:
        raise SystemExit(
            "Couldn't confidently match any fund in that screenshot. "
            "Try a clearer/cropped screenshot of just the holdings table, or lower --match-cutoff."
        )

    changes = reconcile_holdings(holdings)
    print(changes.to_string(index=False))

    unmatched = sorted(set(known_funds) - set(holdings))
    if unmatched:
        print(f"\nNot found in screenshot (left unchanged): {', '.join(unmatched)}")

    unchanged = changes[changes["delta"].abs() < 1e-6]
    if len(unchanged) == len(changes):
        print("\nNo differences found - units.csv already matches the screenshot.")
        return

    if not apply_changes:
        print("\nDry run only - rerun with --apply to write these changes.")
        return

    applied = apply_reconciliation(changes)
    print(f"\nApplied changes for: {', '.join(applied)}. units.csv updated.")
    print("Note: cost basis for these top-ups is left unknown (OCR gives units, not price paid).")


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
    parser.add_argument(
        "--sync-from-image",
        metavar="PATH",
        help="Reconcile units.csv against a screenshot of your HL holdings page via local OCR",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="With --sync-from-image, actually write the reconciled changes (default is a preview only)",
    )
    parser.add_argument(
        "--match-cutoff",
        type=float,
        default=0.6,
        help="With --sync-from-image, fuzzy fund-name match threshold, 0-1 (default 0.6)",
    )
    args = parser.parse_args()

    if args.seed:
        seeded = seed_transactions_from_units()
        print(f"Seeded {len(seeded)} opening transaction(s) into {resolve_transactions_path()}")
        return

    if args.sync_from_image:
        _sync_from_image(args.sync_from_image, apply_changes=args.apply, cutoff=args.match_cutoff)
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
