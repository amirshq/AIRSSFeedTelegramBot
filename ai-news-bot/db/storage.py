"""aiosqlite CRUD operations for sources and sent_articles tables."""

import logging
from datetime import datetime
from typing import Any

import aiosqlite

from config import settings

logger = logging.getLogger(__name__)

DEFAULT_SOURCES = [
    ("Google AI Blog", "https://blog.google/technology/ai/rss/", "rss"),
    ("OpenAI Blog", "https://openai.com/blog/rss.xml", "rss"),
    ("Anthropic Blog", "https://www.anthropic.com/rss.xml", "rss"),
    ("HuggingFace Blog", "https://huggingface.co/blog/feed.xml", "rss"),
    ("TLDR AI", "https://tldr.tech/api/rss/ai", "rss"),
    ("Hacker News AI", "https://hnrss.org/newest?q=AI+LLM+machine+learning&count=20", "rss"),
    ("MIT Technology Review", "https://www.technologyreview.com/feed/", "rss"),
    ("The Batch (DeepLearning.AI)", "https://www.deeplearning.ai/the-batch/feed/", "rss"),
]


async def init_db() -> None:
    """Create tables and seed default sources if the sources table is empty."""
    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sources (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                name     TEXT NOT NULL,
                url      TEXT NOT NULL UNIQUE,
                type     TEXT NOT NULL CHECK(type IN ('rss', 'crawl')),
                active   INTEGER DEFAULT 1,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sent_articles (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash  TEXT NOT NULL UNIQUE,
                title     TEXT,
                source_id INTEGER,
                sent_at   DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        await db.commit()

        cursor = await db.execute("SELECT COUNT(*) FROM sources")
        row = await cursor.fetchone()
        if row[0] == 0:
            await db.executemany(
                "INSERT OR IGNORE INTO sources (name, url, type) VALUES (?, ?, ?)",
                DEFAULT_SOURCES,
            )
            await db.commit()
            logger.info("Seeded %d default sources", len(DEFAULT_SOURCES))


async def get_active_sources() -> list[dict[str, Any]]:
    """Return all active sources as a list of dicts."""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, name, url, type, active, added_at FROM sources WHERE active = 1"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        logger.exception("Failed to fetch active sources")
        return []


async def get_all_sources() -> list[dict[str, Any]]:
    """Return all sources (active and inactive)."""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, name, url, type, active, added_at FROM sources ORDER BY id"
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception:
        logger.exception("Failed to fetch all sources")
        return []


async def add_source(name: str, url: str, source_type: str) -> int:
    """Insert a new source. Returns the new row id."""
    async with aiosqlite.connect(settings.db_path) as db:
        cursor = await db.execute(
            "INSERT INTO sources (name, url, type) VALUES (?, ?, ?)",
            (name, url, source_type),
        )
        await db.commit()
        return cursor.lastrowid


async def set_source_active(source_id: int, active: bool) -> bool:
    """Enable or disable a source. Returns True if a row was affected."""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            cursor = await db.execute(
                "UPDATE sources SET active = ? WHERE id = ?",
                (1 if active else 0, source_id),
            )
            await db.commit()
            return cursor.rowcount > 0
    except Exception:
        logger.exception("Failed to update source %d", source_id)
        return False


async def record_sent_articles(articles: list[dict[str, Any]]) -> None:
    """Persist sent articles to DB (url_hash, title, source_id)."""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            await db.executemany(
                "INSERT OR IGNORE INTO sent_articles (url_hash, title, source_id) VALUES (?, ?, ?)",
                [
                    (a["url_hash"], a.get("title", ""), a.get("source_id"))
                    for a in articles
                ],
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to record sent articles")


async def get_sent_hashes(hashes: list[str]) -> set[str]:
    """Return the subset of hashes already in sent_articles."""
    if not hashes:
        return set()
    try:
        placeholders = ",".join("?" * len(hashes))
        async with aiosqlite.connect(settings.db_path) as db:
            cursor = await db.execute(
                f"SELECT url_hash FROM sent_articles WHERE url_hash IN ({placeholders})",
                hashes,
            )
            rows = await cursor.fetchall()
            return {row[0] for row in rows}
    except Exception:
        logger.exception("Failed to query sent_articles")
        return set()


async def count_sent_today() -> int:
    """Count articles sent since midnight (local wall clock)."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(settings.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM sent_articles WHERE sent_at >= ?",
                (f"{today} 00:00:00",),
            )
            row = await cursor.fetchone()
            return row[0] if row else 0
    except Exception:
        logger.exception("Failed to count today's sent articles")
        return 0


async def get_setting(key: str, default: str | None = None) -> str | None:
    """Read a value from the bot_settings table."""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM bot_settings WHERE key = ?", (key,)
            )
            row = await cursor.fetchone()
            return row[0] if row else default
    except Exception:
        logger.exception("Failed to get setting %s", key)
        return default


async def upsert_setting(key: str, value: str) -> None:
    """Insert or replace a value in bot_settings."""
    try:
        async with aiosqlite.connect(settings.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            await db.commit()
    except Exception:
        logger.exception("Failed to upsert setting %s", key)
