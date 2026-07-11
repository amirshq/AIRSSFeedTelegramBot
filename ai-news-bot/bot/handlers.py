"""All Telegram command handlers."""

import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.formatter import escape_mdv2, format_digest
from config import settings
from core import scheduler as sched_module
from core.dedup import filter_new_articles, mark_as_sent
from core.fetcher import fetch_all_sources
from core.summarizer import build_digest
from db.storage import (
    add_source,
    count_sent_today,
    get_active_sources,
    get_all_sources,
    set_source_active,
    upsert_setting,
)

logger = logging.getLogger(__name__)

# Injected by main.py after the redis client is available
_redis_client: Any = None
_digest_runner: Any = None  # async callable


def set_redis_client(client: Any) -> None:
    global _redis_client
    _redis_client = client


def set_digest_runner(runner: Any) -> None:
    global _digest_runner
    _digest_runner = runner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_url(url: str) -> bool:
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


async def _reply(update: Update, text: str, parse_mode: str = ParseMode.MARKDOWN_V2) -> None:
    if update.message:
        await update.message.reply_text(text, parse_mode=parse_mode)


def _escape_mdv2(text: str) -> str:
    """Escape all MarkdownV2 special characters."""
    special = r'\_*[]()~`>#+-=|{}.!'
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with a command overview."""
    text = (
        "👋 *Welcome to AI News Bot\\!*\n\n"
        "I deliver a daily digest of AI, tech, and data news straight to this chat\\.\n\n"
        "*Available commands:*\n"
        "/digest\\_now — Fetch and send the digest immediately\n"
        "/list\\_sources — Show all configured sources\n"
        "/add\\_source — Add a new news source\n"
        "/remove\\_source — Disable a source\n"
        "/enable\\_source — Re\\-enable a source\n"
        "/set\\_time — Change the daily send time\n"
        "/status — Show bot status\n"
        "/github\\_trending — Top trending AI/ML GitHub repos\n"
        "/help — Show this help message"
    )
    await _reply(update, text)


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all commands with descriptions."""
    text = (
        "📖 *Commands*\n\n"
        "`/start` — Welcome message\n"
        "`/digest_now` — Run the digest pipeline now\n"
        "`/list_sources` — List all sources \\(active \\+ inactive\\)\n"
        "`/add_source <url> <name> [rss|crawl]` — Add a source\n"
        "`/remove_source <id>` — Disable source by ID\n"
        "`/enable_source <id>` — Re\\-enable source by ID\n"
        "`/set_time <HH:MM>` — Reschedule daily digest\n"
        "`/status` — Show bot stats and next run time\n"
        "`/github_trending` — Top trending AI/ML repos \\(past 2 weeks\\)\n"
        "`/help` — Show this message"
    )
    await _reply(update, text)


# ---------------------------------------------------------------------------
# /add_source
# ---------------------------------------------------------------------------

async def cmd_add_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new news source.

    Usage: /add_source <url> <name> [rss|crawl]
    """
    args = context.args or []
    if len(args) < 2:
        await _reply(update, escape_mdv2("Usage: /add_source <url> <name> [rss|crawl]"), ParseMode.MARKDOWN_V2)
        return

    url = args[0]
    source_type = "rss"
    if args[-1].lower() in ("rss", "crawl"):
        source_type = args[-1].lower()
        name = " ".join(args[1:-1]) if len(args) > 2 else args[1]
    else:
        name = " ".join(args[1:])

    if not _is_valid_url(url):
        await _reply(update, escape_mdv2(f"❌ Invalid URL: {url}"), ParseMode.MARKDOWN_V2)
        return

    try:
        new_id = await add_source(name, url, source_type)
        msg = escape_mdv2(f"✅ Added #{new_id}: {name} ({url}) [{source_type}]")
        await _reply(update, msg)
    except Exception as exc:
        logger.exception("Failed to add source")
        if "UNIQUE" in str(exc):
            await _reply(update, escape_mdv2("❌ That URL is already in the database."))
        else:
            await _reply(update, escape_mdv2(f"❌ Error: {exc}"))


# ---------------------------------------------------------------------------
# /list_sources
# ---------------------------------------------------------------------------

async def cmd_list_sources(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all sources with their status."""
    sources = await get_all_sources()
    if not sources:
        await _reply(update, escape_mdv2("No sources configured yet."))
        return

    lines = ["*📡 News Sources*\n"]
    for s in sources:
        status = "✅" if s["active"] else "❌"
        line = escape_mdv2(f"{status} #{s['id']} {s['name']} [{s['type']}]")
        lines.append(line)

    await _reply(update, "\n".join(lines))


# ---------------------------------------------------------------------------
# /remove_source
# ---------------------------------------------------------------------------

async def cmd_remove_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Disable a source by ID (soft delete)."""
    args = context.args or []
    if not args or not args[0].isdigit():
        await _reply(update, escape_mdv2("Usage: /remove_source <id>"))
        return

    source_id = int(args[0])
    ok = await set_source_active(source_id, active=False)
    if ok:
        await _reply(update, escape_mdv2(f"🗑 Source #{source_id} disabled."))
    else:
        await _reply(update, escape_mdv2(f"❌ Source #{source_id} not found."))


# ---------------------------------------------------------------------------
# /enable_source
# ---------------------------------------------------------------------------

async def cmd_enable_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-enable a disabled source by ID."""
    args = context.args or []
    if not args or not args[0].isdigit():
        await _reply(update, escape_mdv2("Usage: /enable_source <id>"))
        return

    source_id = int(args[0])
    ok = await set_source_active(source_id, active=True)
    if ok:
        await _reply(update, escape_mdv2(f"✅ Source #{source_id} re-enabled."))
    else:
        await _reply(update, escape_mdv2(f"❌ Source #{source_id} not found."))


# ---------------------------------------------------------------------------
# /set_time
# ---------------------------------------------------------------------------

async def cmd_set_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reschedule the daily digest to a new HH:MM time."""
    args = context.args or []
    if not args:
        await _reply(update, escape_mdv2("Usage: /set_time <HH:MM>"))
        return

    time_str = args[0]
    if not re.match(r"^\d{1,2}:\d{2}$", time_str):
        await _reply(update, escape_mdv2("❌ Invalid format. Use HH:MM (e.g. 08:30)"))
        return

    h, m = map(int, time_str.split(":"))
    if not (0 <= h <= 23 and 0 <= m <= 59):
        await _reply(update, escape_mdv2("❌ Time out of range."))
        return

    if _digest_runner is None:
        await _reply(update, escape_mdv2("❌ Scheduler not ready yet."))
        return

    sched_module.reschedule_digest(_digest_runner, time_str)
    await upsert_setting("digest_time", time_str)
    await _reply(update, escape_mdv2(f"⏰ Digest will now be sent daily at {time_str}"))


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot statistics and next run time."""
    sources = await get_active_sources()
    today_count = await count_sent_today()
    next_run = sched_module.next_run_time() or "not scheduled"

    text = (
        f"*📊 Bot Status*\n\n"
        f"Active sources: {escape_mdv2(str(len(sources)))}\n"
        f"Articles sent today: {escape_mdv2(str(today_count))}\n"
        f"Next digest: {escape_mdv2(next_run)}"
    )
    await _reply(update, text)


# ---------------------------------------------------------------------------
# /digest_now
# ---------------------------------------------------------------------------

async def cmd_digest_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Trigger the full fetch → dedup → summarise → send pipeline immediately."""
    await _reply(update, escape_mdv2("⏳ Fetching digest… this may take a minute."))
    if _digest_runner:
        await _digest_runner()
    else:
        await _reply(update, escape_mdv2("❌ Digest runner not available."))


# ---------------------------------------------------------------------------
# /github_trending
# ---------------------------------------------------------------------------

async def cmd_github_trending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetch trending AI/ML GitHub repos from the past 2 weeks."""
    await _reply(update, escape_mdv2("⏳ Fetching trending GitHub repos..."))

    try:
        since = (datetime.now() - timedelta(weeks=2)).strftime("%Y-%m-%d")

        queries = [
            "artificial+intelligence",
            "large+language+model",
            "machine+learning",
            "LLM",
        ]

        seen: set[int] = set()
        repos: list[dict] = []

        async with aiohttp.ClientSession() as session:
            for q in queries:
                url = (
                    f"https://api.github.com/search/repositories"
                    f"?q={q}+created:>{since}"
                    f"&sort=stars&order=desc&per_page=5"
                )
                headers = {"Accept": "application/vnd.github+json"}
                async with session.get(url, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("GitHub API returned %d for query %s", resp.status, q)
                        continue
                    data = await resp.json()
                    for repo in data.get("items", []):
                        if repo["id"] not in seen:
                            seen.add(repo["id"])
                            repos.append(repo)

        repos = sorted(repos, key=lambda x: x["stargazers_count"], reverse=True)[:10]

        if not repos:
            await _reply(update, escape_mdv2("❌ No trending repos found."))
            return

        lines = ["⭐ *Trending AI/ML GitHub Repos* — past 2 weeks\n"]

        for i, repo in enumerate(repos, 1):
            stars = repo["stargazers_count"]
            lang = repo.get("language") or "N/A"
            desc = repo.get("description") or "No description"
            desc = desc[:80] + "..." if len(desc) > 80 else desc
            name = repo["full_name"]
            repo_url = repo["html_url"]

            lines.append(
                f"{i}\\. [{_escape_mdv2(name)}]({repo_url})\n"
                f"⭐ {stars:,} \\| 💻 {_escape_mdv2(lang)}\n"
                f"_{_escape_mdv2(desc)}_\n"
            )

        await _reply(update, "\n".join(lines))

    except Exception as exc:
        logger.exception("GitHub trending error")
        await _reply(update, escape_mdv2(f"❌ Error fetching repos: {exc}"))


# ---------------------------------------------------------------------------
# Pipeline (called by scheduler AND /digest_now)
# ---------------------------------------------------------------------------

async def run_digest_pipeline(app: Any) -> None:
    """End-to-end pipeline: fetch → dedup → summarise → send."""
    logger.info("Starting digest pipeline")

    sources = await get_active_sources()
    if not sources:
        logger.warning("No active sources — skipping digest")
        return

    articles = await fetch_all_sources(sources)
    if not articles:
        await app.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=escape_mdv2("✅ No articles fetched from any source."),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    new_articles = await filter_new_articles(articles, _redis_client)
    if not new_articles:
        await app.bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=escape_mdv2("✅ No new articles since last digest."),
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    digest_text = await build_digest(new_articles)
    messages = format_digest(digest_text, len(new_articles), len(sources))

    for chunk in messages:
        try:
            await app.bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("Failed to send digest chunk — retrying without parse mode")
            try:
                await app.bot.send_message(
                    chat_id=settings.telegram_chat_id,
                    text=chunk,
                    disable_web_page_preview=True,
                )
            except Exception:
                logger.exception("Failed to send digest chunk in plain text too")

    await mark_as_sent(new_articles, _redis_client)
    logger.info("Digest pipeline complete: %d articles sent", len(new_articles))