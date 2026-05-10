"""Central configuration — loads .env and exposes typed settings."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_chat_id: str
    anthropic_api_key: str
    redis_url: str
    digest_time: str
    timezone: str
    max_articles_per_source: int
    max_articles_in_digest: int
    db_path: str

    @property
    def digest_hour(self) -> int:
        return int(self.digest_time.split(":")[0])

    @property
    def digest_minute(self) -> int:
        return int(self.digest_time.split(":")[1])


def load_settings() -> Settings:
    """Load and validate settings from environment variables."""
    required = [
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "ANTHROPIC_API_KEY",
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")

    return Settings(
        telegram_bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
        telegram_chat_id=os.environ["TELEGRAM_CHAT_ID"],
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        digest_time=os.getenv("DIGEST_TIME", "08:00"),
        timezone=os.getenv("TIMEZONE", "America/Toronto"),
        max_articles_per_source=int(os.getenv("MAX_ARTICLES_PER_SOURCE", "10")),
        max_articles_in_digest=int(os.getenv("MAX_ARTICLES_IN_DIGEST", "30")),
        db_path=os.getenv("DB_PATH", "news_bot.db"),
    )


settings = load_settings()
