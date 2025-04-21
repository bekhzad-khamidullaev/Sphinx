# hrbot/management/commands/runbot.py
import logging
# import asyncio # Убран, т.к. не используется напрямую
from django.core.management.base import BaseCommand
from django.conf import settings
import os
# Импортируем необходимые модули для работы с Telegram API
from telegram.ext import Application, ApplicationBuilder, Defaults, PicklePersistence # Добавлен PicklePersistence
from telegram import Update
from telegram.constants import ParseMode

# Импортируем функцию настройки обработчиков
try:
    from hrbot.bot.registration import setup_handlers
except ImportError as e:
    # Логируем критическую ошибку, если не можем импортировать setup_handlers
    logging.critical(f"Failed to import setup_handlers from hrbot.bot.registration: {e}")
    # Можно либо выйти, либо продолжить без обработчиков (что бессмысленно)
    raise # Перевыбрасываем исключение, чтобы команда завершилась с ошибкой

# Настраиваем логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    # encoding='utf-8' # Раскомментируйте для Windows консоли
)
# Понижаем уровень логирования для библиотек http
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Логгер для этой команды
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Запускает Telegram бота HR Bot'

    def handle(self, *args, **options):
        """Основная логика команды."""
        logger.info("Starting runbot command...")

        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        if not token:
            logger.critical("TELEGRAM_BOT_TOKEN not found in Django settings!")
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN не найден в настройках Django!"))
            return

        try:
            # --- Persistence (опционально, для сохранения состояния диалогов) ---
            # Укажите путь, где будет храниться файл состояния
            persistence_filepath = os.path.join(settings.BASE_DIR, "bot_persistence.pickle")
            persistence = PicklePersistence(filepath=persistence_filepath)
            logger.info(f"Using persistence file: {persistence_filepath}")
            # ------------------------------------------------------------------

            # Устанавливаем настройки по умолчанию
            defaults = Defaults(parse_mode=ParseMode.MARKDOWN)

            # Собираем приложение
            application = (
                ApplicationBuilder()
                .token(token)
                .defaults(defaults)
                .persistence(persistence) # <-- Используем persistence
                # .concurrent_updates(True) # <-- Опционально
                .build()
            )

            # Настраиваем обработчики
            setup_handlers(application) # Передаем application в функцию настройки

            logger.info("HR Bot application configured. Starting polling...")
            self.stdout.write(self.style.SUCCESS("🚀 HR-бот запускается..."))

            # Запускаем бота в режиме опроса
            # Указываем только нужные типы обновлений (опционально)
            allowed_updates = [
                Update.MESSAGE,
                Update.CALLBACK_QUERY,
                # Добавьте другие типы, если они вам нужны
            ]
            application.run_polling(allowed_updates=allowed_updates)
            # Или application.run_polling() для получения всех типов

            # Этот код выполнится после остановки бота (например, по Ctrl+C)
            logger.info("HR Bot polling stopped.")
            self.stdout.write(self.style.SUCCESS("HR-бот остановлен."))

        except ValueError as e:
             logger.critical(f"Configuration error creating Application: {e}")
             self.stderr.write(self.style.ERROR(f"Ошибка конфигурации: {e}"))
        except ImportError as e: # Ловим ошибку импорта setup_handlers, если она не была поймана выше
             logger.critical(f"Import error during setup: {e}")
             self.stderr.write(self.style.ERROR(f"Ошибка импорта при настройке: {e}"))
        except Exception as e:
            logger.exception("An unexpected error occurred while running the bot.")
            self.stderr.write(self.style.ERROR(f"Непредвиденная ошибка при работе бота: {e}"))