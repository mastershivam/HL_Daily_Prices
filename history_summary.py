import os

import pandas as pd


def load_previous_snapshot(today_str: str, fund_names: list[str]) -> tuple[float | None, dict[str, float]]:
    """
    Return the previous portfolio total and per-fund values from the latest row
    strictly earlier than today. Falls back cleanly if history is unavailable.
    """
    previous_total = None
    previous_by_fund: dict[str, float] = {}

    try:
        hist_path = os.path.join("HL_Daily_Prices_Data", "outputs", "daily_totals.csv")
        if not os.path.exists(hist_path):
            hist_path = "daily_totals.csv"
        if not os.path.exists(hist_path):
            return previous_total, previous_by_fund

        hist_df = pd.read_csv(hist_path)
        if "Date" in hist_df.columns:
            hist_df["Date"] = pd.to_datetime(hist_df["Date"])
        today_dt = pd.to_datetime(today_str)
        prev_df = hist_df[hist_df["Date"] < today_dt].sort_values("Date") if "Date" in hist_df.columns else hist_df
        if prev_df.empty:
            return previous_total, previous_by_fund

        prev_row = prev_df.iloc[-1]
        if "Total" in prev_row and pd.notna(prev_row.get("Total")):
            previous_total = float(prev_row.get("Total"))

        for fund_name in fund_names:
            if fund_name in prev_row.index and pd.notna(prev_row.get(fund_name)):
                try:
                    previous_by_fund[fund_name] = float(prev_row.get(fund_name))
                except (TypeError, ValueError):
                    continue
    except Exception:
        return None, {}

    return previous_total, previous_by_fund
