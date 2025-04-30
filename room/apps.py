# room/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class RoomConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'room'
    verbose_name = _("Чат-комнаты")