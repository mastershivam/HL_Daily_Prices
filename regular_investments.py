"""Automatically record regular (direct-debit) investments.

HL invests a monthly direct debit on a fixed day (the 10th, or the next
working day). Previously every one of those buys had to be added to
units.csv by hand, and any month you forgot made the daily total quietly
drift below what HL shows.

Now you describe the plan once in investment_plan.csv (in the private data
repo, next to units.csv):

    fund,monthly_amount_gbp,day_of_month,start_month
    BlackRock Continental European Income,300,10,2026-09
    Landseer Global Artificial Intelligence,150,10,2026-09
    Vanguard FTSE Global All Cap,300,10,2026-09

- fund: enough of the name in units.csv to identify one fund uniquely
  (case-insensitive) - no need to paste HL's full "...Class D - Accumulation
  (GBP)" name.
- monthly_amount_gbp: change this number when you increase/decrease your
  direct debit. Past months already recorded keep the amount they were
  recorded with; the new amount applies from the next dealing date. Set it
  to 0 (or delete the row) to pause/stop.
- day_of_month: HL dealing day, default 10. Weekends roll to the Monday.
- start_month: YYYY-MM of the first month to record. Months before this are
  never touched, so adding a new fund row doesn't backfill its whole history.

Each daily run (main.py) records any dealing date that has passed but isn't
in transactions.csv yet, using the fund price on the first run after that
date, then regenerates units.csv. Recording is idempotent per fund+month
(note "regular investment YYYY-MM"), so re-runs never double count.

One-off lump sums are still recorded with `python invest.py "Fund" --amount`.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from config import get_data_dir
from persistence import resolve_history_path
from transactions import (
    append_transaction,
    load_transactions,
    resolve_transactions_path,
    resolve_units_path,
    seed_transactions_from_units,
    sync_units_csv_from_transactions,
)


logger = logging.getLogger(__name__)

NOTE_PREFIX = "regular investment"
OPENING_BALANCE_PREFIX = "opening balance"
DEFAULT_DAY_OF_MONTH = 10


def resolve_plan_path() -> Path:
    data_dir = get_data_dir()
    if data_dir is not None:
        return data_dir / "investment_plan.csv"
    return Path("investment_plan.csv")


def resolve_prices_path() -> Path:
    data_dir = get_data_dir()
    if data_dir is not None:
        return data_dir / "outputs" / "daily_prices.csv"
    return Path("daily_prices.csv")


# ---------------------------------------------------------------- plan file

def load_plan(path: Path | None = None) -> pd.DataFrame:
    path = path or resolve_plan_path()
    columns = ["fund", "monthly_amount_gbp", "day_of_month", "start_month"]
    if not path.exists():
        return pd.DataFrame(columns=columns)

    plan = pd.read_csv(path, dtype=str).dropna(how="all")
    plan.columns = [c.strip().lower() for c in plan.columns]
    missing = [c for c in ("fund", "monthly_amount_gbp", "start_month") if c not in plan.columns]
    if missing:
        raise ValueError(f"{path.name} is missing column(s): {', '.join(missing)}")
    if "day_of_month" not in plan.columns:
        plan["day_of_month"] = str(DEFAULT_DAY_OF_MONTH)

    plan["fund"] = plan["fund"].astype(str).str.strip()
    amounts = pd.to_numeric(plan["monthly_amount_gbp"].astype(str).str.replace("£", "").str.replace(",", ""), errors="coerce")
    if amounts.isna().any() or (amounts < 0).any():
        bad = plan.loc[amounts.isna() | (amounts < 0), "fund"].tolist()
        raise ValueError(f"{path.name}: monthly_amount_gbp must be a number >= 0 for: {', '.join(bad)}")
    plan["monthly_amount_gbp"] = amounts

    days = pd.to_numeric(plan["day_of_month"].fillna(str(DEFAULT_DAY_OF_MONTH)), errors="coerce")
    if days.isna().any() or (days < 1).any() or (days > 31).any():
        raise ValueError(f"{path.name}: day_of_month must be between 1 and 31")
    plan["day_of_month"] = days.astype(int)

    for value in plan["start_month"]:
        _parse_month(value, path.name)

    duplicated = plan.loc[plan["fund"].str.casefold().duplicated(), "fund"].tolist()
    if duplicated:
        raise ValueError(f"{path.name} lists the same fund more than once: {', '.join(duplicated)}")
    return plan[columns]


def _parse_month(value: object, source: str = "investment_plan.csv") -> tuple[int, int]:
    try:
        year_str, month_str = str(value).strip().split("-")
        year, month = int(year_str), int(month_str)
        if not 1 <= month <= 12:
            raise ValueError
        return year, month
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"{source}: start_month must look like 2026-09, got {value!r}") from exc


def match_fund(name: str, fund_names: list[str]) -> str:
    """Resolve a short, human-friendly plan name to the exact units.csv
    fund name. Exact match wins; otherwise the plan name must be a
    case-insensitive substring of exactly one fund."""
    if name in fund_names:
        return name
    needle = " ".join(name.casefold().split())
    hits = [f for f in fund_names if needle in " ".join(str(f).casefold().split())]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise ValueError(f"investment_plan.csv fund {name!r} doesn't match any fund in units.csv")
    raise ValueError(f"investment_plan.csv fund {name!r} is ambiguous - matches: {', '.join(hits)}")


# ------------------------------------------------------------ dealing dates

def dealing_date(year: int, month: int, day: int) -> date:
    """HL deals on the given day, or the next weekday if it falls on a
    weekend. (Bank holidays aren't modelled - they shift the price by at
    most a day, which the next screenshot sync would true up.)"""
    d = date(year, month, min(day, calendar.monthrange(year, month)[1]))
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def due_dealings(start_month: str, day: int, today: date) -> list[tuple[str, date]]:
    """Every (YYYY-MM, dealing date) from start_month up to today whose
    dealing date is strictly before today - i.e. a run has had the chance to
    see that day's fund price."""
    year, month = _parse_month(start_month)
    due = []
    while (year, month) <= (today.year, today.month):
        d = dealing_date(year, month, day)
        if d < today:
            due.append((f"{year:04d}-{month:02d}", d))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return due


# ------------------------------------------------------------------ prices

def update_daily_prices(data: pd.DataFrame, today_str: str, path: Path | None = None) -> None:
    """Persist each holding's GBP unit price for the day (value / units, so
    USD shares are already FX-converted). This gives regular investments a
    real historical price to use if a run is late or a month is backfilled."""
    path = path or resolve_prices_path()
    prices = (data["Total Holding Value"] / data["Units"]).to_dict()
    row = {"Date": today_str, **prices}
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        history = pd.read_csv(path)
        history = history[history["Date"].astype(str) != today_str]
        history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    else:
        history = pd.DataFrame([row])
    history.to_csv(path, index=False)


def _first_value_after(path: Path, fund: str, after: date) -> float | None:
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "Date" not in df.columns or fund not in df.columns:
        return None
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df[fund] = pd.to_numeric(df[fund], errors="coerce")
    df = df[(df["Date"] > pd.Timestamp(after)) & df[fund].notna()].sort_values("Date")
    return None if df.empty else float(df[fund].iloc[0])


def _units_held_on(fund: str, on: date, transactions: pd.DataFrame) -> float:
    """Units held at `on`: today's total minus anything bought after `on`
    (opening-balance rows are excluded - their date is just when tracking
    started, not when the units were bought)."""
    rows = transactions[transactions["fund"] == fund]
    units = pd.to_numeric(rows["units"], errors="coerce").fillna(0)
    total = float(units.sum())
    dates = pd.to_datetime(rows["date"], errors="coerce")
    notes = rows["note"].fillna("").astype(str)
    later = (dates > pd.Timestamp(on)) & ~notes.str.startswith(OPENING_BALANCE_PREFIX)
    return total - float(units[later].sum())


def lookup_price(
    fund: str,
    deal: date,
    transactions: pd.DataFrame,
    live_price: float | None,
    prices_path: Path | None = None,
    history_path: Path | None = None,
) -> tuple[float | None, str]:
    """Price for a buy on `deal`, from (best first):
    1. daily_prices.csv - first run after the dealing date.
    2. daily_totals.csv value / units held then (for history recorded before
       daily_prices.csv existed, e.g. backfilling a missed month).
    3. today's live price - approximate, only used if neither history exists.
    """
    price = _first_value_after(prices_path or resolve_prices_path(), fund, deal)
    if price:
        return price, "price history"

    value = _first_value_after(history_path or resolve_history_path(), fund, deal)
    if value:
        units_then = _units_held_on(fund, deal, transactions)
        if units_then > 0:
            return value / units_then, "value history"

    if live_price:
        return live_price, "live price (approximate)"
    return None, "no price"


# ------------------------------------------------------------- the main hook

def apply_regular_investments(
    data: pd.DataFrame,
    today: date | None = None,
    plan_path: Path | None = None,
    units_path: Path | None = None,
    transactions_path: Path | None = None,
    prices_path: Path | None = None,
    history_path: Path | None = None,
) -> list[dict]:
    """Record any due-but-unrecorded plan buys. Returns one dict per buy
    recorded this run (empty list if nothing was due)."""
    today = today or date.today()
    plan = load_plan(plan_path)
    plan = plan[plan["monthly_amount_gbp"] > 0]
    if plan.empty:
        return []

    units_path = units_path or resolve_units_path()
    transactions_path = transactions_path or resolve_transactions_path()
    if not transactions_path.exists():
        # units.csv is regenerated from transactions.csv below, so the log
        # must start from the current holdings or they'd be wiped.
        logger.info("No transactions.csv yet - seeding it from units.csv")
        seed_transactions_from_units(units_path, transactions_path, seed_date=today.isoformat())

    units_df = pd.read_csv(units_path)
    fund_names = units_df["fund"].tolist()
    url_by_fund = dict(zip(units_df["fund"], units_df["url"]))

    live_prices: dict[str, float] = {}
    if data is not None and not data.empty:
        live_prices = (data["Total Holding Value"] / data["Units"]).to_dict()

    # Resolve every name before writing anything, so one typo can't leave a
    # half-applied month.
    resolved = [(match_fund(row["fund"], fund_names), row) for _, row in plan.iterrows()]

    recorded: list[dict] = []
    for fund, row in resolved:
        for month_key, deal in due_dealings(row["start_month"], int(row["day_of_month"]), today):
            note_key = f"{NOTE_PREFIX} {month_key}"
            transactions = load_transactions(transactions_path)
            existing_notes = transactions.loc[transactions["fund"] == fund, "note"].fillna("").astype(str)
            if existing_notes.str.startswith(note_key).any():
                continue

            price, source = lookup_price(
                fund, deal, transactions, live_prices.get(fund), prices_path=prices_path, history_path=history_path
            )
            if not price:
                logger.warning("No price available for %s %s - will retry next run", fund, month_key)
                continue

            amount = float(row["monthly_amount_gbp"])
            units = amount / price
            note = note_key if source == "price history" else f"{note_key} [{source}]"
            append_transaction(
                fund=fund,
                url=url_by_fund.get(fund),
                units=round(units, 4),
                price_gbp=price,
                amount_gbp=amount,
                txn_date=deal.isoformat(),
                note=note,
                path=transactions_path,
            )
            recorded.append(
                {
                    "fund": fund,
                    "label": row["fund"],
                    "month": month_key,
                    "date": deal.isoformat(),
                    "amount_gbp": amount,
                    "units": round(units, 4),
                    "price_gbp": price,
                    "price_source": source,
                }
            )
            logger.info("Recorded %s: £%.2f into %s (%.4f units @ £%.4f, %s)", note_key, amount, fund, units, price, source)

    if recorded:
        sync_units_csv_from_transactions(units_path=units_path, transactions_path=transactions_path)
    return recorded


def apply_to_dataframe(data: pd.DataFrame, recorded: list[dict]) -> pd.DataFrame:
    """Reflect newly recorded units in today's already-priced dataframe,
    valued at today's price, so the total includes them without re-scraping."""
    data = data.copy()
    for buy in recorded:
        fund = buy["fund"]
        if fund not in data.index:
            continue
        old_units = float(data.at[fund, "Units"])
        unit_value = float(data.at[fund, "Total Holding Value"]) / old_units if old_units else buy["price_gbp"]
        data.at[fund, "Units"] = old_units + buy["units"]
        data.at[fund, "Total Holding Value"] = float(data.at[fund, "Total Holding Value"]) + buy["units"] * unit_value
    return data


if __name__ == "__main__":
    # Dry run: show the plan and which months are due/recorded, without
    # pricing or writing anything.
    plan = load_plan()
    if plan.empty:
        print(f"No plan found at {resolve_plan_path()}")
    else:
        fund_names = pd.read_csv(resolve_units_path())["fund"].tolist()
        txns = load_transactions()
        for _, row in plan.iterrows():
            fund = match_fund(row["fund"], fund_names)
            print(f"{row['fund']} -> {fund}: £{row['monthly_amount_gbp']:.2f} on day {row['day_of_month']}")
            notes = txns.loc[txns["fund"] == fund, "note"].fillna("").astype(str)
            for month_key, deal in due_dealings(row["start_month"], int(row["day_of_month"]), date.today()):
                done = notes.str.startswith(f"{NOTE_PREFIX} {month_key}").any()
                print(f"   {month_key} (dealt {deal}): {'recorded' if done else 'DUE - will be recorded on next run'}")
