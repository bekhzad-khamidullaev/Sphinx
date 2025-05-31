# checklists/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChecklistsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'checklists'
    verbose_name = _("Чеклисты")

    def ready(self):
        try:
            import checklists.signals
        except ImportError:
            pass