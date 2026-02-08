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

| | Dátum | Kategória | Popis | # PLN | # CZK | # EUR | # Total CZK |
|---|------|----------|-------------|-----------|-----------|-----------|-----------|
| _(A: empty)_ | 1.2.2026 | Potraviny | Albert | | 658 | | 658 |

- Column A is empty (the table starts at column B)
- The bot writes to columns A–G (where A is always blank)
- **Total CZK** (column H) must be a formula — the bot copies it from the previous row

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

See **[DEPLOY_RAILWAY.md](./DEPLOY_RAILWAY.md)** for a detailed step-by-step guide covering:

- Creating a Railway project from this repo
- Setting all environment variables
- Encoding `credentials.json` as base64 for cloud deployment
- Testing with dry-run mode
- Troubleshooting common issues
- Migrating to your home server later

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
