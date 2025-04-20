# hrbot/apps.py

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class HrbotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hrbot'
    verbose_name = _("HR Бот") # Добавляем читаемое имя

    def ready(self):
        try:
            # Импортируем сигналы здесь
            import hrbot.signals
            import logging
            logger = logging.getLogger(__name__)
            logger.info("HR Bot signals imported successfully.")
        except ImportError:
            pass # Обработка на случай, если signals.py еще не создан