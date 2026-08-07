import pandas as pd

from html_summary import build_html_summary, build_sparkline_svg


def test_build_sparkline_svg_returns_empty_string_for_insufficient_data():
    assert build_sparkline_svg([]) == ""
    assert build_sparkline_svg([100.0]) == ""


def test_build_sparkline_svg_renders_polyline_for_multiple_points():
    svg = build_sparkline_svg([100.0, 110.0, 90.0, 120.0])
    assert svg.startswith("<svg")
    assert "<polyline" in svg


def _sample_data():
    return pd.DataFrame(
        {
            "Total Holding Value": [150.0, 50.0],
        },
        index=["Fund A", "Fund B"],
    )


def test_build_html_summary_includes_failed_funds_warning():
    html = build_html_summary(
        _sample_data(),
        total=200.0,
        today_str="2026-04-16",
        previous_total=190.0,
        previous_by_fund={"Fund A": 140.0, "Fund B": 50.0},
        failed_funds=["Broken Fund"],
    )
    assert "Broken Fund" in html
    assert "Could not price" in html


def test_build_html_summary_includes_cost_basis_and_pnl():
    html = build_html_summary(
        _sample_data(),
        total=200.0,
        today_str="2026-04-16",
        previous_total=190.0,
        previous_by_fund={"Fund A": 140.0, "Fund B": 50.0},
        cost_basis_by_fund={"Fund A": 100.0},
    )
    assert "Cost Basis" in html
    assert "Unrealised P&amp;L" in html or "Unrealised P&L" in html


def test_build_html_summary_includes_watchlist_quotes():
    html = build_html_summary(
        _sample_data(),
        total=200.0,
        today_str="2026-04-16",
        watchlist_quotes=[{"symbol": "ELIX.L", "price_pence": 152.5, "change_pence": 1.5, "change_pct": 1.0}],
    )
    assert "LON:ELIX.L" in html


def test_build_html_summary_includes_sparkline_when_history_given():
    html = build_html_summary(
        _sample_data(),
        total=200.0,
        today_str="2026-04-16",
        history_totals=[180.0, 190.0, 200.0],
    )
    assert "sparkline" in html
    assert "<svg" in html
