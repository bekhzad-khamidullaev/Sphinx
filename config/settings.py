import os
import sys
import logging
from pathlib import Path
from datetime import timedelta
from django.utils.translation import gettext_lazy as _

# --- Основные параметры ---
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = "django-insecure-dev-key-@replace-this!"
DEBUG = True
ALLOWED_HOSTS = ["*", "localhost", "127.0.0.1"]

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
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
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
STATICFILES_DIRS = [BASE_DIR / 'theme' / 'static']
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



SITE_URL = 'http://127.0.0.1:8000' # ИЗМЕНИТЕ НА ВАШ РЕАЛЬНЫЙ URL ДЛЯ ПРОДАкШЕНА
SITE_NAME = 'Sphinx Task Manager' # Название вашего проекта/сайта

# Настройки Email (замените на ваши реальные данные)
# Для локальной разработки можно использовать консольный email backend:
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# Для продакшена:
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.example.com' # Ваш SMTP сервер
EMAIL_PORT = 587 # или 465 для SSL
EMAIL_USE_TLS = True # True для TLS, False для SSL (если порт 465)
EMAIL_HOST_USER = 'your-email@example.com' # Ваш email логин
EMAIL_HOST_PASSWORD = 'your-email-password' # Ваш email пароль
DEFAULT_FROM_EMAIL = f'{SITE_NAME} <noreply@example.com>' # Email отправителя по умолчанию
SERVER_EMAIL = DEFAULT_FROM_EMAIL # Для ошибок сервера
ADMINS = [('Your Admin Name', 'admin-email@example.com')] # Email админов для уведомлений

# Кастомные настройки для user_profiles/signals.py
ENABLE_AUDIT_LOG = False # Установите True, если решите добавить AuditLog позже
# AUDIT_LOG_APP_NAME = 'audit' # Если AuditLog будет в приложении 'audit'
DEFAULT_STAFF_GROUP_NAME = 'Сотрудники' # Имя группы для автоматического добавления staff-пользователей
NOTIFY_ADMINS_ON_NEW_USER = True # Отправлять ли админам email о новом пользователе