from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class CrmCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "crm_core"
    verbose_name = _("Ядро CRM")

    def ready(self):
        """Импортируем сигналы при запуске приложения."""
        import crm_core.signals  # noqa: F401
