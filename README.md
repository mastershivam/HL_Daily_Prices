# HL Daily Update (Playwright Automation)

**What it does**
- Logs in to Hargreaves Lansdown with Playwright (headless by default)
- Handles 2FA via TOTP (authenticator app) automatically, or prompts for SMS code
- Navigates to your Portfolio page and extracts Total value + Day change
- Emails you a short daily summary

## 1) Setup

```bash
cd hl_playwright_daily
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install  # installs browser binaries
```

Copy `.env.example` to `.env` and fill values:
- `HL_USERNAME`, `HL_PASSWORD`
- If you use an authenticator app for HL, put the Base32 `HL_TOTP_SECRET` (so the script can auto-generate codes)
- Configure SMTP settings if you want an email sent each morning

## 2) Run once to test
```bash
python hl_playwright_scraper.py
```

If you don’t set `HL_TOTP_SECRET`, the script will pause and ask you to paste the SMS/app code when it appears.

## 3) Schedule it (macOS/Linux cron)
```bash
crontab -e
# Every weekday at 07:30 (UK time)
30 7 * * 1-5 /path/to/python /path/to/hl_playwright_scraper.py
```

## 4) Troubleshooting
- Set `DEBUG=true` in `.env` to save screenshots and include a text snippet in the email if parsing fails.
- HL sometimes changes labels/selectors. If login fails, run in headed mode: set `HEADLESS=false` and watch what breaks.
- If your portfolio page uses different wording (e.g., “Day’s change”), send me the exact text and I’ll tighten the regex.

## Notes
- This is for personal use. Automated login may be against HL’s T&Cs—use at your discretion.
- Store your `.env` securely and never commit credentials.
- For Slack/Telegram delivery instead of email, replace the `send_email` function with a webhook/bot.
