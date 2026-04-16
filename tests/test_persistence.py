from pathlib import Path

import pandas as pd

import persistence


def test_load_previous_snapshot_uses_latest_prior_row(tmp_path, monkeypatch):
    history_path = tmp_path / "daily_totals.csv"
    pd.DataFrame(
        [
            {"Date": "2026-04-14", "Total": 100.0, "Fund A": 60.0},
            {"Date": "2026-04-15", "Total": 110.0, "Fund A": 70.0},
            {"Date": "2026-04-16", "Total": 120.0, "Fund A": 80.0},
        ]
    ).to_csv(history_path, index=False)

    monkeypatch.setattr(persistence, "PRIVATE_HISTORY_PATH", tmp_path / "missing.csv")
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", history_path)

    previous_total, previous_by_fund = persistence.load_previous_snapshot("2026-04-16", ["Fund A"])
    assert previous_total == 110.0
    assert previous_by_fund == {"Fund A": 70.0}


def test_load_previous_snapshot_returns_empty_when_history_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "PRIVATE_HISTORY_PATH", tmp_path / "missing-private.csv")
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", tmp_path / "missing-local.csv")

    previous_total, previous_by_fund = persistence.load_previous_snapshot("2026-04-16", ["Fund A"])
    assert previous_total is None
    assert previous_by_fund == {}


def test_load_previous_snapshot_handles_malformed_history(tmp_path, monkeypatch):
    history_path = tmp_path / "daily_totals.csv"
    history_path.write_text("not,a,valid,csv\n1,2", encoding="utf-8")

    monkeypatch.setattr(persistence, "PRIVATE_HISTORY_PATH", tmp_path / "missing-private.csv")
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", history_path)

    previous_total, previous_by_fund = persistence.load_previous_snapshot("2026-04-16", ["Fund A"])
    assert previous_total is None
    assert previous_by_fund == {}


def test_update_daily_totals_writes_and_updates_history(tmp_path):
    history_path = tmp_path / "daily_totals.csv"
    data = pd.DataFrame({"Total Holding Value": [10.0, 20.0]}, index=["Fund A", "Fund B"])

    first = persistence.update_daily_totals(data, 30.0, "2026-04-16", filename=str(history_path))
    second = persistence.update_daily_totals(data * 2, 60.0, "2026-04-16", filename=str(history_path))

    assert list(first.columns[:2]) == ["Date", "Total"]
    assert len(second) == 1
    assert second.loc[0, "Total"] == 60.0
    assert second.loc[0, "Fund A"] == 20.0
