from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from django.conf import settings
from hrbot.bot.reports import generate_report
import io
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

async def send_daily_digest():
    """Send daily evaluation digest to HR chat."""
    try:
        bot = Bot(settings.TELEGRAM_BOT_TOKEN)
        buffer = io.BytesIO()
        await generate_report(buffer)
        buffer.name = "daily_report.pdf"
        await bot.send_document(chat_id=settings.HR_TELEGRAM_CHAT_ID, document=buffer)
        logger.info("Daily digest sent to HR.")
    except Exception as e:
        logger.exception("Failed to send daily digest: %s", e)

def start_scheduler():
    scheduler.add_job(send_daily_digest, 'cron', hour=9, minute=0)
    scheduler.start()
    logger.info("Scheduler started with daily digest job.")