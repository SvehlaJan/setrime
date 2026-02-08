# Railway Deployment Guide

Step-by-step guide to deploy the Expense Bot on [Railway](https://railway.app) for temporary (or permanent) cloud hosting.

**Estimated time:** 10–15 minutes.
**Cost:** Free trial ($5 credit, lasts ~2 weeks for this bot), then ~$1–3/month.

---

## Prerequisites

Before you start, have these ready:

- [ ] This repo pushed to **GitHub** (public or private)
- [ ] **Telegram bot token** from @BotFather
- [ ] **Telegram user IDs** for you and your wife (from @userinfobot)
- [ ] **Gemini API key** from [Google AI Studio](https://aistudio.google.com/apikey)
- [ ] **Google Sheet ID** from your spreadsheet URL
- [ ] **credentials.json** (Google service account key file) on your local machine

---

## Step 1: Create a Railway Account

1. Go to [railway.app](https://railway.app)
2. Sign up with your **GitHub account** (this makes repo linking automatic)
3. You get **$5 free trial credit** — no credit card required

---

## Step 2: Create a New Project

1. From the Railway dashboard, click **"New Project"**
2. Select **"Deploy from GitHub Repo"**
3. Find and select your **setrime** repository (or whatever you named it)
4. Railway will detect the `Dockerfile` and `railway.toml` automatically

> Railway will start a build immediately, but it will **fail** because environment variables are not set yet. That's expected — we'll fix it in the next step.

---

## Step 3: Set Environment Variables

1. Click on the **service** (the box that appeared after step 2)
2. Go to the **"Variables"** tab
3. Click **"Raw Editor"** (top-right) to paste all variables at once
4. Paste the following (replace the placeholder values with your real ones):

```
TELEGRAM_BOT_TOKEN=110201543:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
ALLOWED_USER_IDS=123456789,987654321
GEMINI_API_KEY=AIzaSyA1B2C3D4E5F6G7H8I9J0
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
DEFAULT_CURRENCY=CZK
LOG_LEVEL=INFO
DRY_RUN=false
```

5. Click **"Update Variables"**

---

## Step 4: Add Google Credentials (Base64)

Railway doesn't support file mounts, so we encode `credentials.json` as a base64 string.

**On your local machine** (Linux/Mac terminal or Git Bash on Windows):

```bash
# Encode the credentials file
base64 -w0 credentials.json
```

This outputs a long string like `eyJ0eXBlIjoic2VydmljZV9hY2NvdW50Iiw...`

> **Windows (PowerShell):** Use `[Convert]::ToBase64String([IO.File]::ReadAllBytes("credentials.json"))` instead.

**In Railway:**

1. Go back to the **Variables** tab
2. Add a new variable:
   - **Key:** `GOOGLE_CREDENTIALS_BASE64`
   - **Value:** paste the entire base64 string from above
3. Click **"Update Variables"**

> The bot auto-detects this variable and decodes it at startup. No `GOOGLE_CREDENTIALS_FILE` needed in the cloud.

---

## Step 5: Deploy

After setting all variables, Railway will automatically trigger a new deployment.

1. Go to the **"Deployments"** tab to watch the build progress
2. The build takes about 1–2 minutes (installs Python dependencies)
3. Once deployed, check the **logs** (click on the deployment → "View Logs")

You should see:

```
2026-02-08 14:00:00 [INFO] bot.config: Starting Expense Bot...
2026-02-08 14:00:01 [INFO] bot.services.sheets: Connected to Google Sheet: Expenses
2026-02-08 14:00:02 [INFO] bot.services.categories: Category cache refreshed: 14 categories loaded
2026-02-08 14:00:02 [INFO] bot.main: Bot is running (long polling). Authorized users: [123456789, 987654321]
```

---

## Step 6: Test the Bot

1. Open Telegram and message your bot
2. Send `/start` — you should get the welcome message
3. Send `/categories` — should list your 14 Slovak categories
4. Try a test expense: `obed 185 Kč`
5. Try sending a banking screenshot

> **Tip:** Set `DRY_RUN=true` in Railway variables first to test parsing without writing to the sheet. Once satisfied, change it to `false`.

---

## Troubleshooting

### Build fails

- Check the **build logs** in the Deployments tab
- Most common: a typo in `railway.toml` or `Dockerfile` — these should work as-is from the repo

### Bot doesn't respond

- Check **runtime logs** for errors
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Verify `ALLOWED_USER_IDS` contains your Telegram user ID
- Make sure no other instance of the bot is running (e.g., on your local machine) — only one instance can poll at a time

### "Worksheet not found" error

- Make sure the monthly tab exists in your Google Sheet (e.g., `02/2026`)
- The bot uses `MM/YYYY` format for tab names

### "Permission denied" on Google Sheet

- Verify you shared the sheet with the service account email (`...@...iam.gserviceaccount.com`) as **Editor**
- Verify `GOOGLE_SHEET_ID` is correct (the long string from the URL)

### "Could not read data validation rules"

- This is a warning, not a fatal error — the bot falls back to reading unique category values from column C
- Categories will still work

---

## Managing the Deployment

### View logs

Click on the service → Deployments → latest deployment → "View Logs"

Or install the Railway CLI:
```bash
npm install -g @railway/cli
railway login
railway logs
```

### Update the bot

Just push to the GitHub branch — Railway auto-deploys on every push.

### Stop the bot temporarily

In Railway: click on the service → Settings → "Remove Service" (or just pause it).

### Restart

Deployments tab → "Redeploy" on the latest deployment.

---

## Cost Estimate

| Usage | Cost |
|-------|------|
| **Free trial** | $5 credit, lasts ~2–3 weeks for this bot |
| **After trial** | ~$1–3/month (Starter plan: $5/month with $5 included usage) |
| **Compute** | ~$0.50–1.50/month (always-on, minimal CPU/RAM) |
| **Network** | Negligible (text-only Telegram API calls) |

The bot uses <128MB RAM and negligible CPU. Railway bills by the second.

---

## Migrating to Home Server Later

When your Proxmox server is ready:

1. **Stop Railway:** Delete or pause the Railway service
2. **On Proxmox:**
   ```bash
   git clone <your-repo-url> expense-bot
   cd expense-bot
   cp /path/to/.env .env          # Create .env with your secrets
   cp /path/to/credentials.json . # Place the service account key
   docker compose up -d            # Start the bot
   ```
3. The bot token stays the same — it seamlessly switches from Railway to your server
4. **Verify:** Message the bot on Telegram, check it responds

> **Important:** Only one instance of the bot can run at a time (Telegram long polling). Make sure to stop Railway **before** starting the home server instance.
