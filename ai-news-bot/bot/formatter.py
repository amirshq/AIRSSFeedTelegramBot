"""Digest message formatting for Telegram MarkdownV2."""

import re
from datetime import datetime


# Characters that must be escaped in MarkdownV2 *outside* of formatting marks
_ESCAPE_CHARS = r"\_[]()~`>#+=|{}.!-"
_ESCAPE_RE = re.compile(r"([" + re.escape(_ESCAPE_CHARS) + r"])")


def escape_mdv2(text: str) -> str:
    """Escape special MarkdownV2 characters in plain-text segments."""
    return _ESCAPE_RE.sub(r"\\\1", text)


def format_digest(digest_text: str, article_count: int, source_count: int) -> list[str]:
    """Wrap Claude's digest with a header/footer and split at Telegram's 4096-char limit.

    Args:
        digest_text:   The formatted digest body from the summariser.
        article_count: Number of articles included.
        source_count:  Number of sources queried.

    Returns:
        List of message strings, each ≤ 4096 characters.
    """
    date_str = escape_mdv2(datetime.now().strftime("%A, %B %-d %Y"))
    count_str = escape_mdv2(f"{article_count} articles from {source_count} sources")
    separator = escape_mdv2("─" * 21)

    header = (
        f"📰 *Your Daily AI & Tech Digest*\n"
        f"_{date_str}, {count_str}_\n"
        f"{separator}\n\n"
    )
    footer = (
        f"\n\n{separator}\n"
        f"🤖 Summarised by Claude \\| /help for controls"
    )

    full_text = header + digest_text + footer
    return _split_message(full_text)


def format_raw_headlines(articles: list[dict]) -> list[str]:
    """Fallback formatter that lists raw headlines without AI summarisation."""
    date_str = escape_mdv2(datetime.now().strftime("%A, %B %-d %Y"))
    separator = escape_mdv2("─" * 21)

    lines = [
        f"📰 *Your Daily AI & Tech Digest*\n_{date_str}_\n{separator}\n",
        "⚠️ *Summarisation unavailable — raw headlines:*\n",
    ]
    for a in articles:
        title = escape_mdv2(a.get("title", "Untitled"))
        source = escape_mdv2(a.get("source_name", ""))
        url = a.get("url", "")
        lines.append(f"• [{title}]({url}) _\\({source}\\)_")

    lines.append(f"\n{separator}\n🤖 /help for controls")
    full_text = "\n".join(lines)
    return _split_message(full_text)


def _split_message(text: str, limit: int = 4096) -> list[str]:
    """Split text into chunks that fit within Telegram's message size limit."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Try to split at a newline near the limit
        split_at = text.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")

    return chunks
