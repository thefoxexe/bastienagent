import os
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from bot.handlers.dispatcher import send_briefing

logger = logging.getLogger(__name__)


def setup_scheduler(application) -> AsyncIOScheduler:
    timezone = os.getenv("TIMEZONE", "Europe/Zurich")
    briefing_time = os.getenv("BRIEFING_TIME", "07:30")
    user_id = int(os.getenv("TELEGRAM_USER_ID", "0"))

    hour, minute = briefing_time.split(":")

    scheduler = AsyncIOScheduler(timezone=pytz.timezone(timezone))

    async def send_daily_briefing():
        try:
            await send_briefing(user_id, application)
            logger.info("Briefing quotidien envoyé.")
        except Exception as e:
            logger.error(f"Erreur briefing : {e}")

    scheduler.add_job(
        send_daily_briefing,
        CronTrigger(hour=int(hour), minute=int(minute), timezone=pytz.timezone(timezone)),
        id="daily_briefing",
        replace_existing=True,
    )

    return scheduler
