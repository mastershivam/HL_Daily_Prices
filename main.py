from pull_and_collate import create_data_frame
import pandas as pd
import os
from datetime import date
import locale
from html_summary import build_html_summary
from send_email import maybe_send_email


def main():
    for loc in ('en_GB.UTF-8', 'en_US.UTF-8', 'C.UTF-8'):
        try:
            locale.setlocale(locale.LC_ALL, loc)
            break
        except locale.Error:
            continue

    data = create_data_frame()
    print(data)
    total = data['Total Holding Value'].sum()
    

    filename = 'daily_totals.csv'
    today_str = date.today().isoformat()

    # Prepare row data for CSV
    fund_values = data['Total Holding Value'].to_dict()
    row_dict = {'Date': today_str, 'Total': total}
    row_dict.update(fund_values)

    if os.path.exists(filename):
        df = pd.read_csv(filename)
        for fund in fund_values.keys():
            if fund not in df.columns:
                df[fund] = pd.NA
        if today_str in df['Date'].values:
            for key, value in row_dict.items():
                df.loc[df['Date'] == today_str, key] = value
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