from pathlib import Path

import pandas as pd


DEFAULT_HISTORY_PATH = Path("daily_totals.csv")
PRIVATE_HISTORY_PATH = Path("HL_Daily_Prices_Data") / "outputs" / "daily_totals.csv"


def resolve_history_path() -> Path:
    if PRIVATE_HISTORY_PATH.exists():
        return PRIVATE_HISTORY_PATH
    return DEFAULT_HISTORY_PATH


def load_previous_snapshot(today_str: str, fund_names: list[str]) -> tuple[float | None, dict[str, float]]:
    previous_total = None
    previous_by_fund: dict[str, float] = {}

    try:
        history_path = resolve_history_path()
        if not history_path.exists():
            return previous_total, previous_by_fund

        history_df = pd.read_csv(history_path)
        if "Date" in history_df.columns:
            history_df["Date"] = pd.to_datetime(history_df["Date"])
        today_dt = pd.to_datetime(today_str)
        previous_rows = history_df[history_df["Date"] < today_dt].sort_values("Date") if "Date" in history_df.columns else history_df
        if previous_rows.empty:
            return previous_total, previous_by_fund

        previous_row = previous_rows.iloc[-1]
        if "Total" in previous_row and pd.notna(previous_row.get("Total")):
            previous_total = float(previous_row.get("Total"))

        for fund_name in fund_names:
            if fund_name in previous_row.index and pd.notna(previous_row.get(fund_name)):
                try:
                    previous_by_fund[fund_name] = float(previous_row.get(fund_name))
                except (TypeError, ValueError):
                    continue
    except Exception:
        return None, {}

    return previous_total, previous_by_fund


def update_daily_totals(data: pd.DataFrame, total: float, today_str: str, filename: str = "daily_totals.csv") -> pd.DataFrame:
    fund_values = data["Total Holding Value"].to_dict()
    row_dict = {"Date": today_str, "Total": total}
    row_dict.update(fund_values)

    path = Path(filename)
    if path.exists():
        history_df = pd.read_csv(path)
        for fund in fund_values:
            if fund not in history_df.columns:
                history_df[fund] = pd.NA
        if today_str in history_df["Date"].values:
            for key, value in row_dict.items():
                history_df.loc[history_df["Date"] == today_str, key] = value
        else:
            history_df = pd.concat([history_df, pd.DataFrame([row_dict])], ignore_index=True)
    else:
        history_df = pd.DataFrame([row_dict])

    history_df.to_csv(path, index=False)
    return history_df
