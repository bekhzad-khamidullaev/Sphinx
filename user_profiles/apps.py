# user_profiles/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class UserProfilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_profiles'
    verbose_name = _('Профили пользователей и структура')

    def ready(self):
        try:
            import user_profiles.signals
        except ImportError:
            pass# user_profiles/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class UserProfilesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user_profiles'
    verbose_name = _('Профили пользователей и структура')

    def ready(self):
        try:
            import user_profiles.signals
        except ImportError:
            pass