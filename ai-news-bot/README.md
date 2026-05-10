# AI News Bot

A self-hosted Telegram bot that delivers a daily digest of AI, tech, and data engineering news — summarised by Claude AI and sent straight to your chat.

Instead of scrolling through dozens of feeds every morning, the bot scrapes your configured sources, removes duplicates, groups articles by topic, and sends you a clean 2-sentence-per-article summary — all automatically, every day at a time you choose.

---

## What it does

- **Aggregates** RSS feeds and JS-heavy news sites from sources you control
- **Deduplicates** articles across runs using Redis + SQLite so you never see the same story twice
- **Summarises** everything with Claude (claude-sonnet-4-20250514) into a grouped, readable digest
- **Groups by topic** — AI Research, Tools & Models, Industry & Business, Data & MLOps, Tech News
- **Delivers to Telegram** every day at your scheduled time, formatted for mobile reading
- **Fully controllable via Telegram commands** — add/remove sources, change schedule, trigger on demand — no admin UI needed

---

## Example digest

```
📰 Your Daily AI & Tech Digest
Friday, May 9 2025 · 24 articles from 8 sources
─────────────────────────────────────────

🔬 AI Research

*GPT-5 Achieves State-of-the-Art on 12 Benchmarks*
OpenAI's latest model sets new records across reasoning and coding tasks,
with particular gains in multi-step problem solving. (OpenAI Blog)

*DeepMind Releases AlphaFold 3 Dataset*
The full training dataset for protein structure prediction is now publicly
available for academic research. (Google AI Blog)

🛠 Tools & Models

*Hugging Face Launches Inference Endpoints v2*
The new version cuts cold-start latency by 4× and adds auto-scaling
support for transformer models up to 70B parameters. (HuggingFace Blog)

...

─────────────────────────────────────────
🤖 Summarised by Claude | /help for controls
```

---

## Default sources

The bot ships pre-configured with 8 high-quality RSS feeds:

| Source | Type |
|---|---|
| Google AI Blog | RSS |
| OpenAI Blog | RSS |
| Anthropic Blog | RSS |
| HuggingFace Blog | RSS |
| TLDR AI | RSS |
| Hacker News (AI/LLM/ML filtered) | RSS |
| MIT Technology Review | RSS |
| The Batch (DeepLearning.AI) | RSS |

You can add any RSS feed or crawlable website via Telegram commands.

---

## Tech stack

| Component | Technology |
|---|---|
| Bot framework | python-telegram-bot v21 (async) |
| RSS parsing | feedparser |
| JS-heavy sites | crawl4ai + Playwright |
| AI summarisation | Anthropic SDK (Claude Sonnet) |
| Scheduling | APScheduler |
| Database | SQLite via aiosqlite |
| Deduplication | Redis |
| Config | python-dotenv |

---

## Project structure

```
ai-news-bot/
├── main.py               ← Entry point: starts bot + scheduler
├── config.py             ← Typed settings loaded from .env
├── bot/
│   ├── handlers.py       ← All Telegram command handlers
│   └── formatter.py      ← MarkdownV2 formatting + message splitting
├── core/
│   ├── fetcher.py        ← RSS + Crawl4AI scraping
│   ├── summarizer.py     ← Claude digest builder
│   ├── scheduler.py      ← APScheduler daily job
│   └── dedup.py          ← Redis + SQLite deduplication
├── db/
│   └── storage.py        ← SQLite CRUD operations
├── systemd/
│   └── ai-news-bot.service  ← systemd unit for server deployment
├── .env.example          ← Environment variable template
└── requirements.txt
```

---

## Prerequisites

- Python 3.11+
- Redis server
- A Telegram bot token — get one free from [@BotFather](https://t.me/BotFather)
- An Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)

---

## Local setup

### 1. Clone the repo

```bash
git clone https://github.com/amirshq/AIRSSFeedTelegramBot.git
cd AIRSSFeedTelegramBot/ai-news-bot
```

### 2. Create a virtual environment

```bash
python3.11 -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Install the Playwright browser (crawl4ai dependency)

```bash
crawl4ai-setup
# if that fails:
playwright install chromium --with-deps
```

### 4. Configure environment variables

```bash
cp .env.example .env
nano .env   # or open in your editor
```

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | From @BotFather |
| `TELEGRAM_CHAT_ID` | ✅ | Your personal Telegram chat ID |
| `ANTHROPIC_API_KEY` | ✅ | From console.anthropic.com |
| `REDIS_URL` | ✅ | e.g. `redis://localhost:6379/0` |
| `DIGEST_TIME` | ✅ | 24h time, e.g. `08:00` |
| `TIMEZONE` | ✅ | e.g. `America/Toronto` |
| `MAX_ARTICLES_PER_SOURCE` | — | Default: `10` |
| `MAX_ARTICLES_IN_DIGEST` | — | Default: `30` |
| `DB_PATH` | — | Default: `news_bot.db` |

### 5. How to find your Telegram chat ID

1. Start a chat with your bot on Telegram
2. Send it any message
3. Open in your browser: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Find `"chat": {"id": 123456789}` — that number is your chat ID

### 6. Start Redis

```bash
# macOS
brew install redis && brew services start redis

# Ubuntu/Debian
sudo apt install redis-server && sudo systemctl start redis-server
```

### 7. Run the bot

```bash
python main.py
```

Send `/start` to your bot in Telegram — it should reply immediately.

---

## Telegram commands

| Command | Description |
|---|---|
| `/start` | Welcome message and command list |
| `/digest_now` | Fetch and send the digest immediately |
| `/list_sources` | Show all sources with IDs and status |
| `/add_source <url> <name> [rss\|crawl]` | Add a new source |
| `/remove_source <id>` | Disable a source (keeps history) |
| `/enable_source <id>` | Re-enable a disabled source |
| `/set_time <HH:MM>` | Change the daily send time |
| `/status` | Show active sources, articles sent today, next run |
| `/help` | Show all commands |

### Adding sources

```
# Add an RSS feed
/add_source https://feeds.feedburner.com/oreilly/radar O'Reilly Radar rss

# Add a crawlable site (JS-rendered)
/add_source https://www.technologyreview.com MIT Tech Review crawl

# Default type is rss if omitted
/add_source https://example.com/feed My Blog
```

---

## Server deployment (Ubuntu + systemd)

### 1. Install dependencies

```bash
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3.11-dev git redis-server curl build-essential
systemctl enable redis-server && systemctl start redis-server
```

### 2. Clone and install

```bash
git clone https://github.com/amirshq/AIRSSFeedTelegramBot.git /opt/ai-news-bot
cd /opt/ai-news-bot
python3.11 -m venv venv
source venv/bin/activate
pip install -r ai-news-bot/requirements.txt
playwright install chromium --with-deps
```

### 3. Configure .env

```bash
cp /opt/ai-news-bot/ai-news-bot/.env.example /opt/ai-news-bot/ai-news-bot/.env
nano /opt/ai-news-bot/ai-news-bot/.env
chmod 600 /opt/ai-news-bot/ai-news-bot/.env
```

### 4. Install and start the systemd service

```bash
cat > /etc/systemd/system/ai-news-bot.service << 'EOF'
[Unit]
Description=AI News Telegram Bot
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ai-news-bot/ai-news-bot
ExecStart=/opt/ai-news-bot/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/ai-news-bot/ai-news-bot/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ai-news-bot
systemctl start ai-news-bot
systemctl status ai-news-bot
```

### 5. View logs

```bash
journalctl -u ai-news-bot -f
```

---

## Updating the bot

```bash
# On your Mac — commit and push changes
git add . && git commit -m "update" && git push

# On the server — pull and restart
cd /opt/ai-news-bot && git pull
systemctl restart ai-news-bot
```

---

## How it works

```
Every day at DIGEST_TIME:
  1. Load all active sources from SQLite
  2. Fetch articles concurrently (RSS via feedparser, JS sites via Crawl4AI)
  3. Hash each URL with SHA-256
  4. Check Redis seen-set (fast) → SQLite fallback (reliable)
  5. Keep only unseen articles
  6. Send article list to Claude with topic-grouping instructions
  7. Claude returns a MarkdownV2-formatted digest
  8. Split into chunks if > 4096 chars (Telegram limit)
  9. Send to TELEGRAM_CHAT_ID
 10. Mark all sent URLs in Redis (30-day TTL) + SQLite (permanent)
```

---

## Error handling

- A failing source is logged and skipped — one bad feed never breaks the whole run
- If Claude is unavailable, raw headlines are sent as a fallback
- If there are no new articles, a brief "nothing new" message is sent
- The bot restarts automatically via systemd if it crashes (`Restart=always`)

---

## License

MIT
