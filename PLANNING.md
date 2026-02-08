# Telegram Expense Bot - Research & Planning

## 1. Project Overview

**Goal:** A Telegram bot that accepts expense inputs (banking app screenshots or free-form text), parses them using AI, and logs them into an existing Google Sheet for monthly spending analysis by category.

**Key Constraints (all confirmed):**
- **Banks:** Czech, Slovak, and Polish banks + Revolut
- **Languages in screenshots:** English, Czech, Slovak (mixed)
- **Text input language:** Slovak (primary), free-form
- **Currencies:** CZK (primary), PLN, EUR - sheet auto-converts to CZK via formula
- **Categories:** Data validation dropdown in the Google Sheet, **in Slovak language**
- **Sheet structure:** `Date | Category | Description | Amount PLN | Amount CZK | Amount EUR | Total CZK`
- **Sheet organization:** Monthly tabs in `MM/YYYY` format (e.g., "02/2026", "03/2026")
- **Total CZK column:** Formula (auto-calculated) - bot must never write to it
- **Users:** Two users - you and your wife (both whitelisted by Telegram user ID)
- **Operations:** Add expenses only (no edit/delete)
- **Utility commands:** `/summary`, `/last`, `/undo`, `/categories` - all requested
- **Bot interface:** English
- **Interactivity:** If category is ambiguous, bot sends a Telegram single-choice poll for the user to pick
- **Code quality:** Statically typed Python (type hints everywhere, `mypy --strict`, Pydantic models)
- **Error handling:** Full error messages sent to user + comprehensive server-side logging
- **Hosting:** Self-hosted on a Proxmox mini-PC (no dedicated GPU)
- **LLM:** Cloud API required (no GPU for local inference)
- **Secrets:** Docker `.env` file + mounted `credentials.json` (see section 5.2)

**Core Flow:**
```
User (you or wife) sends message (image or text)
  Text input typically in Slovak
  Screenshots in English, Czech, or Slovak
        |
        v
  Telegram Bot receives it
  (checks user is whitelisted)
        |
        v
  AI/LLM parses expense data
  (date, category, description, amount, currency)
  Categories (Slovak) loaded from Google Sheet dropdown
        |
        v
  Missing info? ──Yes──> Ask follow-up question(s)
        |                  (e.g. inline keyboard for category)
       No                       |
        |                  User replies
        v <─────────────────────┘
  Find correct monthly tab (e.g. "02/2026")
  Write row to correct currency column
  Leave Total CZK for the formula
        |
        v
  Confirm to user with summary
  Log the operation
        |
  On error → send full error message to user + log
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
│  │  │   category=null → Telegram poll             │  │ │
│  │  │   amount=null   → "What was the amount?"    │  │ │
│  │  │   all fields ok → confirm + write           │  │ │
│  │  └──────────────────┬──────────────────────────┘  │ │
│  │                     │                              │ │
│  │                     v                              │ │
│  │  ┌─────────────────────────────────────────────┐  │ │
│  │  │   Google Sheets Writer (gspread)            │  │ │
│  │  │                                             │  │ │
│  │  │   Appends row to correct monthly tab:        │  │ │
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
| **Category** | String | Yes | Must match one of the Slovak categories from the data validation dropdown |
| **Description** | String | Yes | Merchant name, payee, or expense description |
| **Amount PLN** | Number | Conditionally | Only filled if currency is PLN |
| **Amount CZK** | Number | Conditionally | Only filled if currency is CZK |
| **Amount EUR** | Number | Conditionally | Only filled if currency is EUR |
| **Total CZK** | Formula | **Never** | Auto-converts PLN/EUR to CZK. Bot must never touch this column. |

**Sheet organization: Monthly tabs (`MM/YYYY` format)**
- Each month has its own tab/worksheet named in `MM/YYYY` format (e.g., "02/2026", "03/2026", "12/2025")
- The bot must determine the correct tab based on the expense date (not necessarily today's date - a user might log a past expense)
- Tab name is derived as: `expense_date.strftime("%m/%Y")` → e.g., `"02/2026"`
- If the tab doesn't exist yet (e.g., logging the first expense of a new month), the bot should handle this gracefully (error message asking the user to create the tab, or optionally auto-create it)

**Important implementation details:**
- The bot must write the amount into exactly **one** of the three currency columns and leave the other two empty/blank
- The `Total CZK` column is a **confirmed formula** - the bot must **never overwrite it**. When appending rows, leave column G empty; the formula should auto-populate (or the user may need to drag it down)
- **Formula handling caveat:** When appending a new row, the formula in `Total CZK` may not auto-extend. Options:
  1. The user drags the formula down manually (simplest, but annoying)
  2. The bot copies the formula from the previous row's `Total CZK` cell into the new row (recommended - use `gspread` to read the formula from the last row and replicate it)
  3. Use an `ARRAYFORMULA` in the sheet header so it auto-extends (best UX, but requires a one-time sheet change)
- Categories are in **Slovak** and come from a **data validation dropdown** - the bot reads the dropdown options via the Sheets API

### 3.3 Category Management (Slovak, Data Validation Dropdown)

Categories are defined as a **data validation dropdown** in the Google Sheet, written in **Slovak**. Example categories might include: "Potraviny", "Stravovanie", "Doprava", "Bývanie", "Zábava", "Oblečenie", "Zdravie", etc.

**Reading categories from data validation:**
- The Google Sheets API can read data validation rules via `spreadsheets.get` with `includeGridData=true` or via the `dataValidation` field
- `gspread` does not have a direct method for this, but you can use the underlying `spreadsheets.get` API call
- Alternatively, if the data validation references a range (e.g., `Categories!A:A`), the bot can read that range directly (simpler)
- **Implementation approach:** Try to read data validation rules first; if that's complex, read unique values from the Category column of existing rows as a fallback

**Bot behavior:**
1. **On startup:** Read the list of valid categories from the sheet (data validation range or unique existing values), cache them in memory
2. **During parsing:** The LLM receives the full Slovak category list in its prompt so it can match "obed v reštaurácii" → "Stravovanie"
3. **If LLM is uncertain:** Send a **Telegram single-choice poll** with all categories for the user to pick (see section 3.6)
4. **Cache refresh:** On `/categories` command or periodically (every hour). The `/categories` command also serves as a way to display the current list
5. **Language bridge:** The LLM must understand that user text input is in Slovak, categories are in Slovak, but the bot interface (confirmations, error messages) is in English

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
You are an expense parser. The user tracks expenses in a Google Sheet.

INPUT:
- Text messages are typically in SLOVAK language (sometimes Czech or English)
- Images are banking app screenshots from Czech, Slovak, or Polish banks, or Revolut
- Screenshots may be in English, Czech, or Slovak

EXTRACT these fields:
- date: in YYYY-MM-DD format. Default to {today} if not specified.
- amount: numeric value (use dot as decimal separator, no thousand separators)
- currency: one of "CZK", "PLN", "EUR". Default to "CZK" if ambiguous.
  Recognize: Kč=CZK, zł=PLN, €=EUR.
- category: one of these EXACT Slovak values: [{categories_from_sheet}]
  Match the expense to the best category. The categories are in Slovak.
  If unsure, set to null.
- description: merchant name, payee, or brief description of the expense

Handle Czech/Slovak/Polish number formatting:
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
Do NOT include any text outside the JSON object.
```

**Example interactions:**
| User Input (Slovak text) | Parsed Output |
|--------------------------|---------------|
| "obed 185 Kč" | `{date: today, amount: 185, currency: "CZK", category: "Stravovanie", description: "obed"}` |
| "Lidl nákup 1250" | `{date: today, amount: 1250, currency: "CZK", category: "Potraviny", description: "Lidl"}` |
| "uber z letiska 45€" | `{date: today, amount: 45, currency: "EUR", category: "Doprava", description: "Uber z letiska"}` |
| [screenshot from banking app] | `{date: "2026-02-05", amount: 890, currency: "CZK", category: "Oblečenie", description: "H&M"}` |

**Follow-up question flow:**
- If `category` is null → send a **Telegram single-choice poll** with all Slovak categories (see section 3.6)
- If `amount` is null → ask "What was the amount?"
- If `currency` is null → ask "What currency?" with CZK/PLN/EUR inline keyboard buttons
- If `description` is null → ask "What was this expense for?"
- If all fields present → show confirmation summary, then write to sheet

### 3.6 Interactive Category Selection (Telegram Poll)

When the LLM cannot confidently determine the category, the bot sends a **Telegram single-choice poll** so the user can tap to pick.

**Telegram Poll API: `sendPoll`**
- `question`: e.g., "What category is this expense? (Albert, 450 CZK)"
- `options`: list of Slovak category names
- `is_anonymous`: `false` (so the bot can see who voted)
- `allows_multiple_answers`: `false` (single-choice)
- `type`: `"regular"` (not quiz)

**Telegram Poll limitations and workarounds:**

| Constraint | Limit | Workaround |
|-----------|-------|------------|
| Max options per poll | **10** | If more than 10 categories, split into "pages" or use inline keyboard as fallback |
| Option text length | 100 chars | Slovak category names should be well under this |
| Question text length | 300 chars | Include partial expense info in the question for context |
| Poll lifetime | Stays until manually closed | Bot should listen for the answer and auto-close / ignore subsequent votes |

**Implementation approach:**

```
LLM returns category=null
        │
        v
  How many categories?
        │
   ┌────┴────┐
  ≤10       >10
   │         │
   v         v
 Single    Paginated polls OR
 poll      inline keyboard fallback
   │
   v
 User taps an option
   │
   v
 Bot receives PollAnswer update
 (via poll_answer handler)
   │
   v
 Map selected option back to category name
 Continue with expense writing
```

**Why a poll instead of inline keyboard buttons?**
- Polls are more visually prominent and native-feeling on mobile
- Single tap to answer (no need to scroll through a long button list)
- The user explicitly requested this interaction pattern

**Fallback for >10 categories:**
If there are more than 10 categories, the bot has two options:
1. **LLM pre-filtering:** Ask the LLM to return its top 5-8 best guesses instead of null, then poll with just those + an "Other" option. If user picks "Other", send a second poll with the remaining categories. (Recommended)
2. **Inline keyboard:** Fall back to an inline keyboard with all categories arranged in a 2-column grid. No option limit.

**Poll answer handling (python-telegram-bot):**
- Register a `PollAnswerHandler` to receive poll responses
- The bot must maintain a mapping: `poll_id → pending_expense` so when the answer comes in, it knows which expense to complete
- This mapping should be in-memory (dict) since the bot only serves 2 users; no need for a database
- Clean up old mappings after a timeout (e.g., 1 hour) to avoid memory leaks

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

## 5. Security & Secret Management

### 5.1 General Security

1. **Restrict bot access** - Whitelist exactly two Telegram user IDs (you and your wife) via `ALLOWED_USER_IDS` env var. Reject all other users with a polite "unauthorized" message.
2. **No financial data stored on server** - Parse and forward to Google Sheets, don't keep a local database of expenses.
3. **Image handling** - Process in memory, don't persist banking screenshots to disk.
4. **Google Sheet permissions** - Service account should only have access to the specific spreadsheet.

### 5.2 Secret Management

There are **4 secrets** this application needs:

| Secret | What It Is | Format |
|--------|-----------|--------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | String: `110201543:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw` |
| `GEMINI_API_KEY` | API key from Google AI Studio | String: `AIzaSy...` |
| `GOOGLE_SHEET_ID` | Spreadsheet ID from the Google Sheets URL | String: `1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms` |
| `GOOGLE_CREDENTIALS` | Google service account credentials | JSON (entire file content or file path) |

Plus **2 non-secret config values:**

| Config | What It Is | Format |
|--------|-----------|--------|
| `ALLOWED_USER_IDS` | Telegram user IDs for you and your wife | Comma-separated: `123456789,987654321` |
| `DEFAULT_CURRENCY` | Fallback currency | String: `CZK` |

#### Recommended Approach: Docker `.env` file + mounted credentials file

This is the simplest approach for a self-hosted Docker setup on your Proxmox server.

**How it works:**

```
expense-bot/
├── .env                  # ← All secrets here (gitignored)
├── credentials.json      # ← Google service account key (gitignored)
├── docker-compose.yml    # ← References .env and mounts credentials.json
└── ...
```

**Step 1:** Create the `.env` file on the server (never commit this):

```bash
# .env (on the server only, never in git)
TELEGRAM_BOT_TOKEN=110201543:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw
GEMINI_API_KEY=AIzaSyA1B2C3D4E5F6G7H8I9J0
GOOGLE_SHEET_ID=1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms
GOOGLE_CREDENTIALS_FILE=/app/credentials.json
ALLOWED_USER_IDS=123456789,987654321
DEFAULT_CURRENCY=CZK
LOG_LEVEL=INFO
```

**Step 2:** Place the `credentials.json` (Google service account key) alongside `.env` on the server.

**Step 3:** Docker Compose mounts both:

```yaml
services:
  expense-bot:
    build: .
    container_name: expense-bot
    restart: unless-stopped
    env_file: .env                                     # ← injects all env vars
    volumes:
      - ./credentials.json:/app/credentials.json:ro    # ← mounts creds as read-only
```

**Step 4:** The Python app reads them:

```python
import os
from google.oauth2.service_account import Credentials

# Simple env var reads (validated by AppConfig dataclass)
bot_token: str = os.environ["TELEGRAM_BOT_TOKEN"]
gemini_key: str = os.environ["GEMINI_API_KEY"]

# Google credentials from mounted file
creds = Credentials.from_service_account_file(
    os.environ["GOOGLE_CREDENTIALS_FILE"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"],
)
```

#### Alternative: Embed credentials JSON as env var (no file mount)

If you prefer not to deal with file mounts, the Google credentials JSON can be base64-encoded into an env var:

```bash
# .env
GOOGLE_CREDENTIALS_BASE64=eyJ0eXBlIjoic2VydmljZV9hY2NvdW50Iiw...  # base64 of credentials.json
```

```python
import base64, json, os
from google.oauth2.service_account import Credentials

creds_json = json.loads(base64.b64decode(os.environ["GOOGLE_CREDENTIALS_BASE64"]))
creds = Credentials.from_service_account_info(creds_json, scopes=[...])
```

**Pros:** No file mount needed, purely env-var driven, easier to move between hosts.
**Cons:** Slightly more complex setup (base64 encoding step), harder to inspect/debug.

#### What gets committed to Git vs what stays on the server

| File | In Git? | Notes |
|------|---------|-------|
| `.env.example` | Yes | Template with placeholder values, no real secrets |
| `.env` | **No** (`.gitignore`) | Real secrets, only on the server |
| `credentials.json` | **No** (`.gitignore`) | Service account key, only on the server |
| `docker-compose.yml` | Yes | References `.env` and `credentials.json` but contains no secrets |

#### How to initially get secrets onto the server

1. **SSH into the Proxmox LXC/VM** where the bot will run
2. **Clone the repo:** `git clone <repo-url> && cd expense-bot`
3. **Create `.env`:** `cp .env.example .env && nano .env` → fill in real values
4. **Copy credentials.json:** `scp` from your local machine, or paste via the Proxmox console
5. **Start:** `docker compose up -d`

That's it. No external secret manager needed for a self-hosted personal project with 2 users.

### 5.3 Error Handling & Logging Strategy

**Requirement:** Full error messages sent to the user in Telegram + comprehensive server-side logging.

### Error Handling (User-Facing)

Every error should result in a clear Telegram message to the user containing:
- What operation failed (e.g., "Failed to parse expense", "Failed to write to Google Sheet")
- The actual error message / exception details
- A suggestion for what to try next

Example error messages:
```
❌ Error: Failed to parse expense from image.
Details: Gemini API returned 429 (rate limit exceeded)
Suggestion: Please try again in a minute.

❌ Error: Failed to write to Google Sheet.
Details: Worksheet "02/2026" not found.
Suggestion: Please create the tab in the spreadsheet, or send the expense again.

❌ Error: Could not determine expense amount.
Details: LLM returned null for amount field.
Suggestion: Please specify the amount, e.g. "lunch 250 CZK"
```

### Logging (Server-Side)

Use Python's `logging` module with structured output:

| Level | What Gets Logged |
|-------|-----------------|
| **INFO** | Every successful expense added (user, date, amount, currency, category, description, sheet tab) |
| **INFO** | Bot startup, shutdown, category cache refresh |
| **WARNING** | Missing fields requiring follow-up, rate limit retries |
| **ERROR** | API failures (Gemini, Google Sheets, Telegram), parsing failures, unexpected exceptions |
| **DEBUG** | Raw LLM responses, full request/response details (for development) |

**Log format:**
```
2026-02-08 14:23:45 [INFO] Expense added: user=@jansvehla date=2026-02-08 amount=450.00 currency=CZK category=Potraviny description="Albert" sheet="02/2026"
2026-02-08 14:25:12 [ERROR] Gemini API error: 500 Internal Server Error. User=@wife. Input="obed 185kc". Traceback: ...
```

**Docker logging:**
- Logs go to stdout/stderr (Docker captures them automatically)
- Configure Docker log rotation in `docker-compose.yml` to prevent disk fill:
  ```yaml
  logging:
    driver: "json-file"
    options:
      max-size: "10m"
      max-file: "3"
  ```
- View logs via `docker compose logs -f expense-bot`

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
| **Phase 1** | **Bot skeleton + Google Sheets** | Bot setup with user whitelist (2 users), gspread connection, read categories from data validation dropdown, find correct monthly tab | 2-3 hours |
| **Phase 2** | **Text expense parsing** | Gemini integration, Slovak text input → structured JSON, write to correct currency column in correct monthly tab | 2-3 hours |
| **Phase 3** | **Image expense parsing** | Handle photos, send to Gemini Vision, extract expense from Czech/Slovak/English banking screenshots | 2-3 hours |
| **Phase 4** | **Follow-up questions** | Conversation state for missing fields, inline keyboards for Slovak category selection & currency, confirm before writing | 2-3 hours |
| **Phase 5** | **Utility commands** | `/summary` (monthly totals by category), `/last` (last N expenses), `/undo` (remove last), `/categories` (list + refresh cache) | 2-3 hours |
| **Phase 6** | **Error handling & logging** | Full error messages to user, structured logging (INFO/WARNING/ERROR), graceful handling of API failures, missing tabs, rate limits | 1-2 hours |
| **Phase 7** | **Docker deployment** | Dockerfile, docker-compose.yml with log rotation, .env config, health checks, README with setup instructions | 1-2 hours |

**Total estimated effort: ~12-19 hours**

### Phase 1 details (foundation):
1. Bot skeleton with `python-telegram-bot` v21+, long polling
2. User whitelist middleware (rejects unauthorized users)
3. Google Sheets connection via `gspread` + service account
4. Read categories from data validation dropdown (Slovak) and cache in memory
5. Locate correct monthly tab by name (e.g., "02/2026")

### Phase 2 details (core feature):
1. Receive Slovak text → send to Gemini with system prompt containing cached Slovak categories
2. Parse JSON response → validate fields
3. Write row: `Date | Category | Description | (amount in correct currency column) | (leave Total CZK empty for formula)`
4. Handle the Total CZK formula (copy from previous row or rely on ARRAYFORMULA)
5. Send confirmation message to user

### Phase 5 details (utility commands):
- `/summary` or `/summary 02/2026` → read all rows from a monthly tab, aggregate by category, format as a table
- `/last` or `/last 5` → show the last N expenses added (from current month tab)
- `/undo` → remove the last row added to the current month tab (with confirmation)
- `/categories` → list all categories from cache, refresh from sheet
- `/help` → show all available commands

---

## 8. All Requirements (Finalized)

All questions have been answered. Here is the complete requirements summary:

| # | Requirement | Decision |
|---|-------------|----------|
| 1 | Bank apps / languages | Czech, Slovak, Polish banks + Revolut. Screenshots in English, Czech, or Slovak. |
| 2 | Text input language | **Slovak** (primary) |
| 3 | Expense categories | Data validation dropdown in Google Sheet, **in Slovak language**. Bot reads them dynamically. |
| 4 | Currency | Primary: CZK. Also PLN and EUR. Sheet auto-converts to CZK via formula. |
| 5 | Google Sheet structure | `Date | Category | Description | Amount PLN | Amount CZK | Amount EUR | Total CZK` |
| 6 | Total CZK column | **Formula** (auto-calculated). Bot never writes to it. |
| 7 | Sheet organization | **Monthly tabs** in `MM/YYYY` format (e.g., "02/2026") |
| 8 | Users | **Two users**: you and your wife. Both whitelisted by Telegram user ID. |
| 9 | Operations | **Add only**. No edit/delete via bot. |
| 10 | Utility commands | **Yes, all**: `/summary`, `/last`, `/undo`, `/categories` |
| 11 | Bot interface language | **English** |
| 12 | Error handling | **Full error messages** sent to user in Telegram + comprehensive server-side logging |
| 13 | Code quality | **Statically typed** Python: type hints, `mypy --strict`, Pydantic v2 models |
| 14 | Category interaction | **Telegram single-choice poll** when category is ambiguous |
| 15 | Tab naming | **`MM/YYYY`** format (e.g., "02/2026") |
| 16 | Secret management | Docker `.env` file + mounted `credentials.json` (see section 5.2) |
| 17 | Server specs | Proxmox mini-PC, no dedicated GPU. Multiple apps already hosted. |
| 18 | Hosting preference | Self-hosted on the mini-PC, Docker in LXC container. |

### Pre-Implementation Setup Checklist

Before coding can begin, these manual steps are needed:

- [ ] **Create Telegram bot** via @BotFather → get bot token
- [ ] **Get Telegram user IDs** for both you and your wife (e.g., message @userinfobot)
- [ ] **Create Google Cloud project** (free) → enable Google Sheets API
- [ ] **Create service account** → download credentials JSON
- [ ] **Share Google Sheet** with the service account email (Editor permission)
- [ ] **Get Gemini API key** from Google AI Studio (free)
- [ ] **Note the Google Sheet ID** (from the URL: `docs.google.com/spreadsheets/d/{SHEET_ID}/...`)
- [x] **Tab naming convention** confirmed: `MM/YYYY` format (e.g., "02/2026")

---

## 9. Code Quality: Static Typing

**Requirement:** All Python code must be statically typed.

### Approach

- **Type hints on all functions:** parameters and return types annotated
- **`mypy --strict`** used for static analysis during development (or at minimum `mypy --disallow-untyped-defs`)
- **Pydantic v2** for runtime-validated data models (parsed expense, config) - this also provides JSON schema generation for LLM structured output
- **`dataclasses`** for simple internal data structures where Pydantic is overkill
- **`TypeAlias`** and `Literal` types for constrained values (e.g., `Currency = Literal["CZK", "PLN", "EUR"]`)

### Data Models (Typed)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


# Constrained types
Currency = Literal["CZK", "PLN", "EUR"]


class ParsedExpense(BaseModel):
    """Structured output from the LLM parser. Fields may be None if
    the LLM could not determine them (triggers follow-up questions)."""

    date: date | None = None
    amount: float | None = None
    currency: Currency | None = None
    category: str | None = None
    description: str | None = None


class Expense(BaseModel):
    """A fully validated expense ready to be written to Google Sheets.
    All fields are required (non-None)."""

    date: date
    amount: float = Field(gt=0)
    currency: Currency
    category: str
    description: str


@dataclass
class PendingExpense:
    """Tracks an expense that is mid-conversation (waiting for user
    to fill in missing fields via poll or text reply)."""

    user_id: int
    chat_id: int
    parsed: ParsedExpense
    poll_id: str | None = None
    created_at: float = field(default_factory=lambda: 0.0)  # time.time()


@dataclass
class AppConfig:
    """Application configuration loaded from environment variables."""

    telegram_bot_token: str
    allowed_user_ids: list[int]
    gemini_api_key: str
    google_sheet_id: str
    google_credentials_path: str
    default_currency: Currency = "CZK"
    log_level: str = "INFO"
```

### Type Checking in CI / Development

```bash
# Run mypy (add to Makefile or pre-commit hook)
mypy bot/ --strict --ignore-missing-imports

# Or use pyproject.toml:
[tool.mypy]
strict = true
ignore_missing_imports = true
plugins = ["pydantic.mypy"]
```

### Additional dev dependencies

```
# dev-requirements.txt
mypy>=1.10
types-Pillow
pydantic>=2.0            # Also a runtime dependency - replaces plain dataclasses for validated models
```

**Why Pydantic in addition to dataclasses?**
- `ParsedExpense` and `Expense` benefit from Pydantic's validation (e.g., `amount > 0`, `currency` is one of 3 values)
- Pydantic can parse the LLM's JSON response directly into a `ParsedExpense` object with validation
- Pydantic's `.model_json_schema()` could be used to generate a JSON schema to include in the LLM prompt (improves structured output reliability)
- `dataclass` is used for simpler internal state (`PendingExpense`, `AppConfig`) that doesn't need runtime validation

---

## 10. Final Recommended Stack

Based on the research and your confirmed requirements:

| Component | Choice | Why |
|-----------|--------|-----|
| **Language** | Python 3.12+ | Best ecosystem for AI + Telegram + Google APIs |
| **Type System** | mypy --strict + Pydantic v2 | Static typing throughout; Pydantic for validated LLM response models |
| **Bot Framework** | python-telegram-bot v21+ | Best conversation handler + poll support, handles follow-up question flows natively |
| **LLM** | Gemini 2.0 Flash (primary) | Free tier covers personal use at $0/month. Good Czech/Slovak vision+text parsing. |
| **LLM Fallback** | GPT-4o-mini | If Gemini has outages or quality issues. ~$0.50/month. |
| **Google Sheets** | gspread + service account | Simplest, most reliable. Reads categories dynamically. |
| **Hosting** | Proxmox mini-PC, Docker in LXC container | $0/month, long polling (no port forwarding), fits existing infra. |
| **Deployment** | Docker Compose | Auto-restart, env var management, easy updates. |
| **Secrets** | Docker `.env` + mounted credentials JSON | Simple, no external secret manager needed for personal project. |

**Total running cost: $0/month**

### Python Dependencies

```
# requirements.txt (runtime)
python-telegram-bot[ext]>=21.0    # Telegram bot framework with extras (includes httpx, etc.)
google-generativeai>=0.8.0        # Gemini API client (google.generativeai)
gspread>=6.0                      # Google Sheets API wrapper
google-auth>=2.0                  # Service account authentication
pydantic>=2.0                     # Typed data models with validation (LLM response parsing)
Pillow>=10.0                      # Image handling (resize before sending to LLM)
python-dotenv>=1.0                # Environment variable management
```

```
# dev-requirements.txt (development only)
mypy>=1.10                        # Static type checking (run with --strict)
types-Pillow                      # Type stubs for Pillow
```

### Environment Variables

See **section 5.2** for the full secret management approach. Summary:

```bash
# .env file (on server only, gitignored)
TELEGRAM_BOT_TOKEN=...                    # From @BotFather
GEMINI_API_KEY=...                        # From Google AI Studio
GOOGLE_SHEET_ID=...                       # Spreadsheet ID from URL
GOOGLE_CREDENTIALS_FILE=/app/credentials.json  # Mounted via Docker volume
ALLOWED_USER_IDS=123456789,987654321      # Your and wife's Telegram user IDs
DEFAULT_CURRENCY=CZK                      # Default currency if ambiguous
LOG_LEVEL=INFO                            # DEBUG for development
```

### Project Structure

```
expense-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Entry point, bot setup, long polling
│   ├── config.py            # Configuration from env vars
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py      # /start, /help, /summary, /last, /undo, /categories
│   │   ├── expense.py       # Text + image expense handlers, conversation flow
│   │   └── auth.py          # User whitelist middleware
│   ├── services/
│   │   ├── __init__.py
│   │   ├── llm_parser.py    # Gemini API integration, prompt building, JSON parsing
│   │   ├── sheets.py        # Google Sheets: read categories, find tab, write row, read summary
│   │   └── categories.py    # Category cache management
│   └── models.py            # Expense dataclass, parsing result model
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example             # Template for secrets (committed)
├── .env                     # Actual secrets (gitignored)
├── credentials.json         # Service account key (gitignored)
└── README.md                # Setup + deployment instructions
```

### Docker Compose

```yaml
services:
  expense-bot:
    build: .
    container_name: expense-bot
    restart: unless-stopped
    env_file: .env
    volumes:
      - ./credentials.json:/app/credentials.json:ro
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```
