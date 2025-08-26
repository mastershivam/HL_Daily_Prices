import os
import pandas as pd

def build_html_summary(data: pd.DataFrame, total: float, today_str: str) -> str:
    # Convert index to column for display
    df_display = data.reset_index().rename(columns={"index": "Fund/Share"})

    # Compute day-over-day using private repo history when available
    previous_total = None
    previous_by_fund = {}
    try:
        hist_path = os.path.join('HL_Daily_Prices_Data', 'outputs', 'daily_totals.csv')
        if not os.path.exists(hist_path):
            hist_path = 'daily_totals.csv'
        if os.path.exists(hist_path):
            hist_df = pd.read_csv(hist_path)
            if 'Date' in hist_df.columns:
                hist_df['Date'] = pd.to_datetime(hist_df['Date'])
            today_dt = pd.to_datetime(today_str)
            prev_df = hist_df[hist_df['Date'] < today_dt].sort_values('Date') if 'Date' in hist_df.columns else hist_df
            if not prev_df.empty:
                prev_row = prev_df.iloc[-1]
                previous_total = float(prev_row.get('Total')) if 'Total' in prev_row else None
                # Map per-instrument previous values using column names that match fund names
                for fund_name in data.index.tolist():
                    if fund_name in prev_row.index and pd.notna(prev_row.get(fund_name)):
                        try:
                            previous_by_fund[fund_name] = float(prev_row.get(fund_name))
                        except Exception:
                            continue
    except Exception:
        # Be resilient; if anything goes wrong, omit DoD info
        previous_total = None
        previous_by_fund = {}

    # Attach DoD Change and DoD % to the display dataframe
    dod_changes = []
    dod_pcts = []
    for fund_name, row in data.iterrows():
        curr_val = float(row.get('Total Holding Value', 0.0))
        prev_val = previous_by_fund.get(fund_name)
        if prev_val is None:
            dod_changes.append(None)
            dod_pcts.append(None)
        else:
            chg = curr_val - prev_val
            pct = (chg / prev_val * 100.0) if prev_val else None
            dod_changes.append(chg)
            dod_pcts.append(pct)
    df_display['DoD Change'] = dod_changes
    df_display['DoD %'] = dod_pcts

    # HTML table
    # Format columns if present
    formatters = {}
    if "Total Holding Value" in df_display.columns:
        formatters["Total Holding Value"] = lambda v: f"£{v:,.2f}" if pd.notna(v) else ""
    if "Sell Price" in df_display.columns:
        formatters["Sell Price"] = lambda v: f"£{v:,.2f}" if pd.notna(v) else ""
    if "DoD Change" in df_display.columns:
        formatters["DoD Change"] = lambda v: ("+" if v is not None and v >= 0 else "") + (f"£{v:,.2f}" if v is not None else "")
    if "DoD %" in df_display.columns:
        formatters["DoD %"] = lambda v: ("+" if v is not None and v >= 0 else "") + (f"{v:.2f}%" if v is not None else "")

    table_html = df_display.to_html(index=False, border=0, classes="dataframe", escape=False, formatters=formatters)

    # Build total badge safely (avoid complex f-string expressions)
    total_badge = f"Total: £{total:,.2f}"
    if previous_total is not None:
        diff = total - previous_total
        pct = None if previous_total == 0 else ((diff / previous_total) * 100.0)
        if pct is not None:
            if diff >0:
                total_class = "total up"
                total_indicator = "▲"
            elif diff <0:
                total_class = "total down"
                total_indicator = "▼"
            else:
                total_class = "total flat"
                total_indicator = "•"
        sign = "+" if diff >= 0 else ""
        pct_txt = f" ({'+' if (pct is not None and pct >= 0) else ''}{pct:.2f}%)" if pct is not None else ""
        total_badge = (
            f"Total: £{total:,.2f}  "
            f"<span style=\"margin-left:8px; padding:4px 8px; border-radius:999px; color:#e5e7eb;\">"
            f"{total_indicator}£{diff:,.2f}{pct_txt}</span>"
        )

    html=f"""
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body {{ margin:0; padding:0; background:#0b1220; color:#e2e8f0; font-family:Arial,Helvetica,sans-serif; }}
        .container {{ width:100%; margin:0; background:#111827; box-shadow:0 2px 12px rgba(0,0,0,.25); overflow:hidden; border:1px solid #1f2937; }}
        .header {{ padding:22px 24px; border-bottom:1px solid #1f2937; }}
        .title {{ margin:0; font-size:24px; color:#f8fafc; }}
        .meta {{ margin-top:6px; font-size:13px; color:#94a3b8; }}
        .total.flat {{ margin:16px 24px 0; background:#0ea5e9; color:#00131a; font-weight:800; display:inline-block; padding:10px 14px; border-radius:999px; }}
        .total.up {{ margin:16px 24px 0; background:#0ea5e9;  color:#22c55e; font-weight:800; display:inline-block; padding:10px 14px; border-radius:999px; }}
        .total.down {{ margin:16px 24px 0; background:#0ea5e9; color:#ef4444; font-weight:800; display:inline-block; padding:10px 14px; border-radius:999px; }}        
        .content {{ padding:20px 24px 28px; }}
        table.dataframe {{ border-collapse:collapse; width:100%; }}
        table.dataframe th, table.dataframe td {{ border:1px solid #374151; padding:10px; text-align:left; font-size:14px;  color:#fff; }}
        table.dataframe thead th {{ background:#0f172a; color:#cbd5e1; border-bottom:2px solid #64748b; }}
        table.dataframe tbody tr:nth-child(odd) {{ background:#0b1324; }}
        a {{ color:#7dd3fc; }}
        .footer {{ color:#64748b; font-size:12px; text-align:center; padding:14px; }}
    </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
        <h1 class="title">Daily Portfolio Summary</h1>
        <div class="meta">{today_str}</div>
        </div>
        <div class={total_class}>{total_badge}</div>
        <div class="content">
        {table_html}
        </div>
        <div class="footer">Automatic message • HL Price Update</div>
    </div>
    </body>
    </html>
    """
    return html