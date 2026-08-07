# HL Daily Prices

Automates a daily portfolio snapshot using Hargreaves Lansdown prices. It reads your holdings, scrapes current prices, computes portfolio values, stores a rolling history in `daily_totals.csv`, renders an HTML summary (with a trend sparkline and unrealised P&L), and can notify you by push and optionally email.

## Current behavior

- `python main.py` is the main entrypoint.
- The GitHub Actions workflow runs the same entrypoint on a schedule.
- Holdings data is expected in `HL_Daily_Prices_Data/units.csv` when running in automation, or a local `units.csv` in the repo root otherwise.
- Outputs are written locally to:
  - `daily_totals.csv`
  - `summaries/daily_summary-YYYY-MM-DD.html`
  - `summaries/latest.html`
- If the whole run fails (network down, HL page unreachable, etc.), you still get a push notification telling you it failed, instead of just a silent gap in history.

## Recording investments (no more hand-editing units.csv)

`units.csv` holds your *current* position and is what each run reads, but you shouldn't edit it directly anymore. Instead there's a `transactions.csv` log (date, fund, units, price paid, amount) and `units.csv` is regenerated from it - so the units figure is always a sum of real purchases, and you get a real cost basis per fund (not just a bare units count) for free.

One-time setup, if you already have a `units.csv`:

```bash
python invest.py --seed
```

This turns your existing holdings into "opening balance" transactions with unknown cost basis (price paid before tracking started isn't recoverable - P&L just starts tracking from here).

Recording a top-up:

```bash
# Fetches the live price and works out units bought
python invest.py "Baillie Gifford Japanese" --amount 500

# Or record an exact fill from your contract note
python invest.py "Baillie Gifford Japanese" --units 12.34 --price 40.52
```

Both append a transaction to `transactions.csv` and regenerate `units.csv` automatically. The fund must already have a row in `units.csv` so `invest.py` knows which URL/ticker to price it against.

### Renaming a fund

Don't edit the fund name directly in `units.csv` - it silently orphans that fund's `daily_totals.csv` history column (a new column starts under the new name, the old one just stops updating). Use:

```bash
python rename_fund.py "Old Fund Name" "New Fund Name"
```

This updates `units.csv`, `transactions.csv`, and merges the history column in `daily_totals.csv` in one go. (`main.py` also logs a warning if it detects funds vanishing and appearing in the same run, in case a rename slips through anyway.)

## Tracking listed shares

`units.csv` supports an optional `type` column (`fund` or `share`, defaults to `fund`). For `type=share` rows, the `url` column holds a Yahoo Finance ticker (e.g. `ELIX.L`) instead of an HL page URL, and the price is fetched via `yfinance` instead of HL scraping - useful since HL's share pages are scraped less reliably than fund pages by the regex parser here.

Separately, `WATCHLIST_TICKERS` (comma-separated Yahoo symbols, in `.env` or as a secret) shows reference quotes alongside your total without them being holdings - e.g. `WATCHLIST_TICKERS=ELIX.L,VOD.L`. Defaults to `ELIX.L` if unset, matching the old hardcoded behaviour.

## Key files

- `main.py` orchestrates the run and sends a failure push notification if anything throws.
- `pull_and_collate.py` loads holdings, scrapes HL/yfinance, and builds the portfolio DataFrame. Validates `units.csv` (no duplicate funds, no zero/negative units, valid `type` values) and returns which funds failed to price.
- `transactions.py` / `invest.py` / `rename_fund.py` - the investment tracking workflow described above.
- `persistence.py` updates daily history, loads prior snapshots, and loads recent totals for the sparkline.
- `html_summary.py` builds the HTML report (total, DoD change, unrealised P&L, watchlist quotes, failed-fund warnings, trend sparkline).
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

- Copy your private `units.csv` into `HL_Daily_Prices_Data/units.csv`, or keep a local `units.csv` in the repo root if you're not using the private data-repo layout.
- `sample_units.csv` is an example shape only.
- Run `python invest.py --seed` once to start tracking cost basis from your existing holdings.

Expected columns in `units.csv`:

- `fund`
- `units`
- `url`
- `type` (optional: `fund` or `share`, defaults to `fund`)

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

Reference-ticker watchlist (optional, defaults to `ELIX.L`):

```env
WATCHLIST_TICKERS=ELIX.L,VOD.L
```

4. Run it.

```bash
python main.py
```

## Testing

Run the lightweight verification suite locally:

```bash
python -m py_compile main.py config.py persistence.py notifications.py pull_and_collate.py price_scraper.py html_summary.py utilities.py transactions.py invest.py rename_fund.py
pytest
```

The tests cover stable helpers only: history lookup, push formatting, price parsing, currency/share-type inference, transaction math, retry behaviour, `units.csv` validation, and deterministic transformation logic. They do not hit live network services.

## GitHub Actions

The workflow in `.github/workflows/daily.yml`:

- checks out this repo
- installs dependencies
- clones the private data repo (which should contain `units.csv` and, if you're using it, `transactions.csv`)
- seeds prior `daily_totals.csv` history if available
- runs `python main.py`
- uploads outputs as artifacts
- commits refreshed outputs back to the private data repo

Required secrets for the current workflow:

- `DATA_REPO_TOKEN`
- `NTFY_TOPIC`
- optional `NTFY_BASE_URL`
- optional `NTFY_TOKEN`
- optional `WATCHLIST_TICKERS`

## Notes

- Generated outputs and local/private data are intentionally ignored by git.
- If you use `ntfy.sh`, a reserved topic plus `NTFY_TOKEN` is the secure setup. A public guessable topic is not.
- Email is optional. If SMTP settings are not present, email sending is skipped.
- Network calls (HL scraping, yfinance, FX rates) retry transiently a couple of times before giving up.
- Unrealised P&L is only shown for funds where every transaction has a known amount - it's intentionally left blank rather than guessed for funds seeded from an old `units.csv` via `invest.py --seed`.
- `layouts/` and `templates/` are leftover empty directories from before `html_summary.py` moved to plain f-string HTML - safe to delete by hand, they're not used or git-tracked.
