"""Redis-based URL deduplication with SQLite fallback."""

import hashlib
import logging
from typing import Any

import redis.asyncio as aioredis

from db.storage import get_sent_hashes, record_sent_articles

logger = logging.getLogger(__name__)

REDIS_KEY = "seen_urls"
REDIS_TTL_SECONDS = 30 * 24 * 3600  # 30 days


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


async def filter_new_articles(
    articles: list[dict[str, Any]],
    redis_client: aioredis.Redis,
) -> list[dict[str, Any]]:
    """Return only articles whose URLs have not been seen before.

    Checks Redis first (fast path), then falls back to the SQLite
    sent_articles table for any hashes Redis might have expired.
    """
    if not articles:
        return []

    for article in articles:
        article["url_hash"] = _hash_url(article["url"])

    hashes = [a["url_hash"] for a in articles]

    # Redis bulk check
    redis_seen: set[str] = set()
    try:
        pipe = redis_client.pipeline()
        for h in hashes:
            pipe.sismember(REDIS_KEY, h)
        results = await pipe.execute()
        redis_seen = {h for h, seen in zip(hashes, results) if seen}
    except Exception:
        logger.exception("Redis check failed — falling back to DB only")

    candidates = [a for a in articles if a["url_hash"] not in redis_seen]

    if not candidates:
        return []

    # DB fallback for any hashes Redis may have evicted
    candidate_hashes = [a["url_hash"] for a in candidates]
    db_seen = await get_sent_hashes(candidate_hashes)

    new_articles = [a for a in candidates if a["url_hash"] not in db_seen]
    logger.info(
        "Dedup: %d in → %d after Redis → %d after DB",
        len(articles),
        len(candidates),
        len(new_articles),
    )
    return new_articles


async def mark_as_sent(
    articles: list[dict[str, Any]],
    redis_client: aioredis.Redis,
) -> None:
    """Record articles as seen in both Redis and SQLite."""
    if not articles:
        return

    try:
        pipe = redis_client.pipeline()
        for article in articles:
            pipe.sadd(REDIS_KEY, article["url_hash"])
        pipe.expire(REDIS_KEY, REDIS_TTL_SECONDS)
        await pipe.execute()
    except Exception:
        logger.exception("Failed to mark URLs in Redis")

    await record_sent_articles(articles)
