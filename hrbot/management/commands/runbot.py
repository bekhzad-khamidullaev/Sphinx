# hrbot/management/commands/runbot.py
import logging
import asyncio
from django.core.management.base import BaseCommand
from django.conf import settings

# Используем Application из python-telegram-bot v20+
from telegram.ext import Application, ApplicationBuilder, Defaults
from telegram import Update
from telegram.constants import ParseMode

# Импортируем функцию настройки обработчиков
# Используем относительный импорт, т.к. registration в подпапке bot
from hrbot.bot.registration import setup_handlers

# Настраиваем логирование для команды
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    # encoding='utf-8' # Указывайте, если выводите в файл или для Windows консоли
)
# Понижаем уровень логирования для httpx и httpcore, чтобы не засорять вывод
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__) # Логгер для этой команды

class Command(BaseCommand):
    help = 'Запускает Telegram бота HR Bot'

    def handle(self, *args, **options):
        """Основная логика команды."""
        logger.info("Starting runbot command...")

        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        if not token:
            logger.critical("TELEGRAM_BOT_TOKEN не найден в настройках Django!")
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN не найден в настройках Django!"))
            return

        try:
            # Устанавливаем настройки по умолчанию для всех запросов бота
            defaults = Defaults(parse_mode=ParseMode.MARKDOWN) # По умолчанию используем Markdown

            # Собираем приложение
            application = (
                ApplicationBuilder()
                .token(token)
                .defaults(defaults) # Применяем настройки по умолчанию
                # .persistence(...) # Добавьте persistence, если нужно сохранять состояние
                # .concurrent_updates(True) # Можно включить для параллельной обработки
                .build()
            )

            # Настраиваем обработчики
            setup_handlers(application)

            logger.info("HR Bot application configured. Starting polling...")
            self.stdout.write(self.style.SUCCESS("🚀 HR-бот запускается..."))

            # Запускаем бота в режиме опроса (polling)
            application.run_polling(allowed_updates=Update.ALL_TYPES)

            logger.info("HR Bot polling stopped.")
            self.stdout.write(self.style.SUCCESS("HR-бот остановлен."))

        except ValueError as e: # Например, если токен не валиден
             logger.critical(f"Configuration error: {e}")
             self.stderr.write(self.style.ERROR(f"Ошибка конфигурации: {e}"))
        except ImportError as e:
             logger.critical(f"Import error during setup: {e}")
             self.stderr.write(self.style.ERROR(f"Ошибка импорта при настройке: {e}"))
        except Exception as e:
            logger.exception("An unexpected error occurred while running the bot.")
            self.stderr.write(self.style.ERROR(f"Непредвиденная ошибка при работе бота: {e}"))