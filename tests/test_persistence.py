from pathlib import Path

import pandas as pd

import persistence


def _no_data_dir(monkeypatch):
    # get_data_dir() is imported into persistence's namespace as
    # `get_data_dir` - patch it there so resolve_history_path() falls back
    # to DEFAULT_HISTORY_PATH, as if no private data repo were found.
    monkeypatch.setattr(persistence, "get_data_dir", lambda: None)


def test_load_previous_snapshot_uses_latest_prior_row(tmp_path, monkeypatch):
    history_path = tmp_path / "daily_totals.csv"
    pd.DataFrame(
        [
            {"Date": "2026-04-14", "Total": 100.0, "Fund A": 60.0},
            {"Date": "2026-04-15", "Total": 110.0, "Fund A": 70.0},
            {"Date": "2026-04-16", "Total": 120.0, "Fund A": 80.0},
        ]
    ).to_csv(history_path, index=False)

    _no_data_dir(monkeypatch)
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", history_path)

    previous_total, previous_by_fund = persistence.load_previous_snapshot("2026-04-16", ["Fund A"])
    assert previous_total == 110.0
    assert previous_by_fund == {"Fund A": 70.0}


def test_load_previous_snapshot_returns_empty_when_history_missing(tmp_path, monkeypatch):
    _no_data_dir(monkeypatch)
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", tmp_path / "missing-local.csv")

    previous_total, previous_by_fund = persistence.load_previous_snapshot("2026-04-16", ["Fund A"])
    assert previous_total is None
    assert previous_by_fund == {}


def test_load_previous_snapshot_handles_malformed_history(tmp_path, monkeypatch):
    history_path = tmp_path / "daily_totals.csv"
    history_path.write_text("not,a,valid,csv\n1,2", encoding="utf-8")

    _no_data_dir(monkeypatch)
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", history_path)

    previous_total, previous_by_fund = persistence.load_previous_snapshot("2026-04-16", ["Fund A"])
    assert previous_total is None
    assert previous_by_fund == {}


def test_resolve_history_path_prefers_data_dir_when_found(tmp_path, monkeypatch):
    data_dir = tmp_path / "HL_Daily_Prices_Data"
    data_dir.mkdir()
    monkeypatch.setattr(persistence, "get_data_dir", lambda: data_dir)

    assert persistence.resolve_history_path() == data_dir / "outputs" / "daily_totals.csv"


def test_load_history_totals_returns_recent_totals_in_date_order(tmp_path, monkeypatch):
    history_path = tmp_path / "daily_totals.csv"
    pd.DataFrame(
        [
            {"Date": "2026-04-16", "Total": 120.0},
            {"Date": "2026-04-14", "Total": 100.0},
            {"Date": "2026-04-15", "Total": 110.0},
        ]
    ).to_csv(history_path, index=False)

    _no_data_dir(monkeypatch)
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", history_path)

    assert persistence.load_history_totals() == [100.0, 110.0, 120.0]
    assert persistence.load_history_totals(limit=2) == [110.0, 120.0]


def test_load_history_totals_returns_empty_list_when_missing(tmp_path, monkeypatch):
    _no_data_dir(monkeypatch)
    monkeypatch.setattr(persistence, "DEFAULT_HISTORY_PATH", tmp_path / "missing-local.csv")

    assert persistence.load_history_totals() == []


def test_update_daily_totals_writes_and_updates_history(tmp_path):
    history_path = tmp_path / "daily_totals.csv"
    data = pd.DataFrame({"Total Holding Value": [10.0, 20.0]}, index=["Fund A", "Fund B"])

    first = persistence.update_daily_totals(data, 30.0, "2026-04-16", filename=str(history_path))
    second = persistence.update_daily_totals(data * 2, 60.0, "2026-04-16", filename=str(history_path))

    assert list(first.columns[:2]) == ["Date", "Total"]
    assert len(second) == 1
    assert second.loc[0, "Total"] == 60.0
    assert second.loc[0, "Fund A"] == 20.0
