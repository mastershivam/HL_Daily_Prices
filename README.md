# **HL Daily Prices**

>Automates a daily portfolio snapshot using Hargreaves Lansdown (HL) prices.
>Combines your instrument list + units, computes values, saves CSV/HTML summaries, and (optionally) emails a neat daily report. Runs locally or on GitHub Actions.

## Features:
- Scrapes HL fund/share prices (handles £, $, and p formats)
- Merges with your units & URLs
- Computes per‑instrument value and total portfolio value
- Saves daily_totals.csv and an HTML daily summary
- Sends the summary via SMTP (Gmail/Outlook etc.)
- Scheduled via GitHub Actions
- Supports keeping data files private in a separate repo

## How it works

- pull_and_collate.py → create_data_frame() returns a DataFrame indexed by instrument name with columns like units, sell, value, …
- main.py:
	- builds today’s table and total
	- writes/updates daily_totals.csv
	- generates summaries/daily_summary-YYYY-MM-DD.html
	- emails the HTML summary (if SMTP env vars are set)

## Repo structure (key files)

├─ main.py                  # Entry point: build + save + email daily summary

├─ pull_and_collate.py      # Pricing + dataframe assembly

├─ requirements.txt         # Runtime dependencies

├─ .github/workflows/       # GitHub Actions workflow(s)

├─ .gitignore               # Ignores data and generated files

└─ summaries/               # (generated) Daily HTML summaries (gitignored)

Note: CSV/HTML/log files are gitignored so the public repo doesn’t leak data.

## **Setup (local)**
1. Python env

        python -m venv .venv
        source .venv/bin/activate   # macOS/Linux
        # .venv\Scripts\activate    # Windows
        pip install -r requirements.txt

2. Environment variables
	Create a .env in the repo root (not committed) with one of the following sets:

	Generic SMTP

        SMTP_HOST=smtp.gmail.com
        SMTP_PORT=587
        SMTP_USER=your_email@example.com
        SMTP_PASS=your_app_password
        EMAIL_FROM=your_email@example.com
        EMAIL_TO=recipient1@example.com,recipient2@example.com

	Alternate names (supported automatically)

        EMAIL_ADDRESS=your_email@example.com
        EMAIL_APP_PASSWORD=your_app_password
        EMAIL_RECIPIENTS=recipient@example.com

3. Run

        python main.py

### *Keep data files private (recommended)*

- Put confidential files (e.g., units.csv, urls.csv) in a separate private repo, e.g. HL_Daily_Prices_Data.
- Create a fine‑grained PAT with Contents: Read-only for that repo.
- In your public repo’s workflow, clone the private repo at runtime and copy the files:

### *Outputs*
- daily_totals.csv — running table keyed by date (YYYY-MM-DD) with total and per‑instrument values
- summaries/daily_summary-YYYY-MM-DD.html — styled HTML summary
- summaries/latest.html — last run’s summary (overwritten each run)

### *Troubleshooting*

*SMTP auth fails / NoneType.encode or (334, 'Password:'):*
- Ensure env names match; main.py accepts either SMTP_* or EMAIL_ADDRESS/EMAIL_APP_PASSWORD/EMAIL_RECIPIENTS.
- Use an App Password (Gmail/Outlook) and starttls() on port 587.

*Locale errors on GitHub Actions:*
- The code avoids locale.atof—prices are parsed by stripping £,$,p, and commas. No locale needed.

*USD/GBP/pence parsing:*
- Handled in code; p prices are converted to pounds, $ handled as USD with currency column and conversion if configured.

*Files not found when copying from the private repo:*
- Check the path; if your files are in a subfolder, update the cp commands accordingly.

*Security notes*
- Secrets are stored in GitHub Actions → Secrets.
- For full historical scrubbing (if you ever committed data), use git filter-repo.

License: MIT
