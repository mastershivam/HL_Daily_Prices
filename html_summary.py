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
    total_class = "total flat"
    if previous_total is not None:
        diff = total - previous_total
        pct = None if previous_total == 0 else ((diff / previous_total) * 100.0)
        sign = "+" if diff >= 0 else ""
        pct_txt = f" ({'+' if (pct is not None and pct >= 0) else ''}{pct:.2f}%)" if pct is not None else ""
        total_badge = (
            f"Total: £{total:,.2f}  "
            f"<span style=\"margin-left:8px; padding:4px 8px; border-radius:999px;\">"
            f"{sign}£{diff:,.2f}{pct_txt}</span>"
        )
        if diff > 0:
            total_class = "total up"
        elif diff < 0:
            total_class = "total down"

    html=f"""
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body {{ margin:0; padding:0; background:#0b1220; color:#e2e8f0; font-family:Arial,Helvetica,sans-serif; }}
        .container {{ width:100%; margin:0; background:#111827; box-shadow:0 2px 12px rgba(0,0,0,.25); overflow:hidden; border:1px solid #1f2937; }}
        .header {{ padding:16px 20px; border-bottom:1px solid #1f2937; }}
        .title {{ margin:0; font-size:20px; color:#f8fafc; }}
        .meta {{ margin-top:6px; font-size:12px; color:#94a3b8; }}
        .total {{ margin:12px 20px 0; background:#0ea5e9; color:#00131a; font-weight:800; display:inline-block; padding:8px 12px; border-radius:999px; font-size:14px; }}
        .total.up {{ background:#16a34a !important; }}
        .total.down {{ background:#dc2626 !important; }}
        .total.flat {{ background:#6b7280 !important; }}
        .content {{ padding:16px 20px 24px; }}
        
        /* Mobile-first table styles */
        table.dataframe {{ 
            border-collapse:collapse; 
            width:100%; 
            font-size:12px;
        }}
        table.dataframe th, table.dataframe td {{ 
            border:1px solid #374151; 
            padding:8px 6px; 
            text-align:left; 
            color:#fff; 
            word-wrap:break-word;
            max-width:120px;
        }}
        table.dataframe thead th {{ 
            background:#0f172a; 
            color:#cbd5e1; 
            border-bottom:2px solid #64748b; 
            font-size:11px;
        }}
        table.dataframe tbody tr:nth-child(odd) {{ background:#0b1324; }}
        a {{ color:#7dd3fc; }}
        .footer {{ color:#64748b; font-size:11px; text-align:center; padding:12px; }}
        
        /* Mobile-specific improvements */
        @media (max-width: 768px) {{
            .header {{ padding:12px 16px; }}
            .title {{ font-size:18px; }}
            .meta {{ font-size:11px; }}
            .total {{ 
                margin:10px 16px 0; 
                padding:6px 10px; 
                font-size:13px;
                display:block;
                text-align:center;
            }}
            .content {{ padding:12px 16px 20px; }}
            
            /* Make table scrollable horizontally on mobile */
            .table-container {{
                overflow-x:auto;
                -webkit-overflow-scrolling:touch;
                margin:0 -16px;
                padding:0 16px;
            }}
            
            table.dataframe {{
                font-size:11px;
                min-width:500px; /* Ensure minimum width for readability */
            }}
            
            table.dataframe th, table.dataframe td {{
                padding:6px 4px;
                font-size:10px;
            }}
            
            table.dataframe thead th {{
                font-size:10px;
            }}
            
            .footer {{
                font-size:10px;
                padding:10px;
            }}
        }}
        
        /* Extra small screens */
        @media (max-width: 480px) {{
            .header {{ padding:10px 12px; }}
            .title {{ font-size:16px; }}
            .total {{
                margin:8px 12px 0;
                padding:5px 8px;
                font-size:12px;
            }}
            .content {{ padding:10px 12px 16px; }}
            
            table.dataframe {{
                font-size:10px;
            }}
            
            table.dataframe th, table.dataframe td {{
                padding:4px 3px;
                font-size:9px;
            }}
            
            table.dataframe thead th {{
                font-size:9px;
            }}
        }}
    </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
        <h1 class="title">Daily Portfolio Summary</h1>
        <div class="meta">{today_str}</div>
        </div>
        <div class="{total_class}">{total_badge}</div>
        <div class="content">
        <div class="table-container">
        {table_html}
        </div>
        </div>
        <div class="footer">Automatic message • HL Price Update</div>
    </div>
    </body>
    </html>
    """
    return html