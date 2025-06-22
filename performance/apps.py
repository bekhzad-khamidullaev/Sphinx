from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class PerformanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'performance'
    verbose_name = _('Аттестации')
