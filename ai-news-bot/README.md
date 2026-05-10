# AI News Bot

A daily AI, tech, and data news digest delivered to Telegram. Scrapes RSS feeds and JS-heavy sites, deduplicates articles, summarises them with Claude, and sends a formatted digest on a configurable schedule — all controllable via Telegram commands.

---

## Prerequisites

- Python 3.11+
- Redis (running locally or remotely)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An Anthropic API key

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url> ai-news-bot
cd ai-news-bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install crawl4ai browser (one-time)

```bash
crawl4ai-setup
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your values
```

Required variables:

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | Your personal chat ID (see below) |
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `REDIS_URL` | e.g. `redis://localhost:6379/0` |
| `DIGEST_TIME` | 24h time, e.g. `08:00` |
| `TIMEZONE` | e.g. `America/Toronto` |
| `MAX_ARTICLES_PER_SOURCE` | Default: `10` |
| `MAX_ARTICLES_IN_DIGEST` | Default: `30` |

### 4. How to get your Telegram chat ID

1. Start a conversation with your bot.
2. Send any message to it.
3. Open: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Find `"chat": {"id": <number>}` — that number is your chat ID.

---

## First run

```bash
source venv/bin/activate
python main.py
```

On first run the bot will:
- Create the SQLite database (`news_bot.db`)
- Seed 8 default RSS sources
- Start polling Telegram for commands
- Schedule the daily digest

Send `/start` to your bot to verify it's running.

---

## Managing sources via Telegram

| Command | Example | Effect |
|---|---|---|
| `/list_sources` | — | Show all sources with IDs |
| `/add_source <url> <name> [type]` | `/add_source https://example.com/rss My Blog rss` | Add a source |
| `/remove_source <id>` | `/remove_source 3` | Disable source #3 |
| `/enable_source <id>` | `/enable_source 3` | Re-enable source #3 |
| `/set_time <HH:MM>` | `/set_time 07:30` | Change daily send time |
| `/digest_now` | — | Trigger digest immediately |
| `/status` | — | Show stats and next run |

---

## Server deployment with systemd

### 1. Copy files to server

```bash
sudo mkdir -p /opt/ai-news-bot
sudo cp -r . /opt/ai-news-bot/
sudo chown -R www-data:www-data /opt/ai-news-bot
```

### 2. Create virtual environment on the server

```bash
cd /opt/ai-news-bot
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/crawl4ai-setup
```

### 3. Set up environment file

```bash
sudo cp .env.example /opt/ai-news-bot/.env
sudo nano /opt/ai-news-bot/.env   # fill in real values
sudo chmod 600 /opt/ai-news-bot/.env
```

### 4. Install and start the systemd service

```bash
sudo cp systemd/ai-news-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ai-news-bot
sudo systemctl start ai-news-bot
sudo systemctl status ai-news-bot
```

### 5. View logs

```bash
sudo journalctl -u ai-news-bot -f
```

---

## Architecture

```
main.py                 ← entry point, wires everything together
config.py               ← typed settings from .env
bot/
  handlers.py           ← Telegram command handlers + digest pipeline
  formatter.py          ← MarkdownV2 formatting and message splitting
core/
  fetcher.py            ← RSS (feedparser) and Crawl4AI scraping
  dedup.py              ← Redis + SQLite URL deduplication
  summarizer.py         ← Claude API digest generation
  scheduler.py          ← APScheduler cron job management
db/
  storage.py            ← aiosqlite CRUD for sources and sent_articles
```

## Default sources

The bot ships with 8 pre-configured RSS feeds:

1. Google AI Blog
2. OpenAI Blog
3. Anthropic Blog
4. HuggingFace Blog
5. TLDR AI
6. Hacker News (AI/LLM/ML filtered)
7. MIT Technology Review
8. The Batch (DeepLearning.AI)
