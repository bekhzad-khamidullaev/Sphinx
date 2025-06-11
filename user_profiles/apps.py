# user_profiles/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _ # For verbose_name

class UserProfilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_profiles'
    verbose_name = _('Профили пользователей и структура') # More descriptive

    def ready(self):
        try:
            import user_profiles.signals # If you add signals to user_profiles
            # logger.info("User profiles signals imported.") # Use logger from models
        except ImportError:
            pass # No signals defined or error importing