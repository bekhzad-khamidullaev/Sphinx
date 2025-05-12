from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _
import logging

logger = logging.getLogger(__name__)

class TasksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tasks'
    verbose_name = _('Управление Задачами')

    def ready(self):
        try:
            import tasks.signals
            logger.info("Tasks signals imported successfully.")
        except ImportError:
             logger.warning("Could not import tasks.signals.")
        except Exception as e:
             logger.error(f"Error importing signals in TasksConfig: {e}")