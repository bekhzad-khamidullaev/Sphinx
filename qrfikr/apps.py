from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class QRFikrConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'qrfikr'
    verbose_name = _("QR Feedback")
