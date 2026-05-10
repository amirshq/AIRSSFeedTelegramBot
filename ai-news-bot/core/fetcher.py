"""RSS and Crawl4AI scraping logic."""

import asyncio
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import feedparser

from config import settings

logger = logging.getLogger(__name__)


def _parse_feed_sync(url: str) -> feedparser.FeedParserDict:
    """Blocking feedparser call — must run in executor."""
    return feedparser.parse(url)


def _entry_to_article(entry: Any, source: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a feedparser entry into a normalised article dict."""
    url = entry.get("link", "").strip()
    if not url:
        return None
    title = entry.get("title", "No title").strip()
    summary = (
        entry.get("summary", "")
        or entry.get("description", "")
    ).strip()
    # Strip HTML tags crudely — summarizer gets plain text
    import re
    summary = re.sub(r"<[^>]+>", " ", summary).strip()
    summary = re.sub(r"\s+", " ", summary)[:500]

    published_date: str | None = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            published_date = datetime(*entry.published_parsed[:6]).isoformat()
        except Exception:
            pass

    return {
        "title": title,
        "url": url,
        "summary": summary,
        "source_name": source["name"],
        "source_id": source["id"],
        "published_date": published_date,
    }


async def _fetch_rss(source: dict[str, Any], loop: asyncio.AbstractEventLoop) -> list[dict[str, Any]]:
    """Fetch and parse an RSS feed asynchronously."""
    try:
        feed = await loop.run_in_executor(None, _parse_feed_sync, source["url"])
    except Exception:
        logger.exception("RSS fetch failed for source '%s'", source["name"])
        return []

    if feed.bozo and not feed.entries:
        logger.warning("Malformed feed for '%s': %s", source["name"], feed.bozo_exception)
        return []

    articles: list[dict[str, Any]] = []
    for entry in feed.entries[: settings.max_articles_per_source]:
        article = _entry_to_article(entry, source)
        if article:
            articles.append(article)

    logger.info("RSS '%s': fetched %d articles", source["name"], len(articles))
    return articles


async def _fetch_crawl(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Crawl a JS-heavy page with crawl4ai and extract article links."""
    try:
        from crawl4ai import AsyncWebCrawler  # type: ignore
    except ImportError:
        logger.error("crawl4ai not installed — skipping crawl source '%s'", source["name"])
        return []

    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=source["url"])
    except Exception:
        logger.exception("Crawl4AI failed for '%s'", source["name"])
        return []

    if not result or not result.markdown:
        logger.warning("Crawl4AI returned no content for '%s'", source["name"])
        return []

    import re
    # Extract markdown links: [title](url)
    pattern = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
    matches = pattern.findall(result.markdown)

    articles: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for title, url in matches:
        url = url.strip()
        if url in seen_urls:
            continue
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            continue
        seen_urls.add(url)
        articles.append(
            {
                "title": title.strip(),
                "url": url,
                "summary": "",
                "source_name": source["name"],
                "source_id": source["id"],
                "published_date": None,
            }
        )
        if len(articles) >= settings.max_articles_per_source:
            break

    logger.info("Crawl '%s': extracted %d articles", source["name"], len(articles))
    return articles


async def fetch_all_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch articles from all active sources concurrently.

    Args:
        sources: List of source dicts from the DB.

    Returns:
        Flat list of article dicts with keys:
        title, url, summary, source_name, source_id, published_date.
    """
    loop = asyncio.get_running_loop()

    tasks: list[asyncio.Task] = []
    for source in sources:
        if source["type"] == "rss":
            tasks.append(asyncio.create_task(_fetch_rss(source, loop)))
        elif source["type"] == "crawl":
            tasks.append(asyncio.create_task(_fetch_crawl(source)))
        else:
            logger.warning("Unknown source type '%s' for '%s'", source["type"], source["name"])

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles: list[dict[str, Any]] = []
    for source, result in zip(sources, results):
        if isinstance(result, Exception):
            logger.error("Source '%s' raised: %s", source["name"], result)
        elif isinstance(result, list):
            all_articles.extend(result)

    logger.info("Total articles fetched: %d", len(all_articles))
    return all_articles
