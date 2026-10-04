import pandas as pd

import pull_and_collate
from pull_and_collate import _scrape_share_row, normalise_merged_dataframe
from utilities import infer_currency, parse_price_to_gbp


def test_scrape_share_row_formats_gbp_ticker_as_pounds_not_pence(monkeypatch):
    monkeypatch.setattr(
        pull_and_collate,
        "fetch_share_quote",
        lambda symbol: {
            "symbol": symbol,
            "price_pence": 630.0,
            "change_pence": 1.5,
            "change_pct": 1.23,
            "currency": "GBP",
            "native_price": 6.30,
            "native_change": 0.015,
        },
    )

    row = _scrape_share_row("ELIX.L")

    assert row["sell"] == "£6.3000"
    # Round-trips correctly through the normal fund-price parsing pipeline.
    assert infer_currency(row["sell"]) == "GBP"
    assert parse_price_to_gbp(row["sell"], is_share=True) == 6.30


def test_scrape_share_row_uses_native_price_for_usd_ticker_not_price_pence(monkeypatch):
    # This is the bug that was fixed: a USD stock's price_pence field isn't
    # meaningful (fetch_share_quote only scales to pence for GBP tickers),
    # so using it here used to understate the value by ~100x and skip FX
    # conversion entirely.
    monkeypatch.setattr(
        pull_and_collate,
        "fetch_share_quote",
        lambda symbol: {
            "symbol": symbol,
            "price_pence": 3890.0,  # native_price * scale(1.0) - NOT what should be used
            "change_pence": -26.0,
            "change_pct": -0.68,
            "currency": "USD",
            "native_price": 38.90,
            "native_change": -0.26,
        },
    )

    row = _scrape_share_row("SMCI")

    assert row["sell"] == "$38.9000"
    assert row["change_value"] == "$-0.2600"
    assert infer_currency(row["sell"]) == "USD"
    assert parse_price_to_gbp(row["sell"], is_share=True) == 38.90


def test_usd_share_row_gets_converted_to_gbp_end_to_end(monkeypatch):
    monkeypatch.setattr(pull_and_collate, "get_fx_rate_to_gbp", lambda currency: 0.8)

    merged = pd.DataFrame(
        {
            "units": [100],
            "sell": ["$38.9000"],
            "title": ["Super Micro Computer Inc"],
            "url": ["SMCI"],
            "type": ["share"],
        },
        index=["Super Micro Computer Inc"],
    )

    normalised = normalise_merged_dataframe(merged)

    # 100 units * $38.90 = $3,890 -> * 0.8 FX rate = £3,112 - not $38.90
    # (the old bug) and not left in USD (also the old bug).
    assert normalised.loc["Super Micro Computer Inc", "value"] == 3112.0
    assert normalised.loc["Super Micro Computer Inc", "currency"] == "GBP"


def test_fx_rate_prefers_yahoo_and_falls_back_to_ecb(monkeypatch):
    import utilities

    monkeypatch.setattr(utilities, "_fetch_yahoo_fx_rate", lambda currency: 0.7551)
    monkeypatch.setattr(utilities, "_fetch_ecb_fx_rate", lambda currency: 0.7575)
    assert utilities.get_fx_rate_to_gbp("USD") == 0.7551
    assert utilities.get_fx_rate_to_gbp("GBP") == 1.0

    def broken(currency):
        raise ValueError("no quote")

    monkeypatch.setattr(utilities, "_fetch_yahoo_fx_rate", broken)
    monkeypatch.setattr(utilities.time, "sleep", lambda s: None)
    assert utilities.get_fx_rate_to_gbp("USD") == 0.7575


def test_html_shows_us_share_price_in_dollars_and_value_in_pounds():
    import pandas as pd
    from html_summary import build_html_summary

    data = pd.DataFrame(
        {
            "Units": [100.0, 10.0],
            "Sell Price": [43.69, 4.01],
            "Price Currency": ["USD", "GBP"],
            "Currency": ["GBP", "GBP"],
            "Total Holding Value": [3298.84, 40.10],
        },
        index=pd.Index(["Super Micro", "Some Fund"], name="Fund/Share"),
    )
    html = build_html_summary(data, 3338.94, "2026-10-04", previous_total=3300.0, previous_by_fund={})
    assert "$43.69" in html and "£43.69" not in html
    assert "£4.01" in html and "£3,298.84" in html
    assert "Price Currency" not in html
