# room/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class RoomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'room'
    verbose_name = _("Чат") # Для админки

    def ready(self):
        # Можно импортировать сигналы здесь, если они есть
        # import room.signals
        pass