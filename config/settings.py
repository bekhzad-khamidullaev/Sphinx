# config/settings.py
import os
import sys
from pathlib import Path
from datetime import timedelta
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / '.env'
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-dev-key-@replace-this!')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS_STRING = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STRING.split(',')]
if DEBUG and '*' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('*')

CSRF_TRUSTED_ORIGINS_STRING = os.environ.get('CSRF_TRUSTED_ORIGINS', 'http://localhost:8000,http://127.0.0.1:8000')
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in CSRF_TRUSTED_ORIGINS_STRING.split(',')]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",

    "user_profiles.apps.UserProfilesConfig",
    "tasks.apps.TasksConfig",
    "room.apps.RoomConfig",
    "checklists.apps.ChecklistsConfig",

    "channels",
    "corsheaders",
    'crispy_forms',
    'crispy_tailwind',
    'tailwind',
    'theme.apps.ThemeConfig',
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
]
if DEBUG:
    MIDDLEWARE.append("django_browser_reload.middleware.BrowserReloadMiddleware")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = os.environ.get('ASGI_APPLICATION', "config.asgi.application")

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

DEFAULT_DB_ENGINE = "django.db.backends.sqlite3"
DEFAULT_DB_NAME = BASE_DIR / "db.sqlite3"
DATABASES = {
    "default": {
        "ENGINE": os.environ.get('SQL_ENGINE', DEFAULT_DB_ENGINE),
        "NAME": os.environ.get('SQL_DATABASE', DEFAULT_DB_NAME),
        "USER": os.environ.get('SQL_USER', ''),
        "PASSWORD": os.environ.get('SQL_PASSWORD', ''),
        "HOST": os.environ.get('SQL_HOST', ''),
        "PORT": os.environ.get('SQL_PORT', ''),
    }
}
if DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3' and not os.path.isabs(DATABASES['default']['NAME']):
    DATABASES['default']['NAME'] = BASE_DIR / DATABASES['default']['NAME']

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = os.environ.get('LANGUAGE_CODE', "ru")
LANGUAGES = [("ru", _("Русский")), ("en", _("English")), ("uz", _("Uzbek"))]
TIME_ZONE = os.environ.get('TIME_ZONE', "Asia/Tashkent")
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [BASE_DIR / "locale"]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles_collected"
STATICFILES_DIRS = [BASE_DIR / "static", BASE_DIR / 'theme' / 'static']
if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "mediafiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "user_profiles.User"
LOGIN_URL = "user_profiles:base_login"
LOGIN_REDIRECT_URL = "tasks:task_list"
LOGOUT_REDIRECT_URL = "user_profiles:base_login"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": os.environ.get('CHANNEL_LAYER_BACKEND', "channels.layers.InMemoryChannelLayer"),
        "CONFIG": { "hosts": [os.environ.get('REDIS_URL', 'redis://localhost:6379/0')] },
    },
}
if CHANNEL_LAYERS['default']['BACKEND'] == "channels.layers.InMemoryChannelLayer":
    CHANNEL_LAYERS['default']['CONFIG'] = {}
WEBSOCKET_ENABLED = os.environ.get('WEBSOCKET_ENABLED', 'True') == 'True'

EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'webmaster@localhost')
SERVER_EMAIL = os.environ.get('SERVER_EMAIL', DEFAULT_FROM_EMAIL)
ADMINS_STRING = os.environ.get('DJANGO_ADMINS', '')
ADMINS = []
if ADMINS_STRING:
    try:
        ADMINS = [tuple(admin.strip().rsplit('<', 1)) for admin in ADMINS_STRING.split(',')]
        ADMINS = [(name.strip(), email.strip().strip('>')) for name, email in ADMINS]
    except Exception as e:
        print(f"Warning: Could not parse ADMINS from .env: {e}")

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 7))),
    "ROTATE_REFRESH_TOKENS": True, "BLACKLIST_AFTER_ROTATION": True, "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256", "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",), "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id", "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type", "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get('JWT_SLIDING_TOKEN_LIFETIME_MINUTES', 15))),
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=int(os.environ.get('JWT_SLIDING_TOKEN_REFRESH_LIFETIME_DAYS', 1))),
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication", "rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": int(os.environ.get('REST_PAGE_SIZE', 20)),
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
}

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {"Bearer": {"type": "apiKey", "name": "Authorization", "in": "header", "description": 'JWT token: "Bearer <token>"'}},
    "USE_SESSION_AUTH": True, "DEFAULT_AUTO_SCHEMA_CLASS": "drf_yasg.inspectors.SwaggerAutoSchema",
}
REDOC_SETTINGS = {"LAZY_RENDERING": False}

CORS_ALLOW_ALL_ORIGINS = os.environ.get('CORS_ALLOW_ALL_ORIGINS', 'True' if DEBUG else 'False') == 'True'
CORS_ALLOWED_ORIGINS_STRING = os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000')
if not CORS_ALLOW_ALL_ORIGINS and CORS_ALLOWED_ORIGINS_STRING:
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ALLOWED_ORIGINS_STRING.split(',')]
# else: CORS_ALLOWED_ORIGINS = [] # Default to empty if not allowing all and no specific origins set

DEFAULT_CACHE_LOCATION = "unique-dev-cache"
if os.environ.get('CACHE_BACKEND') == 'django_redis.cache.RedisCache':
    DEFAULT_CACHE_LOCATION = os.environ.get('CACHE_LOCATION', f"redis://{os.environ.get('REDIS_HOST', 'redis')}:{os.environ.get('REDIS_PORT', 6379)}/1")
CACHES = {
    "default": {
        "BACKEND": os.environ.get('CACHE_BACKEND', "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": DEFAULT_CACHE_LOCATION,
    }
}

FIELD_ENCRYPTION_KEY_STR = os.environ.get('FIELD_ENCRYPTION_KEY')
FIELD_ENCRYPTION_KEYS = [FIELD_ENCRYPTION_KEY_STR.encode()] if FIELD_ENCRYPTION_KEY_STR else [] # Ключ должен быть bytes
if not DEBUG and not FIELD_ENCRYPTION_KEYS:
     raise ValueError("FIELD_ENCRYPTION_KEY must be set in environment for production!")
if DEBUG and not FIELD_ENCRYPTION_KEYS:
    print("WARNING: FIELD_ENCRYPTION_KEY not set. Using a dummy key for development. DO NOT USE IN PRODUCTION.")
    from cryptography.fernet import Fernet
    FIELD_ENCRYPTION_KEYS = [Fernet.generate_key()]


CRISPY_ALLOWED_TEMPLATE_PACKS = ["tailwind"]
CRISPY_TEMPLATE_PACK = "tailwind"
TAILWIND_APP_NAME = 'theme'
NPM_BIN_PATH = os.environ.get("NPM_BIN_PATH", "npm.cmd" if sys.platform == "win32" else "npm")

SELECT2_CACHE_BACKEND = "default"

from django.contrib.messages import constants as messages_constants
MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"
MESSAGE_TAGS = {
    messages_constants.DEBUG: "bg-gray-100 text-gray-800 border-gray-300",
    messages_constants.INFO: "bg-blue-100 text-blue-800 border-blue-300",
    messages_constants.SUCCESS: "bg-green-100 text-green-800 border-green-300",
    messages_constants.WARNING: "bg-yellow-100 text-yellow-800 border-yellow-300",
    messages_constants.ERROR: "bg-red-100 text-red-800 border-red-300",
}

LOGGING_LEVEL = 'DEBUG' if DEBUG else 'INFO'
LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'formatters': {
        'verbose': {'format': '%(levelname)s %(asctime)s %(module)s:%(lineno)d %(message)s'},
        'simple': {'format': '[%(asctime)s] %(levelname)s %(message)s', 'datefmt': '%Y-%m-%d %H:%M:%S'},
        'django.server': {'()': 'django.utils.log.ServerFormatter', 'format': '[{server_time}] {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'level': LOGGING_LEVEL, 'class': 'logging.StreamHandler', 'formatter': 'verbose' if DEBUG else 'simple'},
        'django.server': {'level': 'INFO', 'class': 'logging.StreamHandler', 'formatter': 'django.server'},
    },
    'loggers': {
        'django': {'handlers': ['console'], 'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False},
        'django.server': {'handlers': ['django.server'], 'level': 'INFO', 'propagate': False},
        'daphne': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'channels': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'user_profiles': {'handlers': ['console'], 'level': LOGGING_LEVEL, 'propagate': False},
        'tasks': {'handlers': ['console'], 'level': LOGGING_LEVEL, 'propagate': False},
        'room': {'handlers': ['console'], 'level': LOGGING_LEVEL, 'propagate': False},
        'checklists': {'handlers': ['console'], 'level': LOGGING_LEVEL, 'propagate': False},
    },
    'root': {'handlers': ['console'], 'level': LOGGING_LEVEL }
}

if "test" in sys.argv or os.environ.get('DJANGO_TESTING') == 'True':
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}} # Для тестов Channels

SITE_URL = os.environ.get('SITE_URL', 'http://127.0.0.1:8000')
SITE_NAME = os.environ.get('SITE_NAME', 'Sphinx')

ENABLE_AUDIT_LOG = os.environ.get('ENABLE_AUDIT_LOG', 'False') == 'True'
DEFAULT_STAFF_GROUP_NAME = os.environ.get('DEFAULT_STAFF_GROUP_NAME', 'Сотрудники')
NOTIFY_ADMINS_ON_NEW_USER = os.environ.get('NOTIFY_ADMINS_ON_NEW_USER', 'True' if DEBUG else 'False') == 'True'

CHAT_MESSAGES_PAGE_SIZE = int(os.environ.get('CHAT_MESSAGES_PAGE_SIZE', 50))
MAX_FILE_UPLOAD_SIZE_BYTES = int(os.environ.get('MAX_FILE_UPLOAD_SIZE_BYTES', 5 * 1024 * 1024))
ALLOWED_FILE_TYPES_STRING = os.environ.get('ALLOWED_FILE_TYPES', 'image/jpeg,image/png,application/pdf,text/plain,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
ALLOWED_FILE_TYPES = [ft.strip() for ft in ALLOWED_FILE_TYPES_STRING.split(',')] if ALLOWED_FILE_TYPES_STRING else []

if not DEBUG:
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'True') == 'True'
    CSRF_COOKIE_SECURE = os.environ.get('CSRF_COOKIE_SECURE', 'True') == 'True'
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True') == 'True'
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', 31536000))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get('SECURE_HSTS_INCLUDE_SUBDOMAINS', 'True') == 'True'
    SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'True') == 'True'
    SECURE_CONTENT_TYPE_NOSNIFF = os.environ.get('SECURE_CONTENT_TYPE_NOSNIFF', 'True') == 'True'
    SECURE_BROWSER_XSS_FILTER = os.environ.get('SECURE_BROWSER_XSS_FILTER', 'True') == 'True'
    X_FRAME_OPTIONS = os.environ.get('X_FRAME_OPTIONS', 'DENY')
    USE_X_FORWARDED_HOST = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    if "django_browser_reload.middleware.BrowserReloadMiddleware" in MIDDLEWARE:
        MIDDLEWARE.remove("django_browser_reload.middleware.BrowserReloadMiddleware")
    if "django_browser_reload" in INSTALLED_APPS:
        INSTALLED_APPS.remove("django_browser_reload")
else:
    INTERNAL_IPS = ["127.0.0.1", "localhost"]