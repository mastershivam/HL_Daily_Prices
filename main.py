from pull_and_collate import create_data_frame
import pandas as pd
import os
from datetime import date
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv

def env(name):
    v = os.getenv(name, "")
    return v.strip() if isinstance(v, str) else v

load_dotenv()
EMAIL_FROM = env('EMAIL_ADDRESS')
APP_PASSWORD = env('EMAIL_APP_PASSWORD')
RECIPIENTS = [env('EMAIL_RECIPIENTS')]
SMTP_SERVER=env('SMTP_HOST')
SMTP_PORT=int(env('SMTP_PORT'))



def assert_env():
    missing = [n for n,v in {"SMTP_HOST":SMTP_SERVER, "SMTP_PORT":SMTP_PORT, "EMAIL_ADDRESS":EMAIL_FROM,
    "EMAIL_APP_PASSWORD":APP_PASSWORD, "EMAIL_ADRESS":EMAIL_FROM}.items() if not v]
    if missing:
        raise RuntimeError(f"Missing SMTP env vars: {', '.join(missing)}")

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

def maybe_send_email(subject: str, html_body: str):
    """
    Send the summary via HTML email if SMTP vars are set.
    Required ENV: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO
    """
    
    

    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = RECIPIENTS

    with smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT)) as s:
        s.starttls()
        s.login(EMAIL_FROM, APP_PASSWORD)
        s.send_message(msg)

def main():
    data = create_data_frame()
    total = data['value'].sum()
    print(total)

    filename = 'daily_totals.csv'
    today_str = date.today().isoformat()

    # Prepare row data for CSV
    fund_values = data['value'].to_dict()
    row_dict = {'date': today_str, 'total': total}
    row_dict.update(fund_values)

    if os.path.exists(filename):
        df = pd.read_csv(filename)
        for fund in fund_values.keys():
            if fund not in df.columns:
                df[fund] = pd.NA
        if today_str in df['date'].values:
            for key, value in row_dict.items():
                df.loc[df['date'] == today_str, key] = value
        else:
            df = pd.concat([df, pd.DataFrame([row_dict])], ignore_index=True)
    else:
        df = pd.DataFrame([row_dict])

    df.to_csv(filename, index=False)

    # --- HTML summary ---
    html_summary = build_html_summary(data, total, today_str)
    out_dir = "summaries"
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, f"daily_summary-{today_str}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_summary)

    # Keep a rolling "latest" file too
    with open(os.path.join(out_dir, "latest.html"), "w", encoding="utf-8") as f:
        f.write(html_summary)

    # Optional email
    subject = f"Daily Portfolio Summary — {today_str}"
    maybe_send_email(subject, html_summary)

if __name__ == "__main__":
    main()