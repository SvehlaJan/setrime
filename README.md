# Telegram Expense Bot

A Telegram bot that parses expenses from banking app screenshots (Czech, Slovak, Polish banks, Revolut) or free-form Slovak text messages and logs them to an existing Google Sheet.

## Features

- **Text input** — send a Slovak text message like `obed 185 Kč` and the bot parses it into a structured expense
- **Screenshot parsing** — send a banking app screenshot and the bot extracts amount, merchant, date, currency via Gemini Vision
- **Interactive category selection** — if the category is ambiguous, the bot sends a Telegram poll for you to pick
- **Multi-currency** — supports CZK, PLN, EUR with separate columns; the sheet's formula converts to CZK
- **Monthly tabs** — expenses are written to the correct `MM/YYYY` tab automatically
- **Utility commands** — `/summary`, `/last`, `/undo`, `/categories`, `/help`
- **Two-user access** — whitelisted for you and your wife

## Prerequisites

1. **Telegram bot token** — create a bot via [@BotFather](https://t.me/BotFather)
2. **Telegram user IDs** — message [@userinfobot](https://t.me/userinfobot) to get your numeric ID
3. **Gemini API key** — get one free at [Google AI Studio](https://aistudio.google.com/apikey)
4. **Google service account** — create in [Google Cloud Console](https://console.cloud.google.com):
   - Create a project, enable the Google Sheets API
   - Create a service account, download `credentials.json`
   - Share your Google Sheet with the service account email as Editor
5. **Google Sheet ID** — from the URL: `docs.google.com/spreadsheets/d/{SHEET_ID}/edit`

## Setup

```bash
# Clone the repo
git clone <repo-url> && cd expense-bot

# Create .env from template
cp .env.example .env
# Edit .env with your real values
nano .env

# Place the Google service account key
cp /path/to/your/credentials.json ./credentials.json

# Start with Docker Compose
docker compose up -d

# View logs
docker compose logs -f expense-bot
```

## Google Sheet Structure

The bot expects this exact column layout in each monthly tab (e.g., `02/2026`):

| Date | Category | Description | Amount PLN | Amount CZK | Amount EUR | Total CZK |
|------|----------|-------------|-----------|-----------|-----------|-----------|
| 08.02.2026 | Potraviny | Albert | | 450 | | 450 |

- The bot writes to columns A–F only
- **Total CZK** (column G) must be a formula — the bot copies it from the previous row

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Show all commands |
| `/categories` | List categories (refreshes from sheet) |
| `/summary` | Monthly totals by category (current month) |
| `/summary 01/2026` | Summary for a specific month |
| `/last` | Show last 5 expenses |
| `/last 10` | Show last 10 expenses |
| `/undo` | Remove the last expense from the current month |

## Dry-Run Mode

Set `DRY_RUN=true` in your `.env` to test the bot without writing to Google Sheets. The bot will parse expenses normally and show what it *would* write, but skip the actual sheet write.

```bash
# In .env
DRY_RUN=true
```

This is useful for:
- Testing the bot with real Telegram messages before going live
- Verifying LLM parsing quality
- Running in the cloud temporarily without risking bad data

## Cloud Deployment (Temporary)

If your home server isn't available, you can deploy to **Railway** for free/cheap:

### Railway (recommended for temporary hosting)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app), create a new project from the repo
3. Add environment variables in the Railway dashboard (same as `.env`):
   - `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GOOGLE_SHEET_ID`, `ALLOWED_USER_IDS`
   - For `GOOGLE_CREDENTIALS_FILE`: set `GOOGLE_CREDENTIALS_BASE64` instead (see below)
4. Deploy — Railway uses the included `railway.toml` and `Dockerfile`

**Handling credentials.json in the cloud** (no file mount available):

Set `GOOGLE_CREDENTIALS_BASE64` as an env var containing the base64-encoded credentials:

```bash
# On your local machine:
base64 -w0 credentials.json
# Copy the output and paste it as the GOOGLE_CREDENTIALS_BASE64 env var in Railway
```

The bot supports both methods: file path (`GOOGLE_CREDENTIALS_FILE`) and base64 (`GOOGLE_CREDENTIALS_BASE64`).

### Migrating from cloud to home server

1. Stop the Railway deployment (or delete the project)
2. On your Proxmox server: `git clone`, create `.env`, place `credentials.json`
3. `docker compose up -d`
4. The Telegram bot token stays the same — it seamlessly switches

## Development

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r dev-requirements.txt

# Run locally (set DRY_RUN=true in .env for safe testing)
python -m bot.main

# Run tests
python -m pytest tests/ -v

# Type checking
mypy bot/ --strict --ignore-missing-imports
```

## Architecture

See [PLANNING.md](./PLANNING.md) for the full research and planning document.
