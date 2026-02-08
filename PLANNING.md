# Telegram Expense Bot - Research & Planning

## 1. Project Overview

**Goal:** A Telegram bot that accepts expense inputs (banking app screenshots or free-form text), parses them using AI, and logs them into a Google Sheet for monthly spending analysis by category.

**Core Flow:**
```
User sends message (image or text)
        |
        v
  Telegram Bot receives it
        |
        v
  AI/LLM parses expense data
  (amount, category, merchant, date, notes)
        |
        v
  Missing info? ──Yes──> Ask follow-up question(s)
        |                       |
       No                  User replies
        |                       |
        v <─────────────────────┘
  Write row to Google Sheet
        |
        v
  Confirm to user
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

**Recommendation:** 
- **Primary: Gemini 2.0 Flash** - Best cost-value ratio. Free tier covers light personal use entirely. Good vision capabilities. Google AI Studio API key is free.
- **Runner-up: GPT-4o-mini** - Slightly better structured output support (JSON mode), very cheap. ~$0.50/month for personal use.
- **Self-hosted alternative: Llama 3.2 Vision 11B** - If the mini-server has a GPU with 8+ GB VRAM. Free but quality/reliability trade-off.

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

### 2.5 Hosting Options

#### Option A: Self-Hosted (Home Mini-Server)

| Aspect | Details |
|--------|---------|
| **Cost** | $0 ongoing (hardware already owned) |
| **Setup** | Docker container or systemd service |
| **Connectivity** | Needs stable internet. Can use polling (no public IP needed) or webhook (needs reverse proxy + domain/DDNS) |
| **Reliability** | Depends on home internet/power stability |
| **Maintenance** | You manage updates, monitoring, restarts |
| **Bot Mode** | **Long polling** recommended (no public IP/port forwarding needed) |

**Self-hosting notes:**
- Long polling mode (`getUpdates`) works great behind NAT - no need to expose ports
- Docker Compose for easy deployment and restart policies
- If the server has a GPU, could run a local LLM to avoid API costs entirely

#### Option B: Cloud Solutions

| Service | Free Tier | Monthly Cost | Notes |
|---------|-----------|-------------|-------|
| **Railway** | $5 free credit | ~$1-5/mo | Easy deployment, Docker support, always-on |
| **Fly.io** | 3 shared VMs free | $0-3/mo | Good free tier, global deployment |
| **Render** | Free web services (sleep after inactivity) | $0-7/mo | Free tier sleeps after 15min inactivity (bad for bot) |
| **Oracle Cloud Free Tier** | Always-free ARM VM (4 OCPU, 24GB RAM) | $0 | **Best free option.** Generous free forever tier. |
| **AWS Lambda + API Gateway** | 1M requests free/month | $0-1/mo | Serverless, webhook mode. Cold starts can be annoying. |
| **Google Cloud Run** | 2M requests free/month | $0-1/mo | Serverless, good integration with Google APIs. |
| **Hetzner Cloud** | None | ~$4/mo (CX22) | Cheap, reliable European VPS |
| **DigitalOcean** | None | $4-6/mo | Simple, reliable |

**Recommendation:**
- **If reliability matters most:** Oracle Cloud Free Tier (always-free VM) or your home mini-server with Docker
- **If simplicity matters most:** Railway or Fly.io
- **If cost matters most:** Home mini-server (already owned) or Oracle Cloud free tier

---

## 3. Proposed Architecture

### 3.1 Recommended Stack

```
┌─────────────────────────────────────────────┐
│                 Telegram                      │
│            (User sends message)               │
└──────────────────┬──────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────┐
│          Telegram Bot (Python)               │
│     python-telegram-bot v20+ (async)         │
│                                              │
│  ┌─────────────┐  ┌──────────────────────┐  │
│  │ Text Handler │  │ Image Handler        │  │
│  │             │  │ (download + encode)   │  │
│  └──────┬──────┘  └──────────┬───────────┘  │
│         │                    │               │
│         v                    v               │
│  ┌─────────────────────────────────────┐    │
│  │      LLM Service (Gemini/GPT)       │    │
│  │  - Parse expense from text/image    │    │
│  │  - Return structured JSON           │    │
│  │  - Identify missing fields          │    │
│  └──────────────┬──────────────────────┘    │
│                 │                            │
│                 v                            │
│  ┌─────────────────────────────────────┐    │
│  │    Conversation Manager             │    │
│  │  - If fields missing → ask user     │    │
│  │  - If complete → write to sheet     │    │
│  └──────────────┬──────────────────────┘    │
│                 │                            │
│                 v                            │
│  ┌─────────────────────────────────────┐    │
│  │    Google Sheets Writer             │    │
│  │    (gspread + service account)      │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

### 3.2 Data Model (Google Sheet Columns)

Suggested columns for the expense sheet:

| Column | Type | Source | Required |
|--------|------|--------|----------|
| Date | Date | Parsed from input or today's date | Yes |
| Amount | Number | Parsed from input | Yes |
| Currency | String | Parsed or default | Yes (can default) |
| Category | String | Parsed or asked | Yes |
| Merchant/Description | String | Parsed from input | Yes |
| Payment Method | String | Parsed or asked | No |
| Notes | String | User-provided or extracted | No |
| Source | String | "text" or "image" | Auto |
| Timestamp | DateTime | When recorded | Auto |

### 3.3 LLM Prompt Strategy

The LLM should receive a structured prompt like:

```
You are an expense parser. Extract the following fields from the user's
expense message (text or image):
- date (YYYY-MM-DD format, default to today if not specified)
- amount (numeric)
- currency (3-letter code, default to [USER_DEFAULT])
- category (one of: [USER_CATEGORIES])
- merchant (store/service name)
- payment_method (cash, credit card, debit card, etc.)
- notes (any additional context)

Return a JSON object. For any field you cannot determine, set it to null.
```

When fields are null, the bot asks the user follow-up questions, potentially using inline keyboards for categories.

---

## 4. Alternative Approaches Considered

### 4.1 No-Code / Low-Code Solutions

| Tool | Approach | Limitation |
|------|----------|------------|
| **n8n** (self-hosted) | Telegram trigger → AI node → Google Sheets node | Works well! But less flexible for conversation flow. Can self-host on the mini-server. |
| **Make.com** (Integromat) | Visual automation builder | Free tier limited to 1000 ops/month. Limited image handling. |
| **Zapier** | Telegram → GPT → Sheets | Expensive ($20+/mo for multi-step zaps), limited. |

**n8n** is actually a strong contender if you prefer a visual/no-code approach. It can be self-hosted, has Telegram and Google Sheets nodes, and has an AI agent node. However, it's less flexible for multi-turn conversations (follow-up questions).

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

### Minimal Setup (Self-hosted + Gemini Flash)
| Item | Monthly Cost |
|------|-------------|
| Hosting (home server) | $0 |
| LLM API (Gemini Flash free tier) | $0 |
| Google Sheets API | $0 |
| Telegram Bot API | $0 |
| **Total** | **$0/month** |

### Cloud Setup (Railway + GPT-4o-mini)
| Item | Monthly Cost |
|------|-------------|
| Hosting (Railway/Fly.io) | $0-5 |
| LLM API (GPT-4o-mini) | ~$0.50 |
| Google Sheets API | $0 |
| Telegram Bot API | $0 |
| **Total** | **$0.50-5.50/month** |

---

## 7. Implementation Phases (Estimated Effort)

| Phase | Description | Effort |
|-------|-------------|--------|
| **Phase 1** | Basic bot setup + text expense parsing + Google Sheets write | 3-4 hours |
| **Phase 2** | Image/screenshot parsing with vision LLM | 2-3 hours |
| **Phase 3** | Follow-up question flow for missing fields | 2-3 hours |
| **Phase 4** | Category management (inline keyboards, custom categories) | 1-2 hours |
| **Phase 5** | Monthly summary/reporting commands | 1-2 hours |
| **Phase 6** | Deployment, Docker, monitoring | 1-2 hours |

**Total estimated effort: ~10-16 hours**

---

## 8. Open Questions for You

Before implementation, I'd like to understand your preferences on these:

### Must-Answer

1. **What bank(s)/app(s) do you use?** This helps test screenshot parsing accuracy. Are the screenshots in English or another language?

2. **What expense categories do you want?** For example:
   - Groceries, Dining Out, Transport, Housing, Utilities, Entertainment, Shopping, Health, Education, Subscriptions, Travel, Other
   - Or do you already have categories in your existing Google Sheet?

3. **What currency is your primary currency?** (And do you deal with multiple currencies?)

4. **Do you already have a Google Sheet structure**, or should we design one from scratch?

### Good to Know

5. **Home server specs** - Does it have a GPU? What OS? How much RAM? (Affects whether local LLM is viable)

6. **Preference: self-hosted or cloud?** You mentioned you might prefer cloud - any strong feeling?

7. **Do you want the bot to be usable by just you, or also family members/partner?**

8. **Any existing expense tracking habits?** Do you want to support editing/deleting expenses via the bot, or just adding?

9. **Budget commands?** Would you like commands like `/summary` (monthly totals by category), `/budget` (set spending limits), `/export` (download CSV)?

10. **Language preference for the bot interface?** English? Another language?

---

## 9. Recommended Decision

Based on the research, the **recommended stack** for best cost-value with minimal maintenance:

| Component | Choice | Why |
|-----------|--------|-----|
| **Language** | Python 3.11+ | Best ecosystem for AI + Telegram + Google APIs |
| **Bot Framework** | python-telegram-bot v20+ | Best conversation handler support, most popular |
| **LLM** | Gemini 2.0 Flash (primary) + GPT-4o-mini (fallback) | Free tier covers personal use; fallback for reliability |
| **Google Sheets** | gspread + service account | Simplest, most reliable |
| **Hosting** | Home mini-server (Docker) with long polling | $0/month, no port forwarding needed, you own the infra |
| **Alt Hosting** | Oracle Cloud free-tier VM | If home server reliability is a concern |

This gives a **$0/month** solution with excellent parsing quality.
