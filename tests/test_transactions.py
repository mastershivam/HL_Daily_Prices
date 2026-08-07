import pandas as pd
import pytest

import transactions


def test_append_transaction_derives_price_from_amount_and_units(tmp_path):
    path = tmp_path / "transactions.csv"
    transactions.append_transaction(
        fund="Fund A",
        url="https://example.com/fund-a",
        units=10.0,
        amount_gbp=100.0,
        txn_date="2026-01-01",
        path=path,
    )

    df = transactions.load_transactions(path)
    assert len(df) == 1
    assert df.loc[0, "price_gbp"] == 10.0
    assert df.loc[0, "amount_gbp"] == 100.0


def test_append_transaction_derives_amount_from_price_and_units(tmp_path):
    path = tmp_path / "transactions.csv"
    transactions.append_transaction(
        fund="Fund A",
        url="https://example.com/fund-a",
        units=4.0,
        price_gbp=25.0,
        txn_date="2026-01-01",
        path=path,
    )

    df = transactions.load_transactions(path)
    assert df.loc[0, "amount_gbp"] == 100.0


def test_compute_positions_sums_units_and_cost_basis_per_fund():
    df = pd.DataFrame(
        [
            {"date": "2026-01-01", "fund": "Fund A", "url": "u1", "units": 10, "price_gbp": 10.0, "amount_gbp": 100.0, "note": ""},
            {"date": "2026-02-01", "fund": "Fund A", "url": "u1", "units": 5, "price_gbp": 12.0, "amount_gbp": 60.0, "note": ""},
            {"date": "2026-01-01", "fund": "Fund B", "url": "u2", "units": 20, "price_gbp": 1.0, "amount_gbp": 20.0, "note": ""},
        ]
    )

    positions = transactions.compute_positions(df).set_index("fund")

    assert positions.loc["Fund A", "units"] == 15
    assert positions.loc["Fund A", "cost_basis_gbp"] == 160.0
    assert bool(positions.loc["Fund A", "cost_basis_known"]) is True
    assert positions.loc["Fund B", "units"] == 20


def test_compute_positions_marks_cost_basis_unknown_when_any_amount_missing():
    df = pd.DataFrame(
        [
            {"date": "2026-01-01", "fund": "Fund A", "url": "u1", "units": 100, "price_gbp": None, "amount_gbp": None, "note": "opening balance"},
            {"date": "2026-02-01", "fund": "Fund A", "url": "u1", "units": 5, "price_gbp": 12.0, "amount_gbp": 60.0, "note": ""},
        ]
    )

    positions = transactions.compute_positions(df).set_index("fund")

    assert positions.loc["Fund A", "units"] == 105
    assert bool(positions.loc["Fund A", "cost_basis_known"]) is False
    assert pd.isna(positions.loc["Fund A", "cost_basis_gbp"])


def test_sync_units_csv_from_transactions_writes_current_positions_and_drops_closed(tmp_path):
    transactions_df = pd.DataFrame(
        [
            {"date": "2026-01-01", "fund": "Fund A", "url": "u1", "units": 10, "price_gbp": 10.0, "amount_gbp": 100.0, "note": ""},
            {"date": "2026-01-01", "fund": "Fund B", "url": "u2", "units": 5, "price_gbp": 2.0, "amount_gbp": 10.0, "note": ""},
            {"date": "2026-02-01", "fund": "Fund B", "url": "u2", "units": -5, "price_gbp": 3.0, "amount_gbp": -15.0, "note": "sold"},
        ]
    )
    units_path = tmp_path / "units.csv"

    out = transactions.sync_units_csv_from_transactions(transactions_df, units_path=units_path)

    assert list(out["fund"]) == ["Fund A"]
    assert out.iloc[0]["units"] == 10
    assert units_path.exists()


def test_seed_transactions_from_units_creates_opening_balance_rows(tmp_path):
    units_path = tmp_path / "units.csv"
    pd.DataFrame([{"fund": "Fund A", "units": 100, "url": "https://example.com/a"}]).to_csv(units_path, index=False)
    transactions_path = tmp_path / "transactions.csv"

    seeded = transactions.seed_transactions_from_units(
        units_path=units_path, transactions_path=transactions_path, seed_date="2026-01-01"
    )

    assert len(seeded) == 1
    assert seeded.loc[0, "fund"] == "Fund A"
    assert seeded.loc[0, "units"] == 100
    assert pd.isna(seeded.loc[0, "amount_gbp"])
    assert transactions_path.exists()


def test_seed_transactions_from_units_refuses_to_overwrite_existing(tmp_path):
    units_path = tmp_path / "units.csv"
    pd.DataFrame([{"fund": "Fund A", "units": 100, "url": "https://example.com/a"}]).to_csv(units_path, index=False)
    transactions_path = tmp_path / "transactions.csv"
    transactions_path.write_text("date,fund,url,units,price_gbp,amount_gbp,note\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        transactions.seed_transactions_from_units(units_path=units_path, transactions_path=transactions_path)
