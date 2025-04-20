import logging
from pathlib import Path
import os
from django.utils.translation import gettext_lazy as _
from decouple import config
from datetime import timedelta


# --- Logging Setup ---
logger = logging.getLogger(__name__)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# --- Basic Django Settings ---
SECRET_KEY = config('DJANGO_SECRET_KEY', default='django-insecure-t)onh@=0&bs0eghf!lv8w8==&(4^atr-44z!=xsac_4a6$^^+8') # Use environment variable or default
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='*', cast=lambda v: [s.strip() for s in v.split(',')])

# --- Application Definition ---
INSTALLED_APPS = [
    # Django Core Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-Party Apps
    'channels',             # For WebSockets
    'corsheaders',          # For Cross-Origin Resource Sharing
    'crispy_forms',         # For better form rendering
    'crispy_tailwind',      # Tailwind template pack for crispy-forms
    'django_filters',       # For filtering querysets
    'drf_yasg',             # For API documentation (Swagger/ReDoc)
    'encrypted_model_fields', # For encrypting specific model fields (ensure key is set)
    'rest_framework',       # For building APIs
    'rest_framework_simplejwt', # For JWT authentication
    'rest_framework_simplejwt.token_blacklist', # For JWT token blacklisting
    'simple_history',       # For model history tracking
    'django_browser_reload', # For auto-reloading in development
    'django_select2',

    # Your Project Apps
    'user_profiles',        # User management, teams, profiles, company structure
    'tasks',                # Core task management functionality
    'room',                 # Chat/room functionality (assuming it exists)
    'hrbot',
    # Celery (if used for background tasks) - Uncomment if needed
    # 'celery',
    # 'django_celery_beat', # For scheduled tasks
    # 'django_celery_results', # To store task results
]


TELEGRAM_BOT_TOKEN = "7822648522:AAGegzZBgQpSNm06aN-ycWH1-Dncuyd0xn4"
BITRIX24_WEBHOOK = 'https://yourdomain.bitrix24.ru/rest/ВАШ_WEBHOOK'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # Optimal static file serving
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware', # Place before CommonMiddleware
    'django.middleware.locale.LocaleMiddleware', # Crucial for i18n
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware', # For history tracking
    "django_browser_reload.middleware.BrowserReloadMiddleware", # Dev only
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], # Use Path object
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n', # For language support
            ],
        },
    },
]

# --- Database ---
# Default to SQLite for simplicity, override with environment variables for production
DATABASES = {
    'default': {
        'ENGINE': config('DATABASE_ENGINE', default='django.db.backends.sqlite3'),
        'NAME': config('DATABASE_NAME', default=BASE_DIR / 'db.sqlite3'),
        # Add other connection parameters (USER, PASSWORD, HOST, PORT) if using PostgreSQL/MySQL
        # 'USER': config('DATABASE_USER', default=''),
        # 'PASSWORD': config('DATABASE_PASSWORD', default=''),
        # 'HOST': config('DATABASE_HOST', default=''),
        # 'PORT': config('DATABASE_PORT', default=''),
    }
}

# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --- Internationalization ---
LANGUAGE_CODE = config('LANGUAGE_CODE', default='ru') # Default to Russian
LANGUAGES = [
    ('ru', _('Русский')),
    ('en', _('English')),
    ('uz', _('Uzbek')),
    # Add other languages as needed
    # ('es', _('Español')),
    # ('fr', _('Français')),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
USE_I18N = True
USE_TZ = True # Use timezone-aware datetimes
TIME_ZONE = config('TIME_ZONE', default='UTC') # Default to UTC, can be overridden

# --- Static Files & Media ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' # Directory for collectstatic
STATICFILES_DIRS = [BASE_DIR / 'static'] # Directory for static files during development
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage' # For efficient serving

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media' # Directory for user-uploaded files

# --- Default Primary Key ---
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Authentication ---
AUTH_USER_MODEL = 'user_profiles.User' # Custom user model
LOGIN_URL = 'user_profiles:login'
LOGIN_REDIRECT_URL = 'tasks:task_list' # Where to redirect after login
LOGOUT_REDIRECT_URL = 'user_profiles:login' # Where to redirect after logout

# --- Channels (WebSockets) ---
CHANNEL_LAYERS = {
    "default": {
        # Use Redis in production for scalability
        "BACKEND": config('CHANNEL_LAYER_BACKEND', default="channels.layers.InMemoryChannelLayer"),
        # Example Redis config (uncomment and configure if using Redis):
        # "CONFIG": {
        #     "hosts": [config('REDIS_URL', default="redis://127.0.0.1:6379/1")],
        # },
    },
}

# --- Celery (Background Tasks) ---
# Uncomment and configure if using Celery
# CELERY_BROKER_URL = config('CELERY_BROKER_URL', default='redis://localhost:6379/0')
# CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default='redis://localhost:6379/0')
# CELERY_ACCEPT_CONTENT = ['json']
# CELERY_TASK_SERIALIZER = 'json'
# CELERY_RESULT_SERIALIZER = 'json'
# CELERY_TIMEZONE = TIME_ZONE
# CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler' # If using scheduled tasks

# --- Crispy Forms ---
CRISPY_ALLOWED_TEMPLATE_PACKS = "tailwind"
CRISPY_TEMPLATE_PACK = "tailwind"

# --- REST Framework ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication', # JWT preferred
        'rest_framework.authentication.SessionAuthentication', # For browsable API
        'rest_framework.authentication.TokenAuthentication', # Optional: Basic token auth
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly' # Default policy
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': config('REST_PAGE_SIZE', default=20, cast=int), # Configurable page size
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_SCHEMA_CLASS': 'rest_framework.schemas.openapi.AutoSchema', # For OpenAPI schema generation
}

# --- Simple JWT ---
SIMPLE_JWT = {
    # Теперь timedelta будет распознана
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=config('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', default=60, cast=int)),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=config('JWT_REFRESH_TOKEN_LIFETIME_DAYS', default=1, cast=int)),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=config('JWT_SLIDING_TOKEN_LIFETIME_MINUTES', default=5, cast=int)),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=config('JWT_SLIDING_TOKEN_REFRESH_LIFETIME_DAYS', default=1, cast=int)),
}

# --- DRF-YASG (Swagger/ReDoc) ---
SWAGGER_SETTINGS = {
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
            'description': 'JWT token (add "Bearer " prefix, e.g., "Bearer ey...")'
        }
    },
    'USE_SESSION_AUTH': False, # Prefer JWT for API docs
    'JSON_EDITOR': True,
}
REDOC_SETTINGS = {
   'LAZY_RENDERING': False,
}

# --- CORS Headers ---
# Allow all origins in development, restrict in production
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=DEBUG, cast=bool)
# If CORS_ALLOW_ALL_ORIGINS is False, specify allowed origins:
# CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=lambda v: [s.strip() for s in v.split(',')])
# CORS_ALLOW_CREDENTIALS = True # If you need to send cookies across domains

# --- Logging ---
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'debug.log', # Путь к лог-файлу
            'encoding': 'utf-8', # <--- ВАЖНО
        },
        'console': { # Настройка для консоли (может не помочь с кодировкой самой консоли)
            'level': 'INFO',
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False,
        },
        'hrbot': { # Логгер вашего приложения
            'handlers': ['console', 'file'],
            'level': 'DEBUG', # Уровень DEBUG для подробных логов
            'propagate': False,
        },
         # Добавьте другие логгеры по необходимости
    },
    'root': { # Корневой логгер
        'handlers': ['console', 'file'],
        'level': 'INFO',
    }
}

# Ensure logs directory exists
log_dir = BASE_DIR / 'logs'
log_dir.mkdir(exist_ok=True)

# --- Security Settings (Important for Production) ---
# Set these via environment variables in production
SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = config('CSRF_COOKIE_SECURE', default=not DEBUG, cast=bool)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=not DEBUG, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0 if DEBUG else 31536000, cast=int) # 1 year HSTS
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=not DEBUG, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=not DEBUG, cast=bool)
SECURE_CONTENT_TYPE_NOSNIFF = config('SECURE_CONTENT_TYPE_NOSNIFF', default=True, cast=bool)
SECURE_BROWSER_XSS_FILTER = config('SECURE_BROWSER_XSS_FILTER', default=True, cast=bool)
X_FRAME_OPTIONS = config('X_FRAME_OPTIONS', default='DENY')

# --- Email Settings (Example using console backend for development) ---
EMAIL_BACKEND = config('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
# For production, use SMTP or a service like SendGrid, Mailgun, etc.
# EMAIL_HOST = config('EMAIL_HOST', default='smtp.example.com')
# EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
# EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
# EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
# EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
# DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='webmaster@localhost')

# --- Caching ---
# Use LocMemCache for development, Redis or Memcached for production
CACHE_TIMEOUT = config('CACHE_TIMEOUT', default=300, cast=int) # Default cache timeout in seconds
CACHES = {
    "default": {
        "BACKEND": config('CACHE_BACKEND', default="django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": config('CACHE_LOCATION', default="unique-snowflake"), # Meaningful for LocMem, connection string for others
        # Example Redis cache:
        # "BACKEND": "django_redis.cache.RedisCache",
        # "LOCATION": config('REDIS_URL', default="redis://127.0.0.1:6379/2"),
        # "OPTIONS": {
        #     "CLIENT_CLASS": "django_redis.client.DefaultClient",
        # }
    }
}
# --- Field Encryption Key ---
# IMPORTANT: Keep this key secret and backed up! Losing it means losing data.
# Generate a strong key using: from cryptography.fernet import Fernet; Fernet.generate_key()
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='_3HZU7uFwNYQw0n_7r1BFgwPU52Xs2N16uQUrJvPdUM=') # Provide a default or require env var

# --- Messages Framework ---
MESSAGE_STORAGE = 'django.contrib.messages.storage.fallback.FallbackStorage'
from django.contrib.messages import constants as messages_constants
MESSAGE_TAGS = {
    messages_constants.DEBUG: 'debug',
    messages_constants.INFO: 'info',
    messages_constants.SUCCESS: 'success',
    messages_constants.WARNING: 'warning',
    messages_constants.ERROR: 'danger', # Use 'danger' for Bootstrap compatibility
}

# --- Telegram Bot Settings (Optional) ---
# TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', default=None)

# --- Other Custom Settings ---
SITE_URL = config('SITE_URL', default='http://127.0.0.1:8000') # Used for generating absolute URLs in emails/notifications