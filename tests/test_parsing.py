import pandas as pd

from price_scraper import parse_fund_html
from pull_and_collate import normalise_merged_dataframe
from utilities import convert_value_to_gbp, infer_currency, infer_is_share, parse_price_to_gbp


def test_parse_fund_html_extracts_expected_fields():
    html = """
    <html>
      <head><meta property="og:title" content="Vanguard FTSE Global All Cap Index Accumulation"></head>
      <body>
        <div>Sell: £123.45</div>
        <div>Buy: £125.67</div>
        <div>Change: +1.23 ( +1.01%)</div>
      </body>
    </html>
    """

    parsed = parse_fund_html(html)

    assert parsed["title"] == "Vanguard FTSE Global All Cap Index Accumulation"
    assert parsed["sell"] == "£123.45"
    assert parsed["buy"] == "£125.67"
    assert parsed["change_value"] == "+1.23"
    assert parsed["change_pct"] == "+1.01%"


def test_parse_price_to_gbp_handles_fund_and_share_values():
    assert parse_price_to_gbp("123.45p", is_share=False) == 1.2345
    assert parse_price_to_gbp("£123.45", is_share=True) == 123.45


def test_currency_helpers_convert_usd_and_eur_values():
    assert infer_currency("$123.45") == "USD"
    assert infer_currency("£123.45") == "GBP"
    assert infer_currency("€123.45") == "EUR"
    assert convert_value_to_gbp(100.0, "USD", 0.8) == 80.0
    assert convert_value_to_gbp(100.0, "EUR", 0.9) == 90.0
    assert convert_value_to_gbp(100.0, "GBP", 0.8) == 100.0


def test_infer_is_share_prefers_explicit_type_over_name_text():
    # "iShares" funds contain the substring "share" but are priced in pence
    # like any other fund - the old name-text heuristic misclassified them.
    assert infer_is_share(None, "https://www.hl.co.uk/funds/...", "iShares FTSE 100 Index") is False
    assert infer_is_share("share", None, "Electra Private Equity") is True
    assert infer_is_share(None, "https://www.hl.co.uk/shares/shares-search-results/x", "Anything") is True
    # No type/url signal at all falls back to the legacy name-text heuristic.
    assert infer_is_share(None, None, "Some Share Class Fund") is True
    assert infer_is_share(None, None, "Ordinary Fund") is False


def test_normalise_merged_dataframe_converts_prices_and_values(monkeypatch):
    monkeypatch.setattr("pull_and_collate.get_fx_rate_to_gbp", lambda currency: 0.8)
    merged = pd.DataFrame(
        {
            "units": [2, 3],
            "sell": ["123.45p", "$10.00"],
            "title": ["Fund A", "Share B"],
        },
        index=["Fund A", "Share B"],
    )

    normalised = normalise_merged_dataframe(merged)

    assert normalised.loc["Fund A", "sell"] == 1.2345
    assert normalised.loc["Fund A", "value"] == 2.469
    assert normalised.loc["Share B", "sell"] == 10.0
    assert normalised.loc["Share B", "value"] == 24.0
    assert set(normalised["currency"]) == {"GBP"}


def test_normalise_merged_dataframe_only_fetches_fx_for_currencies_present(monkeypatch):
    calls = []
    monkeypatch.setattr("pull_and_collate.get_fx_rate_to_gbp", lambda currency: calls.append(currency) or 1.0)
    merged = pd.DataFrame(
        {"units": [2], "sell": ["123.45p"], "title": ["Fund A"]},
        index=["Fund A"],
    )

    normalise_merged_dataframe(merged)

    assert calls == []


def test_normalise_merged_dataframe_uses_url_pattern_for_share_detection(monkeypatch):
    monkeypatch.setattr("pull_and_collate.get_fx_rate_to_gbp", lambda currency: 1.0)
    merged = pd.DataFrame(
        {
            "units": [10],
            "sell": ["£4.5000"],
            "title": ["iShares FTSE 100 Index"],
            "url": ["https://www.hl.co.uk/funds/fund-discounts,-prices--and--factsheets/search-results/i/ishares-ftse-100-index"],
            "type": ["fund"],
        },
        index=["iShares FTSE 100 Index"],
    )

    normalised = normalise_merged_dataframe(merged)

    # Priced in pounds ("£4.5000") but is_share is correctly False because the
    # URL is a /funds/ URL - so it should be divided by 100 like any fund
    # price, not treated as an already-in-pounds share price.
    assert normalised.loc["iShares FTSE 100 Index", "sell"] == 0.045
