import pandas as pd
import pytest

from pull_and_collate import load_units_dataframe, scrape_fund_rows


def _write_units(tmp_path, rows):
    path = tmp_path / "units.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_load_units_dataframe_rejects_duplicate_fund_names(tmp_path):
    path = _write_units(
        tmp_path,
        [
            {"fund": "Fund A", "units": 10, "url": "https://example.com/a"},
            {"fund": "Fund A", "units": 5, "url": "https://example.com/a2"},
        ],
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_units_dataframe(path)


def test_load_units_dataframe_rejects_non_positive_units(tmp_path):
    path = _write_units(
        tmp_path,
        [{"fund": "Fund A", "units": 0, "url": "https://example.com/a"}],
    )
    with pytest.raises(ValueError, match="units"):
        load_units_dataframe(path)


def test_load_units_dataframe_rejects_invalid_type(tmp_path):
    path = _write_units(
        tmp_path,
        [{"fund": "Fund A", "units": 10, "url": "https://example.com/a", "type": "bond"}],
    )
    with pytest.raises(ValueError, match="'fund' or 'share'"):
        load_units_dataframe(path)


def test_load_units_dataframe_defaults_type_to_fund(tmp_path):
    path = _write_units(
        tmp_path,
        [{"fund": "Fund A", "units": 10, "url": "https://example.com/a"}],
    )
    df = load_units_dataframe(path)
    assert list(df["type"]) == ["fund"]


def test_scrape_fund_rows_reports_failed_funds_without_raising(monkeypatch):
    units_df = pd.DataFrame(
        [
            {"fund": "Good Fund", "units": 10, "url": "https://example.com/good", "type": "fund"},
            {"fund": "Broken Fund", "units": 5, "url": "https://example.com/broken", "type": "fund"},
        ]
    )

    def fake_price_scraper_fund(url):
        if "broken" in url:
            raise RuntimeError("network error")
        return {"title": "Good Fund", "sell": "£1.00", "buy": "£1.01", "change_value": None, "change_pct": None}

    monkeypatch.setattr("pull_and_collate.price_scraper_fund", fake_price_scraper_fund)

    rows, failed_funds = scrape_fund_rows(units_df)

    assert len(rows) == 1
    assert failed_funds == ["Broken Fund"]


def test_holding_whose_page_has_no_sell_price_is_reported_not_silently_dropped(monkeypatch, tmp_path):
    """Regression: a page that loads (has a title) but yields no "Sell:" price
    used to be dropped from the total with failed_funds left empty, so the
    push notification gave no warning (this hid Super Micro for months)."""
    import pull_and_collate

    units_path = _write_units(
        tmp_path,
        [
            {"fund": "Good Fund", "units": 10, "url": "https://example.com/funds/good", "type": "fund"},
            {"fund": "No Price Share", "units": 100, "url": "https://example.com/shares/noprice", "type": "fund"},
        ],
    )
    monkeypatch.setattr(pull_and_collate, "resolve_units_path", lambda: units_path)

    def fake_price_scraper_fund(url):
        if "noprice" in url:
            return {"title": "No Price Share", "sell": None, "buy": None, "change_value": None, "change_pct": None}
        return {"title": "Good Fund", "sell": "100.00p", "buy": None, "change_value": None, "change_pct": None}

    monkeypatch.setattr(pull_and_collate, "price_scraper_fund", fake_price_scraper_fund)

    data, failed_funds = pull_and_collate.create_data_frame()

    assert list(data.index) == ["Good Fund"]
    assert failed_funds == ["No Price Share"]
