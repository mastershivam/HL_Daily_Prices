"""Transaction log for investments, so units.csv no longer has to be
hand-edited every time you top up a fund.

units.csv still holds the *current* position (fund, units, url[, type]) and
is what pull_and_collate.py reads each run - that hasn't changed. What's new
is transactions.csv, an append-only log of buys (date, fund, units,
price paid, amount). units.csv is now a derived view: `invest.py` appends a
transaction and then regenerates units.csv from the full transaction history,
so the units figure is always a sum of real purchases rather than a number
someone has to remember to bump. This also gives us a real cost basis per
fund, which a bare units count can never provide.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from config import get_data_dir


DEFAULT_UNITS_PATH = Path("units.csv")
DEFAULT_TRANSACTIONS_PATH = Path("transactions.csv")

TRANSACTION_COLUMNS = ["date", "fund", "url", "units", "price_gbp", "amount_gbp", "note"]


def resolve_units_path() -> Path:
    # Mirrors persistence.resolve_history_path: prefer the private data-repo
    # copy whenever it can be found (see config.get_data_dir), so local dev
    # and CI automation read/write the same file.
    data_dir = get_data_dir()
    if data_dir is not None:
        return data_dir / "units.csv"
    return DEFAULT_UNITS_PATH


def resolve_transactions_path() -> Path:
    data_dir = get_data_dir()
    if data_dir is not None:
        return data_dir / "transactions.csv"
    return DEFAULT_TRANSACTIONS_PATH


def load_transactions(path: Path | None = None) -> pd.DataFrame:
    path = path or resolve_transactions_path()
    if not path.exists():
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    df = pd.read_csv(path)
    for col in TRANSACTION_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
    return df[TRANSACTION_COLUMNS]


def append_transaction(
    fund: str,
    url: str | None,
    units: float,
    price_gbp: float | None = None,
    amount_gbp: float | None = None,
    txn_date: str | None = None,
    note: str = "",
    path: Path | None = None,
) -> pd.DataFrame:
    if price_gbp is None and amount_gbp is not None and units:
        price_gbp = amount_gbp / units
    if amount_gbp is None and price_gbp is not None:
        amount_gbp = price_gbp * units

    path = path or resolve_transactions_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    row = {
        "date": txn_date or date.today().isoformat(),
        "fund": fund,
        "url": url,
        "units": units,
        "price_gbp": price_gbp,
        "amount_gbp": amount_gbp,
        "note": note,
    }

    existing = load_transactions(path)
    new_row_df = pd.DataFrame([row], columns=TRANSACTION_COLUMNS)
    updated = new_row_df if existing.empty else pd.concat([existing, new_row_df], ignore_index=True)
    updated.to_csv(path, index=False)
    return updated


def compute_positions(transactions: pd.DataFrame) -> pd.DataFrame:
    """Aggregate the transaction log into current units + cost basis per fund.

    cost_basis_known is False whenever any transaction for that fund has no
    recorded amount (e.g. an opening balance migrated from a units.csv that
    had no purchase history) - in that case we deliberately don't report a
    (misleadingly partial) cost basis figure at all.
    """
    columns = ["fund", "units", "url", "cost_basis_gbp", "cost_basis_known"]
    if transactions.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for fund, group in transactions.groupby("fund", sort=False):
        units = pd.to_numeric(group["units"], errors="coerce").fillna(0).sum()
        amounts = pd.to_numeric(group["amount_gbp"], errors="coerce")
        cost_basis_known = bool(amounts.notna().all()) and len(group) > 0
        cost_basis = float(amounts.sum()) if cost_basis_known else None
        url = None
        known_urls = group["url"].dropna()
        if not known_urls.empty:
            url = known_urls.iloc[-1]
        rows.append(
            {
                "fund": fund,
                "units": units,
                "url": url,
                "cost_basis_gbp": cost_basis,
                "cost_basis_known": cost_basis_known,
            }
        )
    return pd.DataFrame(rows, columns=columns)


def sync_units_csv_from_transactions(
    transactions: pd.DataFrame | None = None,
    units_path: Path | None = None,
    transactions_path: Path | None = None,
) -> pd.DataFrame:
    """Rebuild units.csv from the transaction log, preserving the 'type'
    (fund/share) column of any existing rows since transactions don't track
    that."""
    transactions = transactions if transactions is not None else load_transactions(transactions_path)
    positions = compute_positions(transactions)
    positions = positions[positions["units"] > 0]

    units_path = units_path or resolve_units_path()
    type_by_fund: dict[str, str] = {}
    if units_path.exists():
        existing_units = pd.read_csv(units_path)
        if "type" in existing_units.columns:
            type_by_fund = dict(zip(existing_units["fund"], existing_units["type"]))

    out_rows = [
        {
            "fund": row["fund"],
            "units": round(float(row["units"]), 6),  # avoid float noise like 14.104700000000001
            "url": row["url"],
            "type": type_by_fund.get(row["fund"], "fund"),
        }
        for _, row in positions.iterrows()
    ]
    out_df = pd.DataFrame(out_rows, columns=["fund", "units", "url", "type"])
    units_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(units_path, index=False)
    return out_df


def reconcile_holdings(screenshot_holdings: dict[str, float], units_path: Path | None = None) -> pd.DataFrame:
    """Compare OCR'd screenshot holdings against the current units.csv
    position. Returns the proposed per-fund changes for review - this never
    writes anything itself, so a bad OCR read can be caught before it
    touches your data."""
    units_path = units_path or resolve_units_path()
    current = pd.read_csv(units_path) if units_path.exists() else pd.DataFrame(columns=["fund", "units", "url", "type"])
    current_units = dict(zip(current["fund"], current["units"]))

    rows = [
        {
            "fund": fund,
            "current_units": float(current_units.get(fund, 0.0)),
            "screenshot_units": screenshot_units,
            "delta": round(screenshot_units - float(current_units.get(fund, 0.0)), 4),
        }
        for fund, screenshot_units in screenshot_holdings.items()
    ]
    return pd.DataFrame(rows, columns=["fund", "current_units", "screenshot_units", "delta"])


def apply_reconciliation(
    changes: pd.DataFrame,
    note: str = "reconciled from holdings screenshot (OCR)",
    txn_date: str | None = None,
    units_path: Path | None = None,
) -> list[str]:
    """Append a transaction for every non-zero delta in `changes` (as
    produced by reconcile_holdings) and rebuild units.csv from the result.

    Price/amount are deliberately left unknown: OCR gives us a units figure,
    not what was actually paid, so cost-basis tracking for these top-ups is
    marked unknown rather than guessed. Use `invest.py "Fund" --amount ...`
    instead for a transaction where you want accurate cost-basis tracking.
    """
    units_path = units_path or resolve_units_path()
    existing = pd.read_csv(units_path) if units_path.exists() else pd.DataFrame(columns=["fund", "url"])
    url_by_fund = dict(zip(existing["fund"], existing["url"])) if "url" in existing.columns else {}

    applied = []
    for _, row in changes.iterrows():
        if abs(row["delta"]) < 1e-6:
            continue
        append_transaction(
            fund=row["fund"],
            url=url_by_fund.get(row["fund"]),
            units=row["delta"],
            txn_date=txn_date,
            note=note,
        )
        applied.append(row["fund"])

    if applied:
        sync_units_csv_from_transactions(units_path=units_path)
    return applied


def seed_transactions_from_units(
    units_path: Path | None = None,
    transactions_path: Path | None = None,
    seed_date: str | None = None,
) -> pd.DataFrame:
    """One-time migration: turn an existing hand-maintained units.csv into an
    opening-balance transaction per fund. Cost basis is left unknown for
    these rows (price paid before tracking started isn't recoverable) -
    P&L tracking simply starts from whenever this migration is run."""
    units_path = units_path or resolve_units_path()
    transactions_path = transactions_path or resolve_transactions_path()

    if transactions_path.exists():
        raise FileExistsError(
            f"{transactions_path} already exists; refusing to overwrite. "
            "Delete it first if you really want to reseed from units.csv."
        )
    if not units_path.exists():
        raise FileNotFoundError(f"No units.csv found at {units_path} to seed from.")

    units_df = pd.read_csv(units_path)
    seed_date = seed_date or date.today().isoformat()

    rows = [
        {
            "date": seed_date,
            "fund": row["fund"],
            "url": row.get("url"),
            "units": row["units"],
            "price_gbp": None,
            "amount_gbp": None,
            "note": "opening balance (migrated from units.csv, cost basis unknown)",
        }
        for _, row in units_df.iterrows()
    ]
    seeded = pd.DataFrame(rows, columns=TRANSACTION_COLUMNS)
    transactions_path.parent.mkdir(parents=True, exist_ok=True)
    seeded.to_csv(transactions_path, index=False)
    return seeded
