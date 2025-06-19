import os
import sys
import logging
from pathlib import Path
from datetime import timedelta
from django.utils.translation import gettext_lazy as _

# --- Основные параметры ---
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-key-@replace-this!")
# DEBUG = os.environ.get("DEBUG", "True") == "True"
DEBUG = True
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "tasks.evos.uz,localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = ['https://tasks.evos.uz']

# --- Установленные приложения ---
INSTALLED_APPS = [
    # "jazzmin",
    # "simpleui",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "user_profiles",
    "tasks",
    "room",
    "checklists",
    "qrfikr",
    "reviews",

    "channels",
    "corsheaders",
    'crispy_forms',
    'crispy_tailwind',
    'tailwind',
    'theme',
    'django_browser_reload',
    "django_filters",
    "drf_yasg",
    "encrypted_model_fields",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "simple_history",
    "django_select2",
    "widget_tweaks",
    'phonenumber_field',
    "taggit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django_browser_reload.middleware.BrowserReloadMiddleware",
]

SWAGGER_SETTINGS = {
    'LOGIN_URL': 'rest_framework:login',
    'LOGOUT_URL': 'rest_framework:logout',
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT token: "Bearer <token>"',
        }
    },
    'USE_SESSION_AUTH': False, # Important for JWT
    'DEFAULT_AUTO_SCHEMA_CLASS': 'drf_yasg.inspectors.SwaggerAutoSchema',
}

REDOC_SETTINGS = {"LAZY_RENDERING": False}

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Шаблоны ---
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            'django.template.context_processors.i18n',
        ],
    },
}]

# --- База данных SQLite (для разработки) ---
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'servicedesk',
        'USER': 'sphinx',
        'PASSWORD': 't3sl@admin',
        'HOST': '127.0.0.1',
        'PORT': '',
    }
}

# --- Парольные валидаторы ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Языки и время ---
LANGUAGE_CODE = "ru"
LANGUAGES = [("ru", _("Русский")), ("en", _("English")), ("uz", _("Uzbek"))]
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

# --- Файлы ---
STATIC_URL = "/static/"
# STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Пользовательская модель ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "user_profiles.User"
LOGIN_URL = "user_profiles:login"
LOGIN_REDIRECT_URL = "tasks:task_list"
LOGOUT_REDIRECT_URL = "user_profiles:login"

# --- WebSocket ---
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}
WEBSOCKET_ENABLED = True

# --- Email ---
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "dev@example.com"
SITE_URL = "http://127.0.0.1:8000"

# --- JWT ---
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=5),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
}

# --- DRF ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
}

# --- Swagger ---
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": 'JWT token: "Bearer <token>"',
        }
    },
    "USE_SESSION_AUTH": False,
    "DEFAULT_AUTO_SCHEMA_CLASS": "drf_yasg.inspectors.SwaggerAutoSchema",
}

REDOC_SETTINGS = {"LAZY_RENDERING": False}

# --- CORS ---
CORS_ALLOW_ALL_ORIGINS = True

# --- Кэш ---
CACHE_TIMEOUT = 300
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-dev-cache",
    }
}

# --- Field Encryption ---
FIELD_ENCRYPTION_KEY = "_3HZU7uFwNYQw0n_7r1BFgwPU52Xs2N16uQUrJvPdUM="

# --- Crispy Forms ---
CRISPY_ALLOWED_TEMPLATE_PACKS = ["tailwind"]
CRISPY_TEMPLATE_PACK = "tailwind"
TAILWIND_APP_NAME = 'theme'
NPM_BIN_PATH = "C:/Program Files/nodejs/npm.cmd"

# --- Select2 ---
SELECT2_CACHE_BACKEND = "default"

# --- Сообщения ---
from django.contrib.messages import constants as messages_constants
MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"
MESSAGE_TAGS = {
    messages_constants.DEBUG: "debug",
    messages_constants.INFO: "info",
    messages_constants.SUCCESS: "success",
    messages_constants.WARNING: "warning",
    messages_constants.ERROR: "danger",
}

# --- Логирование ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{levelname} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "DEBUG"},
        "django.template": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "tasks": {"handlers": ["console"], "level": "DEBUG"},
        "checklists": {"handlers": ["console"], "level": "DEBUG"},
    },
}

# --- Тестовая БД ---
if "test" in sys.argv:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
    PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)



SITE_URL = 'http://127.0.0.1:8080' # ИЗМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ URL ДЛЯ ПРОДАкШЕНА
SITE_NAME = 'ServiceDesk' # Название вашего проекта/сайта

# Настройки Email (замените на ваши реальные данные)
# Для локальной разработки можно использовать консольный email backend:
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# Для продакшена:
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.example.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', f'{SITE_NAME} <noreply@example.com>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ADMINS = []

# Кастомные настройки для user_profiles/signals.py
ENABLE_AUDIT_LOG = False # Установите True, если решите добавить AuditLog позже
# AUDIT_LOG_APP_NAME = 'audit' # Если AuditLog будет в приложении 'audit'
DEFAULT_STAFF_GROUP_NAME = 'Сотрудники' # Имя группы для автоматического добавления staff-пользователей
NOTIFY_ADMINS_ON_NEW_USER = True # Отправлять ли админам email о новом пользователе


# Chat specific settings
CHAT_MESSAGES_PAGE_SIZE = 50 # Количество сообщений при подгрузке старых
MAX_FILE_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_FILE_TYPES = ['image/jpeg', 'image/png', 'application/pdf', 'text/plain'] # MIME types


CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)

