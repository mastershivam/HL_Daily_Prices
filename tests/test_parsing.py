import pandas as pd

from price_scraper import parse_fund_html
from pull_and_collate import normalise_merged_dataframe
from utilities import convert_value_to_gbp, infer_currency, parse_price_to_gbp


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


def test_parse_price_to_gbp_handles_fund_and_share_values():
    assert parse_price_to_gbp("123.45p", is_share=False) == 1.2345
    assert parse_price_to_gbp("£123.45", is_share=True) == 123.45


def test_currency_helpers_convert_usd_values():
    assert infer_currency("$123.45") == "USD"
    assert infer_currency("£123.45") == "GBP"
    assert convert_value_to_gbp(100.0, "USD", 0.8) == 80.0
    assert convert_value_to_gbp(100.0, "GBP", 0.8) == 100.0


def test_normalise_merged_dataframe_converts_prices_and_values(monkeypatch):
    monkeypatch.setattr("pull_and_collate.get_usd_gbp_rate", lambda: 0.8)
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
