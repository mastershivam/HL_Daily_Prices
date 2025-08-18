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
    
    html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            h1 {{ color: #333; }}
            table.dataframe {{
                border-collapse: collapse;
                width: 100%;
            }}
            table.dataframe th, table.dataframe td {{
                border: 1px solid #ddd;
                padding: 8px;
                text-align: left;
            }}
            table.dataframe th {{
                background-color: #f2f2f2;
            }}
            tr:hover {{ background-color: #f9f9f9; }}
        </style>
    </head>
    <body>
        <h1>Daily Portfolio Summary — {today_str}</h1>
        <h2>Total: £{total:,.2f}</h2>
        {table_html}
    </body>
    </html>
    """
    return html