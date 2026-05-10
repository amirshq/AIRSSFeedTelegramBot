"""Entry point: initialise DB, Redis, Telegram bot, and APScheduler."""

import asyncio
import logging
import sys
from functools import partial

import redis.asyncio as aioredis
from telegram.ext import Application, CommandHandler

import bot.handlers as handlers
from config import settings
from core.scheduler import get_scheduler, setup_scheduler
from db.storage import get_setting, init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


async def _build_digest_runner(app: Application):
    """Return a zero-argument async callable suitable for APScheduler."""
    async def runner():
        await handlers.run_digest_pipeline(app)
    return runner


async def main() -> None:
    # --- Database ---
    await init_db()

    # --- Redis ---
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis_client.ping()
        logger.info("Redis connected: %s", settings.redis_url)
    except Exception:
        logger.exception("Cannot connect to Redis — dedup will rely on DB only")

    handlers.set_redis_client(redis_client)

    # --- Telegram Application ---
    app = Application.builder().token(settings.telegram_bot_token).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", handlers.cmd_start))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("add_source", handlers.cmd_add_source))
    app.add_handler(CommandHandler("list_sources", handlers.cmd_list_sources))
    app.add_handler(CommandHandler("remove_source", handlers.cmd_remove_source))
    app.add_handler(CommandHandler("enable_source", handlers.cmd_enable_source))
    app.add_handler(CommandHandler("set_time", handlers.cmd_set_time))
    app.add_handler(CommandHandler("status", handlers.cmd_status))
    app.add_handler(CommandHandler("digest_now", handlers.cmd_digest_now))

    # --- Scheduler ---
    digest_runner = await _build_digest_runner(app)
    handlers.set_digest_runner(digest_runner)

    # Allow overriding digest time from DB (set via /set_time command)
    saved_time = await get_setting("digest_time")
    if saved_time:
        h, m = map(int, saved_time.split(":"))
        scheduler = setup_scheduler(digest_runner, hour=h, minute=m)
    else:
        scheduler = setup_scheduler(digest_runner)

    scheduler.start()
    logger.info("Scheduler started")

    # --- Run bot (blocks until interrupted) ---
    logger.info("Starting Telegram bot (polling)…")
    async with app:
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)

        # Keep alive until Ctrl-C
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            logger.info("Shutting down…")
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()
            await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
