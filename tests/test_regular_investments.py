from datetime import date

import pandas as pd
import pytest

import regular_investments as ri
from notifications import format_push_message


FUND_A = "BlackRock Continental European Income FundClass D - Accumulation (GBP)"
FUND_B = "Vanguard FTSE Global All Cap Index Accumulation (GBP)"
SHARE = "Super Micro Computer Inc USD0.001 Share Price"


@pytest.fixture
def repo(tmp_path):
    units = tmp_path / "units.csv"
    pd.DataFrame(
        [
            {"fund": FUND_A, "units": 1000.0, "url": "https://hl/funds/a", "type": "fund"},
            {"fund": FUND_B, "units": 10.0, "url": "https://hl/funds/b", "type": "fund"},
            {"fund": SHARE, "units": 100.0, "url": "SMCI", "type": "share"},
        ]
    ).to_csv(units, index=False)
    plan = tmp_path / "investment_plan.csv"
    plan.write_text(
        "fund,monthly_amount_gbp,day_of_month,start_month\n"
        "blackrock continental european income,300,10,2026-09\n"
        "Vanguard FTSE Global All Cap,300,10,2026-09\n"
    )
    paths = {
        "plan_path": plan,
        "units_path": units,
        "transactions_path": tmp_path / "transactions.csv",
        "prices_path": tmp_path / "daily_prices.csv",
        "history_path": tmp_path / "daily_totals.csv",
    }
    return paths


def _today_frame():
    return pd.DataFrame(
        {"Units": [1000.0, 10.0, 100.0], "Total Holding Value": [4100.0, 3200.0, 3300.0]},
        index=[FUND_A, FUND_B, SHARE],
    )


def test_dealing_date_rolls_weekend_to_monday():
    assert ri.dealing_date(2026, 10, 10) == date(2026, 10, 12)  # Saturday -> Monday
    assert ri.dealing_date(2026, 9, 10) == date(2026, 9, 10)  # Thursday
    assert ri.dealing_date(2026, 2, 31) == date(2026, 3, 2)  # clamps to 28th (Sat) -> Mon


def test_due_dealings_only_includes_dates_strictly_before_today():
    assert ri.due_dealings("2026-09", 10, date(2026, 9, 10)) == []
    assert ri.due_dealings("2026-09", 10, date(2026, 9, 11)) == [("2026-09", date(2026, 9, 10))]
    assert [m for m, _ in ri.due_dealings("2026-09", 10, date(2026, 10, 13))] == ["2026-09", "2026-10"]


def test_match_fund_accepts_short_names_and_rejects_ambiguity():
    names = [FUND_A, FUND_B, "Vanguard FTSE 100 IndexAccumulation (GBP)"]
    assert ri.match_fund("blackrock continental", names) == FUND_A
    with pytest.raises(ValueError, match="ambiguous"):
        ri.match_fund("Vanguard FTSE", names)
    with pytest.raises(ValueError, match="doesn't match"):
        ri.match_fund("Baillie Gifford", names)


def test_backfills_missed_month_from_value_history_and_is_idempotent(repo):
    # daily_totals has values for the day after dealing; units unchanged since.
    pd.DataFrame(
        [
            {"Date": "2026-09-10", "Total": 1, FUND_A: 3900.0, FUND_B: 2900.0},
            {"Date": "2026-09-11", "Total": 1, FUND_A: 4000.0, FUND_B: 3000.0},
        ]
    ).to_csv(repo["history_path"], index=False)

    recorded = ri.apply_regular_investments(_today_frame(), today=date(2026, 10, 4), **repo)

    assert {(b["fund"], b["month"]) for b in recorded} == {(FUND_A, "2026-09"), (FUND_B, "2026-09")}
    by_fund = {b["fund"]: b for b in recorded}
    assert by_fund[FUND_A]["price_gbp"] == pytest.approx(4.0)  # 4000 / 1000 units
    assert by_fund[FUND_A]["units"] == pytest.approx(75.0)
    assert by_fund[FUND_B]["price_gbp"] == pytest.approx(300.0)
    assert by_fund[FUND_B]["units"] == pytest.approx(1.0)

    units = pd.read_csv(repo["units_path"]).set_index("fund")
    assert units.at[FUND_A, "units"] == pytest.approx(1075.0)
    assert units.at[FUND_B, "units"] == pytest.approx(11.0)
    # untouched holding + its share type/ticker survive the regeneration
    assert units.at[SHARE, "units"] == pytest.approx(100.0)
    assert units.at[SHARE, "type"] == "share" and units.at[SHARE, "url"] == "SMCI"

    # Second run the same day: nothing new.
    assert ri.apply_regular_investments(_today_frame(), today=date(2026, 10, 4), **repo) == []
    assert pd.read_csv(repo["units_path"]).set_index("fund").at[FUND_A, "units"] == pytest.approx(1075.0)


def test_prefers_daily_price_history_and_amount_change_applies_going_forward(repo):
    pd.DataFrame([{"Date": "2026-09-11", FUND_A: 4.0, FUND_B: 300.0}]).to_csv(repo["prices_path"], index=False)
    ri.apply_regular_investments(_today_frame(), today=date(2026, 9, 12), **repo)

    # Direct debit increased after September was recorded.
    repo["plan_path"].write_text(
        "fund,monthly_amount_gbp,day_of_month,start_month\n"
        "blackrock continental european income,400,10,2026-09\n"
        "Vanguard FTSE Global All Cap,300,10,2026-09\n"
    )
    pd.DataFrame(
        [{"Date": "2026-09-11", FUND_A: 4.0, FUND_B: 300.0}, {"Date": "2026-10-13", FUND_A: 5.0, FUND_B: 250.0}]
    ).to_csv(repo["prices_path"], index=False)
    recorded = ri.apply_regular_investments(_today_frame(), today=date(2026, 10, 13), **repo)

    oct_a = next(b for b in recorded if b["fund"] == FUND_A)
    assert oct_a["month"] == "2026-10" and oct_a["amount_gbp"] == 400 and oct_a["units"] == pytest.approx(80.0)
    txns = pd.read_csv(repo["transactions_path"])
    sept_a = txns[(txns["fund"] == FUND_A) & txns["note"].str.startswith("regular investment 2026-09")]
    assert sept_a["amount_gbp"].tolist() == [300.0]  # history not rewritten


def test_falls_back_to_live_price_and_flags_it(repo):
    recorded = ri.apply_regular_investments(_today_frame(), today=date(2026, 9, 12), **repo)
    a = next(b for b in recorded if b["fund"] == FUND_A)
    assert a["price_source"].startswith("live price")
    assert a["price_gbp"] == pytest.approx(4.1)


def test_zero_amount_pauses_and_missing_plan_is_noop(repo, tmp_path):
    repo["plan_path"].write_text("fund,monthly_amount_gbp,start_month\nblackrock continental,0,2026-09\n")
    assert ri.apply_regular_investments(_today_frame(), today=date(2026, 10, 4), **repo) == []
    repo["plan_path"] = tmp_path / "nope.csv"
    assert ri.apply_regular_investments(_today_frame(), today=date(2026, 10, 4), **repo) == []
    assert not repo["transactions_path"].exists()


def test_bad_plan_name_writes_nothing(repo):
    repo["plan_path"].write_text("fund,monthly_amount_gbp,start_month\nNot A Fund,100,2026-09\n")
    with pytest.raises(ValueError):
        ri.apply_regular_investments(_today_frame(), today=date(2026, 10, 4), **repo)
    assert pd.read_csv(repo["units_path"]).set_index("fund").at[FUND_A, "units"] == pytest.approx(1000.0)


def test_apply_to_dataframe_values_new_units_at_todays_price():
    data = ri.apply_to_dataframe(_today_frame(), [{"fund": FUND_A, "units": 75.0, "price_gbp": 4.0}])
    assert data.at[FUND_A, "Units"] == pytest.approx(1075.0)
    assert data.at[FUND_A, "Total Holding Value"] == pytest.approx(4100.0 * 1075 / 1000)


def test_update_daily_prices_stores_gbp_unit_price(tmp_path):
    path = tmp_path / "daily_prices.csv"
    ri.update_daily_prices(_today_frame(), "2026-10-04", path)
    ri.update_daily_prices(_today_frame(), "2026-10-04", path)  # same day overwrites
    df = pd.read_csv(path)
    assert len(df) == 1 and df.at[0, SHARE] == pytest.approx(33.0)


def test_push_excludes_invested_money_from_daily_change():
    buys = [{"label": "BlackRock", "amount_gbp": 300.0, "month": "2026-10", "price_source": "price history"}]
    msg = format_push_message(10_350.0, 10_000.0, regular_investments=buys)
    assert "(+50.00, +0.50%) excl. GBP 300.00 invested" in msg
    assert "Recorded regular investment: GBP 300.00" in msg
