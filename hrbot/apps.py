# hrbot/apps.py
from django.apps import AppConfig

class HrbotConfig(AppConfig):
    name = 'hrbot'
    verbose_name = "HR Bot"

    def ready(self):
        # подключаем наши сигналы
        import hrbot.signals  # noqa
