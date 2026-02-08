# Telegram Expense Bot - Research & Planning

## 1. Project Overview

**Goal:** A Telegram bot that accepts expense inputs (banking app screenshots or free-form text), parses them using AI, and logs them into an existing Google Sheet for monthly spending analysis by category.

**Key Constraints (from requirements gathering):**
- **Banks:** Czech, Slovak, and Polish banks + Revolut
- **Languages in screenshots:** English, Czech, Slovak (mixed)
- **Currencies:** CZK (primary), PLN, EUR - the sheet converts everything to CZK
- **Categories:** Already defined in the Google Sheet (bot reads them dynamically)
- **Sheet structure:** `Date | Category | Description | Amount PLN | Amount CZK | Amount EUR | Total CZK`
- **Hosting:** Self-hosted on a Proxmox mini-PC (no dedicated GPU)
- **LLM:** Cloud API required (no GPU for local inference)

**Core Flow:**
```
User sends message (image or text)
  (in English, Czech, or Slovak)
        |
        v
  Telegram Bot receives it
        |
        v
  AI/LLM parses expense data
  (date, category, description, amount, currency)
  Categories are loaded from Google Sheet
        |
        v
  Missing info? ──Yes──> Ask follow-up question(s)
        |                  (e.g. inline keyboard for category)
       No                       |
        |                  User replies
        v <─────────────────────┘
  Write row to correct currency column
  in Google Sheet (Amount PLN / CZK / EUR)
        |
        v
  Confirm to user with summary
```

---

## 2. Component Research

### 2.1 Telegram Bot API & Frameworks

The Telegram Bot API is free, well-documented, and supports text messages, photos, inline keyboards (for category selection), and conversation state management.

| Framework | Language | Pros | Cons |
|-----------|----------|------|------|
| **python-telegram-bot** | Python | Most popular, excellent docs, built-in conversation handlers, async support | Slightly heavier than alternatives |
| **aiogram** | Python | Modern async-first, fast, good for production | Smaller community than python-telegram-bot |
| **Telegraf** | Node.js | Clean API, middleware-based, good TypeScript support | JS ecosystem dependency churn |
| **grammY** | TypeScript/Deno | Modern, type-safe, plugin ecosystem, great docs | Newer, smaller community |
| **teloxide** | Rust | Very fast, type-safe | Overkill for this use case, steeper learning curve |

**Recommendation:** **python-telegram-bot** (v20+) or **aiogram** (v3). Python is ideal here because the AI/ML ecosystem (LLM clients, OCR libraries) is Python-native. `python-telegram-bot` has the best conversation handler support for managing follow-up questions.

**Key Telegram Bot API features we need:**
- `getUpdates` / Webhooks for receiving messages
- `PhotoSize` / `getFile` for downloading images sent by the user
- `sendMessage` with `reply_markup` for inline keyboards (category selection)
- Conversation state management (for multi-step flows when info is missing)

### 2.2 Image Parsing / OCR for Banking Screenshots

Banking screenshots vary wildly by app, locale, and phone. We need to extract: amount, merchant/payee, date, and sometimes category.

| Approach | Cost | Accuracy | Notes |
|----------|------|----------|-------|
| **LLM Vision (GPT-4o, Claude, Gemini)** | $0.001-0.01/image | Excellent | Best approach - understands context, layout, and can extract structured data in one call. Can handle any bank app format. |
| **Google Cloud Vision API** | $1.50/1000 images | Good OCR, no understanding | Pure OCR - gives text blocks, you still need to parse/understand them. |
| **Tesseract (local OCR)** | Free | Moderate | Open-source, runs locally. Struggles with complex banking UI layouts, colored backgrounds, overlapping elements. |
| **AWS Textract** | ~$1.50/1000 pages | Good | Similar to Google Vision - good OCR but no semantic understanding. |
| **EasyOCR** | Free | Moderate | Python library, better than Tesseract for some layouts, supports many languages. |

**Recommendation:** **Use an LLM with vision capability directly.** This is the clear winner because:
1. Banking screenshots are not simple text documents - they have complex layouts, icons, colors
2. An LLM can understand context ("this number next to the dollar sign is the amount, not the account number")
3. One API call does both OCR and structured extraction (no pipeline of OCR -> parsing -> extraction)
4. It can handle any bank app without app-specific parsing rules

### 2.3 LLM Options (Best Cost-Value Ratio)

This is the most critical choice. We need a model that can:
- Parse images of banking screenshots (vision capability)
- Extract structured data from free-form text
- Be reliable and fast enough for real-time chat interaction

| Model | Vision | Input Cost (per 1M tokens) | Output Cost (per 1M tokens) | Image Cost | Quality | Notes |
|-------|--------|---------------------------|----------------------------|------------|---------|-------|
| **GPT-4o-mini** | Yes | $0.15 | $0.60 | ~$0.001/img | Very Good | **Best cost-value for this use case.** Great vision, structured output support. |
| **GPT-4o** | Yes | $2.50 | $10.00 | ~$0.01/img | Excellent | More capable but ~15x more expensive than mini. Overkill for expense parsing. |
| **Claude 3.5 Haiku** | Yes | $0.80 | $4.00 | ~$0.004/img | Very Good | Fast, good vision. Slightly more expensive than GPT-4o-mini. |
| **Claude 3.5 Sonnet** | Yes | $3.00 | $15.00 | ~$0.01/img | Excellent | Excellent but expensive for this task. |
| **Gemini 2.0 Flash** | Yes | $0.10 | $0.40 | ~$0.001/img | Good-Very Good | **Cheapest option.** Generous free tier (1500 req/day). Good vision. |
| **Gemini 1.5 Pro** | Yes | $1.25 | $5.00 | ~$0.005/img | Very Good | More capable than Flash but pricier. |
| **Llama 3.2 Vision (local)** | Yes | Free | Free | Free | Moderate | 11B or 90B params. Can run on mini-server but needs decent GPU. Quality may be insufficient. |
| **Qwen2-VL (local)** | Yes | Free | Free | Free | Moderate-Good | Open-source vision model. Needs GPU. |

**Cost Estimate for typical usage:**
- Assume 5-10 expenses/day, ~300/month
- GPT-4o-mini: ~$0.30-0.50/month
- Gemini 2.0 Flash: ~$0.10-0.30/month (possibly free within free tier)
- Local model: $0/month but requires GPU hardware and maintenance

**Recommendation (no local GPU available - cloud API required):** 
- **Primary: Gemini 2.0 Flash** - Best cost-value ratio. Free tier (1500 req/day) covers personal use entirely. Good vision and good Czech/Slovak language understanding. Google AI Studio API key is free.
- **Runner-up: GPT-4o-mini** - Slightly better structured output support (JSON mode), very cheap. ~$0.50/month for personal use. Excellent multilingual capabilities.
- ~~Self-hosted alternative~~ - Not viable without a GPU on the Proxmox mini-PC.

**Note on Czech/Slovak/Polish language support:** Both Gemini and GPT-4o-mini handle Central European languages well. They can read Czech banking screenshots (e.g., "Příchozí platba", "Odchozí platba", "Zůstatek") and extract structured data correctly. This should be validated with real screenshots during development.

### 2.4 Google Sheets Integration

| Method | Complexity | Notes |
|--------|-----------|-------|
| **Google Sheets API v4** (via `gspread` Python library) | Low | Most common approach. Uses service account or OAuth. `gspread` is the de-facto Python library. |
| **Google Sheets API v4** (direct REST) | Medium | More control, no extra dependency, but more boilerplate. |
| **Google Apps Script** (webhook) | Low-Medium | Deploy a web app in Google Apps Script that receives POST requests and writes to sheet. No Google Cloud project needed. |

**Authentication options:**
1. **Service Account** (recommended) - Create in Google Cloud Console, share the sheet with the service account email. No user interaction needed. Free.
2. **OAuth 2.0** - More complex, requires user consent flow. Better for multi-user but overkill for personal use.
3. **API Key** - Only works for public sheets. Not suitable.

**Recommendation:** **`gspread` + Service Account**. This is the simplest, most reliable approach for a personal bot. Steps:
1. Create a Google Cloud project (free)
2. Enable Google Sheets API
3. Create a service account and download credentials JSON
4. Share the Google Sheet with the service account email
5. Use `gspread` to read/append rows

### 2.5 Hosting: Self-Hosted on Proxmox Mini-PC (Confirmed)

| Aspect | Details |
|--------|---------|
| **Cost** | $0 ongoing (hardware already owned) |
| **Platform** | Proxmox - can run as LXC container or VM with Docker |
| **Connectivity** | Long polling mode - no public IP or port forwarding needed |
| **Bot Mode** | **Long polling** (`getUpdates`) - works behind NAT |
| **No GPU** | Local LLM not viable - must use cloud LLM API |

**Recommended deployment approach on Proxmox:**

1. **Option A: LXC container + Docker** (recommended)
   - Lightweight Debian/Ubuntu LXC container on Proxmox
   - Install Docker inside the LXC
   - Run the bot via `docker compose` with restart policy `unless-stopped`
   - Minimal resource usage (~128MB RAM, negligible CPU)

2. **Option B: Dedicated lightweight VM**
   - If Docker-in-LXC is problematic, use a small VM (512MB RAM, 1 core)
   - Same Docker Compose setup inside the VM

3. **Option C: Add to existing Docker host**
   - If you already have a Proxmox VM/LXC running Docker for other apps, just add this as another service in the compose stack

**Docker Compose will handle:**
- Automatic restart on failure (`restart: unless-stopped`)
- Environment variable management for API keys
- Log rotation
- Easy updates (`docker compose pull && docker compose up -d`)

---

## 3. Proposed Architecture

### 3.1 Architecture Diagram

```
┌────────────────────────────────────────────────────────┐
│                    Telegram                              │
│  User sends: photo (banking screenshot) or text message  │
│  (Czech / Slovak / English)                              │
└─────────────────────────┬──────────────────────────────┘
                          │ Long Polling
                          v
┌────────────────────────────────────────────────────────┐
│       Proxmox Mini-PC (Docker in LXC container)         │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │       Telegram Bot (python-telegram-bot v21+)      │ │
│  │                                                    │ │
│  │  ┌──────────────┐  ┌───────────────────────────┐  │ │
│  │  │ Text Handler  │  │ Image Handler             │  │ │
│  │  │ "lunch 250kc" │  │ (download photo → bytes)  │  │ │
│  │  └──────┬───────┘  └─────────────┬─────────────┘  │ │
│  │         │                        │                 │ │
│  │         v                        v                 │ │
│  │  ┌─────────────────────────────────────────────┐  │ │
│  │  │   LLM Parser (Gemini 2.0 Flash API)         │  │ │
│  │  │                                             │  │ │
│  │  │   System prompt includes:                   │  │ │
│  │  │   - Categories from Google Sheet (cached)   │  │ │
│  │  │   - CZK/PLN/EUR currency detection rules    │  │ │
│  │  │   - Czech/Slovak number format handling     │  │ │
│  │  │                                             │  │ │
│  │  │   Returns JSON:                             │  │ │
│  │  │   {date, amount, currency, category,        │  │ │
│  │  │    description}                             │  │ │
│  │  └──────────────────┬──────────────────────────┘  │ │
│  │                     │                              │ │
│  │                     v                              │ │
│  │  ┌─────────────────────────────────────────────┐  │ │
│  │  │   Conversation Manager                      │  │ │
│  │  │                                             │  │ │
│  │  │   category=null → inline keyboard           │  │ │
│  │  │   amount=null   → "What was the amount?"    │  │ │
│  │  │   all fields ok → confirm + write           │  │ │
│  │  └──────────────────┬──────────────────────────┘  │ │
│  │                     │                              │ │
│  │                     v                              │ │
│  │  ┌─────────────────────────────────────────────┐  │ │
│  │  │   Google Sheets Writer (gspread)            │  │ │
│  │  │                                             │  │ │
│  │  │   Appends row to correct month/sheet:       │  │ │
│  │  │   Date | Category | Description |           │  │ │
│  │  │   Amt PLN | Amt CZK | Amt EUR | (Total)    │  │ │
│  │  │                                             │  │ │
│  │  │   Writes amount to ONE currency column,     │  │ │
│  │  │   leaves others blank. Leaves Total CZK     │  │ │
│  │  │   for the sheet formula.                    │  │ │
│  │  └─────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘
                          │
                          v
┌────────────────────────────────────────────────────────┐
│              Google Sheets (existing)                    │
│                                                          │
│  Date | Category | Description | PLN | CZK | EUR | Tot  │
│  ─────┼──────────┼─────────────┼─────┼─────┼─────┼────  │
│  2/8  | Groceries| Albert      |     | 450 |     | 450  │
│  2/8  | Dining   | Restaurant  | 85  |     |     | 570  │
│  2/7  | Transport| Uber        |     |     | 12  | 315  │
└────────────────────────────────────────────────────────┘
```

### 3.2 Data Model (Existing Google Sheet)

The Google Sheet already exists with this exact structure. The bot must write to it, **not** create its own schema.

| Column | Type | Bot Writes? | Notes |
|--------|------|-------------|-------|
| **Date** | Date | Yes | Parsed from input; default to today |
| **Category** | String | Yes | Must match one of the categories already defined in the sheet |
| **Description** | String | Yes | Merchant name, payee, or expense description |
| **Amount PLN** | Number | Conditionally | Only filled if currency is PLN |
| **Amount CZK** | Number | Conditionally | Only filled if currency is CZK |
| **Amount EUR** | Number | Conditionally | Only filled if currency is EUR |
| **Total CZK** | Number/Formula | **No** | Likely a formula that auto-converts PLN/EUR to CZK. Bot should leave this column untouched. |

**Important implementation details:**
- The bot must write the amount into exactly **one** of the three currency columns and leave the other two empty/blank.
- The `Total CZK` column almost certainly has a conversion formula - the bot must **never overwrite it**. Instead, append rows and let the formula handle conversion.
- Categories must be read dynamically from the sheet (a dedicated column, sheet, or data validation range) so the user can manage them in the spreadsheet without touching the bot.

### 3.3 Category Management

Categories are already defined in the Google Sheet. The bot should:

1. **On startup (and periodically):** Read the list of valid categories from the sheet (e.g., from a "Categories" sheet/tab, a named range, or a data validation dropdown column).
2. **During parsing:** The LLM receives the category list in its prompt so it can match the expense to an existing category.
3. **If uncertain:** Present an inline keyboard with the category list so the user can tap to select.
4. **Cache the list** in memory and refresh it periodically or on a `/reload` command (avoids API calls on every expense).

### 3.4 Multi-Language Screenshot Parsing

Banking screenshots will be in **Czech, Slovak, or English**. This has specific implications:

- Czech/Slovak amounts use **comma as decimal separator** (e.g., `1 234,50 Kč`) and sometimes a space as thousand separator.
- Currency symbols vary: `Kč`, `CZK`, `PLN`, `zł`, `€`, `EUR`.
- Date formats vary: `DD.MM.YYYY` (Czech/Slovak), `DD/MM/YYYY`, `YYYY-MM-DD`.
- Revolut uses English UI with standard formatting.

The LLM prompt must explicitly instruct the model to:
- Handle Czech/Slovak/Polish locale formatting
- Normalize amounts to plain numbers (no thousand separators, dot as decimal)
- Detect the currency from context (symbol, bank name, or text cues)
- Output dates in a consistent format (e.g., `YYYY-MM-DD`)

### 3.5 LLM Prompt Strategy

The LLM should receive a structured system prompt like:

```
You are an expense parser for a Czech user who uses Czech, Slovak, Polish
banks and Revolut. Extract expense information from text messages or
banking app screenshots.

The input may be in English, Czech, or Slovak language.

Extract these fields:
- date: in YYYY-MM-DD format. Default to {today} if not specified.
- amount: numeric value (use dot as decimal separator, no thousand separators)
- currency: one of "CZK", "PLN", "EUR". Default to "CZK" if ambiguous.
  Recognize: Kč=CZK, zł=PLN, €=EUR.
- category: one of these exact values: [{categories_from_sheet}]
  Pick the best match. If unsure, set to null.
- description: merchant name, payee, or brief description of the expense

Handle Czech/Slovak number formatting:
- "1 234,50" means 1234.50
- "1.234,50" means 1234.50

Return ONLY a JSON object:
{
  "date": "YYYY-MM-DD",
  "amount": 123.45,
  "currency": "CZK",
  "category": "...",
  "description": "..."
}

For any field you cannot determine, set it to null.
```

**Follow-up question flow:**
- If `category` is null → show inline keyboard with all categories
- If `amount` is null → ask "What was the amount?"
- If `currency` is null → ask "What currency?" with CZK/PLN/EUR buttons
- If `description` is null → ask "What was this expense for?"
- If all fields present → confirm and write to sheet

---

## 4. Alternative Approaches Considered

### 4.1 No-Code / Low-Code Solutions

| Tool | Approach | Limitation |
|------|----------|------------|
| **n8n** (self-hosted) | Telegram trigger → AI node → Google Sheets node | Works well! But less flexible for conversation flow. Can self-host on the mini-server. |
| **Make.com** (Integromat) | Visual automation builder | Free tier limited to 1000 ops/month. Limited image handling. |
| **Zapier** | Telegram → GPT → Sheets | Expensive ($20+/mo for multi-step zaps), limited. |

**n8n** is worth mentioning since it can run on the same Proxmox server and has Telegram + Google Sheets + AI agent nodes. However, it's significantly less flexible for multi-turn conversations (follow-up questions when fields are missing) and the image handling + custom prompt logic would be harder to fine-tune. The custom Python bot is the better fit for this use case.

### 4.2 Existing Telegram Expense Bots

Several exist (e.g., @ExpenseBot, @FinancePlannerBot) but:
- None support banking screenshot OCR
- Limited/no Google Sheets integration
- Privacy concerns - your financial data goes to a third party
- Limited customization of categories

Building custom is the right call for this use case.

---

## 5. Security Considerations

1. **Restrict bot access** - Only allow your Telegram user ID to interact with the bot (whitelist by `chat_id`)
2. **Store credentials securely** - Service account JSON, API keys in environment variables or secrets manager, never in code
3. **No financial data stored on server** - Parse and forward to Google Sheets, don't keep a local database of expenses
4. **Image handling** - Process in memory, don't persist banking screenshots to disk
5. **Google Sheet permissions** - Service account should only have access to the specific sheet

---

## 6. Estimated Costs Summary

### Your Setup: Self-hosted Proxmox + Gemini 2.0 Flash
| Item | Monthly Cost |
|------|-------------|
| Hosting (Proxmox mini-PC, already owned) | $0 |
| LLM API (Gemini 2.0 Flash free tier, ~300 requests/month) | $0 |
| Google Sheets API (free quota: 300 requests/min) | $0 |
| Telegram Bot API | $0 |
| **Total** | **$0/month** |

### Fallback: If Gemini Free Tier Becomes Insufficient
| Item | Monthly Cost |
|------|-------------|
| LLM API (GPT-4o-mini, ~300 requests/month) | ~$0.30-0.50 |
| Everything else | $0 |
| **Total** | **~$0.50/month** |

---

## 7. Implementation Phases (Estimated Effort)

| Phase | Description | Details | Effort |
|-------|-------------|---------|--------|
| **Phase 1** | **Setup & text parsing** | Bot skeleton, Gemini integration, parse text expenses, write to Google Sheet with correct currency column | 3-4 hours |
| **Phase 2** | **Image parsing** | Handle photos, send to Gemini Vision, extract expense from Czech/Slovak/English banking screenshots | 2-3 hours |
| **Phase 3** | **Category management** | Read categories from Google Sheet, cache, include in LLM prompt, inline keyboard fallback | 1-2 hours |
| **Phase 4** | **Follow-up questions** | Conversation state for missing fields, inline keyboards for category/currency selection, confirm before writing | 2-3 hours |
| **Phase 5** | **Docker deployment** | Dockerfile, docker-compose.yml, .env config, test on Proxmox LXC | 1-2 hours |
| **Phase 6** | **Polish & extras** | Error handling, `/undo` command, `/summary` command, edge cases, testing with real screenshots | 2-3 hours |

**Total estimated effort: ~11-17 hours**

### Phase 1 details (most critical):
1. Create Telegram bot via @BotFather, get token
2. Set up Google Cloud service account, share sheet
3. Bot receives text → sends to Gemini → gets JSON → writes to correct column in sheet
4. Example: user sends "Albert 450 Kč" → bot writes `Date=today, Category=Groceries, Description=Albert, Amount CZK=450`

---

## 8. Answered Questions & Remaining Open Questions

### Answered (Requirements Confirmed)

| # | Question | Answer |
|---|----------|--------|
| 1 | Bank apps / languages | Czech, Slovak, Polish banks + Revolut. Screenshots in English, Czech, or Slovak. |
| 2 | Expense categories | Already defined in the Google Sheet. Bot reads them dynamically. |
| 3 | Currency | Primary: CZK. Also PLN and EUR. Sheet converts everything to CZK. |
| 4 | Google Sheet structure | Existing: `Date | Category | Description | Amount PLN | Amount CZK | Amount EUR | Total CZK` |
| 5 | Server specs | Proxmox mini-PC, no dedicated GPU. Multiple apps already hosted. |
| 6 | Hosting preference | Self-hosted on the mini-PC. |

### Remaining Questions (Nice to Clarify Before Implementation)

7. **Where in the Google Sheet are categories defined?** Options:
   - A separate "Categories" tab/sheet?
   - A column with data validation (dropdown)?
   - A named range?
   - The bot could also just read unique values from the "Category" column of existing rows.

8. **Total CZK column** - Is this a formula (auto-calculated) or manually entered? If it's a formula, the bot will leave it blank when appending rows and let the formula fill in. If manual, the bot would need exchange rates.

9. **Monthly sheet tabs or single sheet?** Does each month have its own tab (e.g., "January 2026", "February 2026") or is everything in one continuous sheet? This affects where the bot appends rows.

10. **Do you want the bot to be usable by just you, or also family members/partner?** (Affects user whitelist, potentially separate tracking.)

11. **Edit/delete via bot?** Or just adding expenses? (Editing is much more complex to implement.)

12. **Utility commands?** Would you like:
    - `/summary` - monthly totals by category
    - `/last` - show last N expenses added
    - `/undo` - remove last added expense
    - `/categories` - show current category list
    - Or keep it minimal (just send expense, get confirmation)?

13. **Bot interface language?** English? Czech? (The bot's replies and prompts, not the input parsing.)

---

## 9. Final Recommended Stack

Based on the research and your confirmed requirements:

| Component | Choice | Why |
|-----------|--------|-----|
| **Language** | Python 3.12+ | Best ecosystem for AI + Telegram + Google APIs |
| **Bot Framework** | python-telegram-bot v21+ | Best conversation handler support, handles follow-up question flows natively |
| **LLM** | Gemini 2.0 Flash (primary) | Free tier covers personal use at $0/month. Good Czech/Slovak vision+text parsing. |
| **LLM Fallback** | GPT-4o-mini | If Gemini has outages or quality issues. ~$0.50/month. |
| **Google Sheets** | gspread + service account | Simplest, most reliable. Reads categories dynamically. |
| **Hosting** | Proxmox mini-PC, Docker in LXC container | $0/month, long polling (no port forwarding), fits existing infra. |
| **Deployment** | Docker Compose | Auto-restart, env var management, easy updates. |

**Total running cost: $0/month**

### Python Dependencies (Preliminary)

```
python-telegram-bot[ext]>=21.0    # Telegram bot framework with extras
google-generativeai>=0.8.0        # Gemini API client
gspread>=6.0                      # Google Sheets API wrapper
google-auth>=2.0                  # Service account authentication
Pillow>=10.0                      # Image handling (resize before sending to LLM)
python-dotenv>=1.0                # Environment variable management
```

### Deployment Files Needed

```
expense-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Entry point, bot setup, polling
│   ├── handlers.py          # Telegram message/command handlers
│   ├── llm_parser.py        # LLM integration (Gemini/GPT)
│   ├── sheets.py            # Google Sheets read/write
│   ├── models.py            # Expense data model (dataclass)
│   └── config.py            # Configuration from env vars
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example             # Template for secrets
└── README.md
```
