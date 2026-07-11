"""Claude API digest builder with topic grouping."""

import json
import logging
from typing import Any

import anthropic

from config import settings

logger = logging.getLogger(__name__)

TOPICS = [
    "🔬 AI Research",
    "🛠 Tools & Models",
    "🏢 Industry & Business",
    "📊 Data & MLOps",
    "🌐 Tech News",
]

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_prompt(articles: list[dict[str, Any]]) -> str:
    article_data = [
        {
            "title": a.get("title", ""),
            "summary": a.get("summary", ""),
            "source": a.get("source_name", ""),
            "url": a.get("url", ""),
        }
        for a in articles
    ]
    topics_str = ", ".join(f'"{t}"' for t in TOPICS)
    return f"""You are a tech news curator writing a daily digest for a senior engineer interested in AI, ML, data engineering, and tech industry news.

Given the articles below, write a concise daily digest following these rules:
1. Group articles under one of these topic headers: {topics_str}
2. Only include topics that have at least one article.
3. For each article write exactly 1–2 sentences summarising the key insight.
4. After each article summary include the source in parentheses, e.g. (OpenAI Blog).
5. Use Telegram MarkdownV2 formatting:
   - Topic headers: *\\[emoji\\] Topic Name*
   - Article title as bold: *Article Title*
   - Body text: plain (escape special chars: . ! - ( ) [ ] ~ ` > # + = | {{ }} )
6. Skip duplicates or near-duplicates — pick the most informative version.
7. Return ONLY the formatted digest. No preamble, no closing remarks.

Articles (JSON):
{json.dumps(article_data, ensure_ascii=False, indent=2)}"""


async def build_digest(articles: list[dict[str, Any]]) -> str:
    """Summarise articles into a grouped Telegram-formatted digest.

    Args:
        articles: List of article dicts (title, url, summary, source_name).

    Returns:
        Formatted digest string ready for Telegram MarkdownV2, or a
        fallback raw-headlines string if the API call fails.
    """
    if not articles:
        return ""

    capped = articles[: settings.max_articles_in_digest]
    prompt = _build_prompt(capped)

    try:
        client = _get_client()
        message = await client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        digest = message.content[0].text.strip()
        logger.info("Digest built: %d chars from %d articles", len(digest), len(capped))
        return digest
    except Exception:
        logger.exception("Claude API call failed — returning raw headlines")
        lines = [
            f"• {a.get('title', 'Untitled')} ({a.get('source_name', '')})"
            for a in capped
        ]
        return "⚠️ Summarisation failed, here are raw headlines:\n\n" + "\n".join(lines)
