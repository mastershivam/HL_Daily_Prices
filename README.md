# HL Daily Prices

Automates a daily portfolio snapshot using Hargreaves Lansdown prices. It reads your holdings, scrapes current prices, computes portfolio values, stores a rolling history in `daily_totals.csv`, renders an HTML summary, and can notify you by push and optionally email.

## Current behavior

- `python main.py` is the main entrypoint.
- The GitHub Actions workflow runs the same entrypoint on a schedule.
- Holdings data is expected in `HL_Daily_Prices_Data/units.csv` when running in automation.
- Outputs are written locally to:
  - `daily_totals.csv`
  - `summaries/daily_summary-YYYY-MM-DD.html`
  - `summaries/latest.html`

## Key files

- `main.py` orchestrates the run.
- `pull_and_collate.py` loads holdings, scrapes HL, and builds the portfolio DataFrame.
- `persistence.py` updates daily history and loads prior snapshots.
- `html_summary.py` builds the HTML report.
- `notifications.py` formats and sends push/email notifications.
- `.github/workflows/daily.yml` runs the scheduled job.

## Local setup

1. Create and activate a virtual environment.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Provide holdings data.

- Copy your private `units.csv` into `HL_Daily_Prices_Data/units.csv`, or adapt the path if you are running differently.
- `sample_units.csv` is an example shape only.

Expected columns in `units.csv`:

- `fund`
- `units`
- `url`

3. Optional notification config in `.env`.

Push via `ntfy`:

```env
NTFY_BASE_URL=https://ntfy.sh
NTFY_TOPIC=your_reserved_or_random_topic
NTFY_TOKEN=your_token_if_required
```

Email via SMTP:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASS=your_app_password
EMAIL_FROM=your_email@example.com
EMAIL_TO=recipient@example.com
```

4. Run it.

```bash
python main.py
```

## Testing

Run the lightweight verification suite locally:

```bash
python -m py_compile main.py config.py persistence.py notifications.py pull_and_collate.py price_scraper.py html_summary.py
pytest
```

The tests cover stable helpers only: history lookup, push formatting, price parsing, and deterministic transformation logic. They do not hit live network services.

## GitHub Actions

The workflow in `.github/workflows/daily.yml`:

- checks out this repo
- installs dependencies
- clones the private data repo
- seeds prior `daily_totals.csv` history if available
- runs `python main.py`
- uploads outputs as artifacts
- commits refreshed outputs back to the private data repo

Required secrets for the current workflow:

- `DATA_REPO_TOKEN`
- `NTFY_TOPIC`
- optional `NTFY_BASE_URL`
- optional `NTFY_TOKEN`

## Notes

- Generated outputs and local/private data are intentionally ignored by git.
- If you use `ntfy.sh`, a reserved topic plus `NTFY_TOKEN` is the secure setup. A public guessable topic is not.
- Email is optional. If SMTP settings are not present, email sending is skipped.
