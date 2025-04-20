import sys

if sys.platform == "win32":
    # switch both input and output to UTF-8
    import ctypes
    ctypes.windll.kernel32.SetConsoleCP(65001)
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)

# Now reconfigure Python’s stdout to UTF‑8 as well:
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


import os
import django
import logging
import asyncio
import sys
import io
from django.core.management.base import BaseCommand
from django.conf import settings
from telegram import Bot
from telegram.ext import ApplicationBuilder

# UTF-8 for console output
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(console_handler)

from hrbot.bot.handlers import setup_handlers

class Command(BaseCommand):
    help = "Запускает HR-бота"

    def handle(self, *args, **options):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        bot = Bot(settings.TELEGRAM_BOT_TOKEN)
        loop.run_until_complete(bot.delete_webhook(drop_pending_updates=True))

        app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).build()
        setup_handlers(app)

        root.info("🚀 HR-бот запущен")
        loop.run_until_complete(app.run_polling())
        root.info("🛑 HR-бот остановлен")
        loop.close()
        sys.exit(0)