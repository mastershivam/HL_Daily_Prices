from pull_and_collate import create_data_frame
import pandas as pd
import os
from datetime import date
import locale
from html_summary import build_html_summary
from history_summary import load_previous_snapshot
from send_email import maybe_send_email
from notifier import maybe_send_push


def format_push_message(total: float, previous_total: float | None) -> str:
    message = f"Portfolio total: GBP {total:,.2f}"
    if previous_total is None:
        return message

    diff = total - previous_total
    if previous_total == 0:
        return f"{message} ({diff:+,.2f})"

    pct = (diff / previous_total) * 100.0
    return f"{message} ({diff:+,.2f}, {pct:+.2f}%)"

def main():
    # Try to set locale, but don't fail if it doesn't work
    for loc in ('en_GB.UTF-8', 'en_US.UTF-8', 'C.UTF-8', 'C'):
        try:
            locale.setlocale(locale.LC_ALL, loc)
            print(f"Locale set to: {loc}")
            break
        except locale.Error:
            continue
    else:
        print("Warning: Could not set locale, using system default")

    # Check for debug mode via environment variable
    debug_mode = os.getenv('DEBUG', 'false').lower() in ('true', '1', 'yes')
    
    data = create_data_frame(debug=debug_mode)
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
    
    
    previous_total, _ = load_previous_snapshot(today_str, data.index.tolist())

    subject = f"Daily Portfolio Summary - {today_str}"
    push_message = format_push_message(total, previous_total)
    maybe_send_push(subject, push_message)
    maybe_send_email(subject, html_summary)
    
    
if __name__ == "__main__":
    main()
