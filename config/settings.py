import os
import sys
import logging
from pathlib import Path
from datetime import timedelta
from django.utils.translation import gettext_lazy as _

# --- Основные параметры ---
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-key-@replace-this!")
DEBUG = os.environ.get("DEBUG", "True") == "True"

# --- Настройки хостов ---
ALLOWED_HOSTS = ['127.0.0.1', 'localhost','www.tasks.evos.uz', 'tasks.evos.uz']
# Примечание: В продакшене замените на реальные домены вашего приложения
# Если вы используете ASGI серверы (Daphne, Uvicorn), то нужно учитывать, что они могут передавать хост с портом.
# Для ASGI серверов, которые могут передавать хост с портом, используем ASGI_ALLOWED_HOSTS
# Пример: ASGI_ALLOWED_HOSTS = ['127.0.0.1:8000', 'localhost:8000']
ASGI_ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
# ALLOWED_HOSTS_ENV = os.environ.get("ALLOWED_HOSTS", "")
# if ALLOWED_HOSTS_ENV:
#     ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_ENV.split(",")]
# else:
#     ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
#     if DEBUG:
#         ALLOWED_HOSTS.append("0.0.0.0")

# -----------------------------------------------------------------------------
# ГЛАВНОЕ ИСПРАВЛЕНИЕ: Добавляем ASGI_ALLOWED_HOSTS
# Это решает проблему DisallowedHost при использовании ASGI серверов (Daphne, Uvicorn),
# которые передают хост вместе с портом в заголовке.
# -----------------------------------------------------------------------------
ASGI_ALLOWED_HOSTS = ALLOWED_HOSTS


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

    # Ваши приложения
    "user_profiles",
    "tasks",
    "room",
    "checklists",
    "qrfikr",
    "reviews",

    # Сторонние приложения
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

# --- Middleware ---
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", # Whitenoise рекомендуется размещать сразу после SecurityMiddleware
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

# --- База данных ---
# Для разработки используется SQLite
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# Настройка для тестов (перенесена в конец файла для логичности)


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

# --- Статические и медиа файлы ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Пользовательская модель и аутентификация ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "user_profiles.User"
LOGIN_URL = "user_profiles:login"
LOGIN_REDIRECT_URL = "tasks:task_list"
LOGOUT_REDIRECT_URL = "user_profiles:login"

# --- WebSocket и Channels ---
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
        # Для продакшена замените на:
        # "BACKEND": "channels_redis.core.RedisChannelLayer",
        # "CONFIG": {
        #     "hosts": [os.environ.get('REDIS_URL', 'redis://localhost:6379/1')],
        # },
    }
}
WEBSOCKET_ENABLED = True

# --- Настройки сайта и Email ---
SITE_NAME = 'ServiceDesk'
# ИСПРАВЛЕНО: Устанавливаем порт, на котором работает Daphne
SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8080')

# Для продакшена используйте переменные окружения
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', f'{SITE_NAME} <noreply@example.com>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ADMINS = [] # Заполните для получения уведомлений об ошибках в продакшене


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

# --- Swagger / drf-yasg ---
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

# --- CORS и CSRF ---
# ВНИМАНИЕ: Для продакшена замените на конкретный список доменов!
# CORS_ALLOWED_ORIGINS = ["https://your-frontend-domain.com"]
CORS_ALLOW_ALL_ORIGINS = True if DEBUG else False
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8080",
    "http://localhost:8080",
    "http://www.tasks.evos.uz",
    "http://tasks.evos.uz",
    "https://www.tasks.evos.uz",
    "https://tasks.evos.uz",
]

# --- Кэш ---
CACHE_TIMEOUT = 300
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-dev-cache",
    }
}
SELECT2_CACHE_BACKEND = "default"

# --- Шифрование полей ---
FIELD_ENCRYPTION_KEY = "_3HZU7uFwNYQw0n_7r1BFgwPU52Xs2N16uQUrJvPdUM="

# --- Crispy Forms и Tailwind ---
CRISPY_ALLOWED_TEMPLATE_PACKS = ["tailwind"]
CRISPY_TEMPLATE_PACK = "tailwind"
TAILWIND_APP_NAME = 'theme'
NPM_BIN_PATH = "C:/Program Files/nodejs/npm.cmd"

# --- Сообщения Django ---
MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"
from django.contrib.messages import constants as messages_constants

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
        "django": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO"},
        "django.template": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "tasks": {"handlers": ["console"], "level": "DEBUG"},
        "checklists": {"handlers": ["console"], "level": "DEBUG"},
    },
}

# --- Celery ---
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', CELERY_BROKER_URL)

# --- Кастомные настройки приложений ---
ENABLE_AUDIT_LOG = False
DEFAULT_STAFF_GROUP_NAME = 'Сотрудники'
NOTIFY_ADMINS_ON_NEW_USER = True

CHAT_MESSAGES_PAGE_SIZE = 50
MAX_FILE_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_FILE_TYPES = ['image/jpeg', 'image/png', 'application/pdf', 'text/plain']

# --- Настройки для тестов ---
if "test" in sys.argv:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
    PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend" # Ускоряет тесты
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True