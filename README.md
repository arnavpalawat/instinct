# Instinct — Daily Financial Briefing

Automated daily financial briefing pipeline that collects market data, news, and deal activity, then generates an AI-written briefing delivered via email and published to GitHub Pages.

## Setup

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `GROQ_API_KEY` | Groq API key for LLM generation |
| `FINNHUB_API_KEY` | Finnhub API key for market data |
| `FRED_API_KEY` | FRED API key for economic data |
| `FMP_API_KEY` | Financial Modeling Prep API key |
| `SMTP_HOST` | SMTP server hostname (e.g., `smtp.gmail.com`) |
| `SMTP_PORT` | SMTP port (`587` for STARTTLS, `465` for SSL) |
| `SMTP_USER` | SMTP login username |
| `SMTP_PASSWORD` | SMTP password or app password |
| `SMTP_FROM` | Sender email address |
| `RECIPIENT_EMAIL` | Email address to receive briefings |

### SMTP Setup

Gmail with an App Password is recommended:

1. Enable 2-Step Verification on your Google account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a new app password for "Mail"
4. Use `smtp.gmail.com` / port `587` / the generated password

### GitHub Pages

1. Go to repo **Settings > Pages**
2. Set source to **Deploy from a branch**
3. Select the `gh-pages` branch, root folder
4. The workflow will auto-create the `gh-pages` branch on first run

## Schedule

The pipeline runs daily at **8:00 AM CDT** (13:00 UTC) via GitHub Actions.

> **Note:** The cron is set to `0 13 * * *` (UTC). During CST (Nov–Mar), this is 7:00 AM CT. Adjust to `0 14 * * *` if you want 8:00 AM CST year-round.

### Manual Trigger

Go to **Actions > Daily Briefing > Run workflow**. You can optionally override the date or enable dry-run mode.

### Changing the Run Time

Edit `.github/workflows/daily_briefing.yml` and update the cron expression. Use [crontab.guru](https://crontab.guru) to verify your schedule. Remember the cron is in UTC.

## Local Development

```bash
cp .env.example .env
# Fill in API keys in .env
pip install -r requirements.txt
python -m src.pipeline --dry-run
```
