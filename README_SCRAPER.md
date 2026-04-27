# Scraper Pack

This folder contains a set of standalone scrapers plus a runner script `run_scrapers.py`.

The scrapers write `*_raw.json` files to the current working directory. These output files are ignored by git via `.gitignore`.

## Requirements

- macOS/Linux
- Python 3.9+ (recommended: 3.10/3.11)
- For Playwright-based scrapers: Playwright + Chromium browser install

## Setup

Create a virtual environment (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install Playwright browser (needed for `scraper_combined_pw.py` and `scraper_socialmediatoday_pw.py`):

```bash
python -m playwright install chromium
```

## Credentials / Secrets

Important: do NOT commit any credentials to git.

### X/Twitter (`scraper.py`)

`scraper.py` requires authenticated cookies for X GraphQL endpoints.

Provide cookies via either:

1) Environment variables:

```bash
export X_AUTH_TOKEN="..."
export X_CT0="..."
export X_TWID="u%3D..."   # optional
```

2) A local JSON file (recommended): `x_cookies.json` in the same directory (already gitignored),

```json
{
  "auth_token": "YOUR_AUTH_TOKEN",
  "ct0": "YOUR_CT0",
  "twid": "u%3D123..."
}
```

You can also set a custom path:

```bash
export X_COOKIES_FILE="/abs/path/to/x_cookies.json"
```

How to obtain cookies (manual):

1. Log in to [https://x.com](https://x.com) in your browser.
2. Open DevTools -> Application/Storage -> Cookies -> `https://x.com`.
3. Copy values for `auth_token`, `ct0`, and (optional) `twid`.

If cookies are missing, `scraper.py` will error with:
`Missing X/Twitter cookies ...`

## Quick Start

Run all scrapers in parallel (best effort, each has its own retries/timeouts):

```bash
python3 run_scrapers.py
```

Run one scraper:

```bash
python3 scraper_reuters.py
python3 scraper_reddit.py
python3 scraper_newsletter.py
python3 scraper_combined_pw.py
python3 scraper.py
```

## Outputs

`run_scrapers.py` runs multiple scripts and then prints a summary of any `*_raw.json` files it finds.

Common output files:

- `tweets_raw.json` (from `scraper.py`)
  - Object with fields: `collected_at`, `since`, `total_kept`, `account_stats`, `tweets`
  - Incremental state: `scraper_state.json` (gitignored)
- `reuters_raw.json` (from `scraper_reuters.py`)
  - Object with fields: `collected_at`, `source`, `items`
- `reddit_raw.json` (from `scraper_reddit.py`)
  - Array of records
  - Incremental state: `reddit_state.json` (gitignored)
  - Logs: `warnings.log`, `test_output.txt` (gitignored)
- `newsletter_raw.json` (from `scraper_newsletter.py`)
  - Array of records
  - Notes: it will try to auto-install `feedparser` if missing
- `techcrunch_raw.json` and `socialmediatoday_raw.json` (from `scraper_combined_pw.py`)
  - Objects with `items` arrays

## Notes / Troubleshooting

- Playwright scrapers may get blocked by Cloudflare or change in site structure; re-run later or adjust selectors.
- X/Twitter endpoints and query IDs can change; errors like 401/403 usually indicate invalid/expired cookies.
- `run_scrapers.py` uses a 300s timeout per script and retries once on failure.

## Repository Intent

This repository is intended to include only:

- `run_scrapers.py`
- `scraper.py`
- `scraper_*.py`
- `requirements.txt`
- `README_SCRAPER.md`
- `.gitignore`

All produced data files (`*_raw.json`) and local credential files are intentionally excluded.

