import pandas as pd

def build_html_summary(data: pd.DataFrame, total: float, today_str: str) -> str:
    # Convert index to column for display
    df_display = data.reset_index().rename(columns={"index": "Fund/Share"})
    
    # Format columns
    if "value" in df_display.columns:
        df_display["value"] = df_display["value"].apply(lambda v: f"£{v:,.2f}")
    if "sell" in df_display.columns:
        df_display["sell"] = df_display["sell"].fillna("").astype(str)

    # HTML table
    table_html = df_display.to_html(index=False, border=0, classes="dataframe", escape=False)
    

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
        .total {{ margin:16px 24px 0; background:#0ea5e9; color:#00131a; font-weight:800; display:inline-block; padding:10px 14px; border-radius:999px; }}
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
        <div class="total">Total: £{total:,.2f}</div>
        <div class="content">
        {table_html}
        </div>
        <div class="footer">Automatic message • HL Price Update</div>
    </div>
    </body>
    </html>
    """
    return html