from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class QrfikrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'qrfikr'
    verbose_name = _("QR Feedback System")

    def ready(self):
        try:
            import qrfikr.signals
            import logging
            logger = logging.getLogger(__name__)
            logger.info("qrfikr signals imported successfully.")
        except ImportError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Could not import qrfikr.signals: {e}")