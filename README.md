# Telegram Finance Bot (Render Webhook Edition)

## 1. Executive Summary
This project is a Python Telegram bot that helps you categorize uncategorized expense records in Notion. Instead of editing each record manually in Notion, you can run `/search` in Telegram, see each uncategorized transaction, and assign an expense type with one tap.

The bot is built for webhook hosting (for example on Render) using Flask + pyTelegramBotAPI. It receives Telegram updates at `/webhook`, fetches target records from Notion, and updates relation fields in Notion when users click category buttons.

## 2. Architecture Overview

### Text Diagram
```text
Telegram User
   |
   v
Telegram Bot API
   |
   v
Flask webhook endpoint (/webhook) in main.py
   |
   v
BotManager (telegram_manager.py)
   |                    \
   |                     \-- sends messages + inline keyboard buttons
   v
NotionManager (notion_manager.py)
   |
   v
Notion Data Source (transactions + expense type relation)
```

### Main Components
- `main.py`
  - Starts Flask app.
  - Sets Telegram webhook from `WEBHOOK_URL`.
  - Routes incoming updates to the bot.
- `telegram_manager.py`
  - Registers `/start` and `/search` handlers.
  - Builds category buttons.
  - Handles callbacks to update or delete a transaction.
- `notion_manager.py`
  - Queries uncategorized transactions from Notion.
  - Updates `Expense Type` relation.
  - Archives (soft deletes) a transaction when requested.

### Runtime Flow
1. App starts and sets webhook.
2. User sends `/search`.
3. Bot loads uncategorized rows from Notion.
4. Bot sends each row with inline buttons (Food, Shopping, etc.).
5. User taps a button.
6. Bot patches the related Notion row and confirms success in chat.

## 3. Setup Guide

### Prerequisites
- Python 3.10+
- A Telegram bot token (from BotFather)
- A Notion integration token
- A Notion data source with expected properties
- Public HTTPS URL for webhook (Render URL or ngrok in local dev)

### Install
```bash
git clone <your-repo-url>
cd tele_finance_bot_on_render
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure
Create a `.env` file in project root:

```env
BOT_TOKEN=your_telegram_bot_token
# optional alias if BOT_TOKEN is not used:
# TELEGRAM_BOT_TOKEN=your_telegram_bot_token

WEBHOOK_URL=https://your-domain-or-render-url/webhook

NOTION_API_TOKEN=your_notion_integration_token
NOTION_DB_ID=your_notion_data_source_id

# category relation target page IDs in Notion
FOOD_CAT_ID=
SHOPPING_CAT_ID=
TRANSPORT_CAT_ID=
WORK_LEARNING_CAT_ID=
SUBSCRIPTION_CAT_ID=
BUFFER_CAT_ID=
INVT_CAT_ID=
```

### Run Locally
```bash
python main.py
```

By default, Flask runs on `PORT` env var or `5001`.

### Quick Health Check
```bash
curl http://localhost:5001/
```
Expected:
```text
OK
```

## 4. Usage Guide

### Telegram Commands
- `/start`: Shows welcome message.
- `/search`: Fetches uncategorized transactions and sends category buttons.

### Example User Flow
1. Send `/search`.
2. Bot responds with records like:
```text
Coffee at XYZ
Date: 2025-10-12
Amount: 6.20
Open in Notion
```
3. Tap `Food` button.
4. Bot updates Notion and appends:
```text
✅ Categorised.
```

### Delete Transaction
- Tap `🗑 Delete`.
- Bot archives that Notion page and marks message as deleted.

## 5. Configuration

### Environment Variables
| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | Yes (or `TELEGRAM_BOT_TOKEN`) | Telegram bot token |
| `TELEGRAM_BOT_TOKEN` | Optional fallback | Alternate token env key |
| `WEBHOOK_URL` | Yes | Public HTTPS webhook URL ending in `/webhook` |
| `PORT` | Optional | Flask listen port (`5001` default local) |
| `NOTION_API_TOKEN` | Yes | Notion integration token |
| `NOTION_DB_ID` | Yes | Notion data source ID for transactions |
| `FOOD_CAT_ID` | Optional | Notion page ID for Food |
| `SHOPPING_CAT_ID` | Optional | Notion page ID for Shopping |
| `TRANSPORT_CAT_ID` | Optional | Notion page ID for Transport |
| `WORK_LEARNING_CAT_ID` | Optional | Notion page ID for Work & Learning |
| `SUBSCRIPTION_CAT_ID` | Optional | Notion page ID for Subscription |
| `BUFFER_CAT_ID` | Optional | Notion page ID for Buffer |
| `INVT_CAT_ID` | Optional | Notion page ID for Investment |

### Required Notion Schema
Your target data source should include:
- Title property: `Expense Record`
- Date property: `Date`
- Number property: `Amount`
- Relation property: `Expense Type` (points to your category pages/data source)

### Secrets Handling
- Keep `.env` out of git (`.gitignore` already includes `.env`).
- Never hardcode tokens in Python files.
- Rotate Telegram/Notion tokens if leaked.

## 6. Testing

### Current State
No automated test suite is included yet (`pytest`/`unittest` not configured).

### Manual Test Strategy
1. Start app locally.
2. Confirm `/` returns `OK`.
3. Send `/start` in Telegram.
4. Send `/search` and verify uncategorized records appear.
5. Tap one category and confirm Notion row relation updates.
6. Tap `🗑 Delete` and confirm row is archived in Notion.

### Suggested Future Coverage
- Unit tests for Notion response normalization (`normalize_page`).
- Tests for callback-key lifecycle (`SET:<key>` mapping).
- Integration test for webhook payload handling.

## 7. Deployment

### Local Development
- Use ngrok (or similar) to expose local Flask server over HTTPS.
- Set `WEBHOOK_URL` to `https://<public-url>/webhook`.

### Render (Recommended)
1. Create a new Render Web Service.
2. Connect this repository.
3. Set build command:
```bash
pip install -r requirements.txt
```
4. Set start command:
```bash
gunicorn main:app
```
5. Add all required environment variables in Render dashboard.
6. Set `WEBHOOK_URL` to your Render service URL + `/webhook`.

### CI/CD Notes
- No CI pipeline is currently defined in this repo.
- If using GitHub + Render auto-deploy, each push can trigger deployment.

## 8. Contributing Guide

### Branching
- Create a feature branch from `main`.
- Keep changes focused (one problem per PR).

### Pull Request Checklist
1. Explain what changed and why.
2. Include steps to test manually.
3. Confirm commands still work:
```bash
python -m py_compile main.py telegram_manager.py notion_manager.py
```
4. Attach screenshots/log snippets for Telegram flow when relevant.

### Code Style
- Follow existing Python style in this repo.
- Prefer small, testable functions for parsing/formatting logic.

## 9. FAQ & Troubleshooting

### `Missing BOT_TOKEN / TELEGRAM_BOT_TOKEN`
- Cause: token env variable not set.
- Fix: set `BOT_TOKEN` (or `TELEGRAM_BOT_TOKEN`) in `.env`.

### App fails on startup with `WEBHOOK_URL` assertion
- Cause: `WEBHOOK_URL` missing, not HTTPS, or does not end with `/webhook`.
- Fix: use a valid URL like `https://your-domain/webhook`.

### Button shows `Invalid/expired button`
- Cause: callback keys are stored in memory and can expire after restart or second tap.
- Fix: run `/search` again to generate fresh buttons.

### `/search` returns `Nothing to categorise`
- Cause: no rows match the Notion filter (`Date` not empty AND `Expense Type` empty).
- Fix: verify there are uncategorized rows and property names match exactly.

### Notion API errors (401/403/404/400)
- Cause: bad token, missing permissions, wrong data source ID, or schema mismatch.
- Fix:
1. Verify `NOTION_API_TOKEN` and `NOTION_DB_ID`.
2. Share the data source with your integration.
3. Confirm property names: `Expense Record`, `Date`, `Amount`, `Expense Type`.

## 10. License and Credits

### License
No `LICENSE` file is currently present. Add one (for example MIT) before public distribution.

### Credits
- [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI)
- [Flask](https://flask.palletsprojects.com/)
- [Notion API](https://developers.notion.com/)
- [python-dotenv](https://github.com/theskumar/python-dotenv)
- [gunicorn](https://gunicorn.org/)
