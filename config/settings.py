# config/settings.py
import logging
from pathlib import Path
import os
from django.utils.translation import gettext_lazy as _
from datetime import timedelta
import sys # For checking if running tests

# --- Basic Setup ---
BASE_DIR = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)

# --- Security ---
# WARNING: Keep the secret key used in production secret!
# Generate a new secret key for production.
# For development, a fixed key is acceptable but not recommended for shared repos.
SECRET_KEY = "django-insecure-development-key-@replace-me-in-prod@!"

# DEBUG = True in development, False in production.
# Use an environment variable in production for safety.
DEBUG = True # Set to False in production!

# Define allowed hosts. '*' is dangerous in production.
# Use specific domain names and IP addresses for production.
ALLOWED_HOSTS = ["*", "localhost", "127.0.0.1", "10.10.137.120"] # Adjust for your dev environment/prod

# --- Application Definition ---
INSTALLED_APPS = [
    # Django Core Apps
    "jazzmin", # Should be listed before 'django.contrib.admin'
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-Party Apps
    "channels",
    "corsheaders",
    "crispy_forms",
    "crispy_tailwind",
    "django_filters",
    "drf_yasg",
    "encrypted_model_fields", # Ensure FIELD_ENCRYPTION_KEY is set
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "simple_history",
    "django_browser_reload", # Development only
    "django_select2",
    "widget_tweaks",
    'taggit',
    # Your Project Apps
    "user_profiles",
    "tasks",
    "room",
    # "hrbot", # Uncomment if used
    "checklists",
    # Celery (Uncomment if used)
    # 'celery',
    # 'django_celery_beat',
    # 'django_celery_results',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware", # For serving static files efficiently
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware", # Place early, especially before CommonMiddleware
    "django.middleware.locale.LocaleMiddleware", # Crucial for i18n
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "django_browser_reload.middleware.BrowserReloadMiddleware", # Development only
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                # Add your custom context processors here if any
            ],
        },
    },
]

# --- Database ---
# Default to SQLite for development. Use environment variables for production.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        # Add 'TEST' config if using a separate test database
        # 'TEST': {
        #     'NAME': BASE_DIR / 'test_db.sqlite3',
        # },
    }
}
# Example for PostgreSQL (use environment variables in production):
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'your_db_name',
#         'USER': 'your_db_user',
#         'PASSWORD': 'your_db_password',
#         'HOST': 'localhost', # Or your DB host
#         'PORT': '5432',
#     }
# }

# --- Password Validation ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalization ---
LANGUAGE_CODE = "ru" # Default to Russian for development
LANGUAGES = [
    ("ru", _("Русский")),
    ("en", _("English")),
    ("uz", _("Uzbek")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_TZ = True # Recommended for handling timezones correctly
TIME_ZONE = "Asia/Tashkent" # Set your specific timezone for development/production

# --- Static Files & Media ---
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles" # For collectstatic in production
STATICFILES_DIRS = [BASE_DIR / "static"] # For development server
# Use WhiteNoise storage for compression and manifest (good for production)
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --- Default Primary Key ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentication ---
AUTH_USER_MODEL = "user_profiles.User"
LOGIN_URL = "user_profiles:login"
LOGIN_REDIRECT_URL = "tasks:task_list" # Redirect after successful login
LOGOUT_REDIRECT_URL = "user_profiles:login" # Redirect after logout

# --- Channels (WebSockets) ---
# Use InMemoryChannelLayer for development. Use Redis in production.
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}
# Example Redis config for production:
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {
#             "hosts": [os.environ.get('REDIS_URL', "redis://127.0.0.1:6379/1")],
#         },
#     },
# }

# --- Celery (Background Tasks) ---
# Uncomment and configure if using Celery
# CELERY_BROKER_URL = 'redis://localhost:6379/0' # Example using Redis
# CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
# CELERY_ACCEPT_CONTENT = ['json']
# CELERY_TASK_SERIALIZER = 'json'
# CELERY_RESULT_SERIALIZER = 'json'
# CELERY_TIMEZONE = TIME_ZONE
# CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler' # For scheduled tasks

# --- Crispy Forms ---
CRISPY_ALLOWED_TEMPLATE_PACKS = ["tailwind"]
CRISPY_TEMPLATE_PACK = "tailwind"

# --- REST Framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication", # Useful for Browsable API
        # "rest_framework.authentication.TokenAuthentication", # Less common now
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        # More restrictive default - require authentication for most actions
        "rest_framework.permissions.IsAuthenticated",
        # Or keep it more open initially:
        # "rest_framework.permissions.IsAuthenticatedOrReadOnly"
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25, # Default page size for API results
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_SCHEMA_CLASS": "rest_framework.schemas.openapi.AutoSchema",
}

# --- Simple JWT ---
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60), # Access token valid for 1 hour
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),    # Refresh token valid for 1 week
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True, # Requires `rest_framework_simplejwt.token_blacklist` app
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY, # Uses Django's SECRET_KEY by default
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "rest_framework_simplejwt.authentication.default_user_authentication_rule",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "SLIDING_TOKEN_REFRESH_EXP_CLAIM": "refresh_exp",
    "SLIDING_TOKEN_LIFETIME": timedelta(minutes=5), # Not typically used with rotate/blacklist
    "SLIDING_TOKEN_REFRESH_LIFETIME": timedelta(days=1),
}

# --- DRF-YASG (Swagger/ReDoc) ---
SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {
        "Bearer": { "type": "apiKey", "name": "Authorization", "in": "header", "description": 'Prefix with "Bearer ", e.g., "Bearer ey..."', }
    },
    "USE_SESSION_AUTH": False, # Prefer JWT for API docs
    "DEFAULT_AUTO_SCHEMA_CLASS": "drf_yasg.inspectors.SwaggerAutoSchema",
    "DEFAULT_INFO": "config.urls.api_info", # Point to API info object in urls.py
}
REDOC_SETTINGS = {
    "LAZY_RENDERING": False, # Render Redoc immediately
}

# --- CORS Headers ---
# Allow all origins for development. Restrict in production.
CORS_ALLOW_ALL_ORIGINS = DEBUG # True in debug, False otherwise
# If False, use:
# CORS_ALLOWED_ORIGINS = [
#     "http://localhost:3000", # Example React frontend
#     "http://127.0.0.1:3000",
#     "https://your-production-frontend.com",
# ]
# CORS_ALLOW_CREDENTIALS = True # If frontend needs to send cookies (e.g., session)

# --- Logging ---
# Simplified logging for development, more robust for production
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": { "format": "{levelname} {asctime} {module}:{lineno} {message}", "style": "{", },
        "simple": { "format": "{levelname} {message}", "style": "{", },
    },
    "handlers": {
        "console": { "class": "logging.StreamHandler", "level": "DEBUG" if DEBUG else "INFO", "formatter": "simple", },
        "file": { "level": "INFO", "class": "logging.handlers.RotatingFileHandler", "filename": BASE_DIR / "logs/django.log", "maxBytes": 1024 * 1024 * 5, "backupCount": 2, "formatter": "verbose", }, # 5MB file, 2 backups
    },
    "loggers": {
        "django": { "handlers": ["console", "file"], "level": "INFO", "propagate": False, },
        "django.request": { "handlers": ["file"], "level": "WARNING", "propagate": False, }, # Log errors/warnings for requests to file
        "tasks": { "handlers": ["console", "file"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False, },
        "user_profiles": { "handlers": ["console", "file"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False, },
        "checklists": { "handlers": ["console", "file"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False, },
        "room": { "handlers": ["console", "file"], "level": "DEBUG" if DEBUG else "INFO", "propagate": False, },
        "channels": { "handlers": ["console"], "level": "INFO", }, # Channels logging
    },
    "root": { "handlers": ["console"], "level": "INFO", },
}

# Ensure logs directory exists
log_dir = BASE_DIR / "logs"
log_dir.mkdir(exist_ok=True)

# --- Security Settings ---
# Use sensible defaults for development, override with env vars for production
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000 # 0 for dev, 1 year for prod
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
# SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https') # If behind a proxy handling SSL

# --- Email Settings ---
# Console backend for development is easiest
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.example.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'your-email@example.com'
# EMAIL_HOST_PASSWORD = 'your-password'
DEFAULT_FROM_EMAIL = "webmaster@localhost" # Change for production

# --- Caching ---
# LocMemCache is fine for development
CACHE_TIMEOUT = 300 # Default cache timeout in seconds
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-sphinx-cache",
    }
}

# --- Field Encryption Key ---
# WARNING: Generate a strong, unique key for production and keep it secret!
# Use: from cryptography.fernet import Fernet; Fernet.generate_key()
# Store it securely, e.g., in environment variables or a secrets manager.
# This default key is INSECURE and ONLY for development illustration.
FIELD_ENCRYPTION_KEY = "_3HZU7uFwNYQw0n_7r1BFgwPU52Xs2N16uQUrJvPdUM="

# --- Messages Framework ---
MESSAGE_STORAGE = "django.contrib.messages.storage.fallback.FallbackStorage"
from django.contrib.messages import constants as messages_constants
MESSAGE_TAGS = {
    messages_constants.DEBUG: "debug", # gray
    messages_constants.INFO: "info",   # blue
    messages_constants.SUCCESS: "success", # green
    messages_constants.WARNING: "warning", # yellow
    messages_constants.ERROR: "danger",   # red
}

# --- Telegram Bot Settings (Optional) ---
# Load from environment or define directly (not recommended for secrets)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") # Get from environment
HR_TELEGRAM_CHAT_ID = os.environ.get("HR_TELEGRAM_CHAT_ID") # Get from environment
# Example direct definition (for testing ONLY, replace with env vars):
# TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
# HR_TELEGRAM_CHAT_ID = "YOUR_HR_CHAT_ID_HERE"

# --- Bitrix24 Webhook (Optional) ---
BITRIX24_WEBHOOK = os.environ.get("BITRIX24_WEBHOOK") # Get from environment
# Example: BITRIX24_WEBHOOK = "https://yourdomain.bitrix24.ru/rest/1/yoursecretwebhookcode/"

# --- Other Custom Settings ---
SITE_URL = "http://127.0.0.1:8000" # Base URL for links in emails etc. Change for production.

# --- Testing specific settings ---
# Ensure tests run with a separate in-memory database if needed
if 'test' in sys.argv:
    logger.info("Applying test-specific settings...")
    DATABASES['default'] = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}
    PASSWORD_HASHERS = ('django.contrib.auth.hashers.MD5PasswordHasher',) # Faster hashing for tests
    # Disable unnecessary middleware for tests if needed
    # Example: remove 'django_browser_reload.middleware.BrowserReloadMiddleware'
    # DEBUG = False # Often tests run better with DEBUG=False


# --- WebSocket Enabled Flag for Templates ---
# This can be controlled by DEBUG or a specific setting
WEBSOCKET_ENABLED = DEBUG # Enable WebSockets in development

# --- Django Select2 ---
SELECT2_CACHE_BACKEND = "default" # Use the default Django cache
# SELECT2_JS = "//cdnjs.cloudflare.com/ajax/libs/select2/4.0.13/js/select2.min.js" # CDN example
# SELECT2_CSS = "//cdnjs.cloudflare.com/ajax/libs/select2/4.0.13/css/select2.min.css"

# --- Jazzmin Admin Theme Settings (Optional) ---
JAZZMIN_SETTINGS = {
    "site_title": "Sphinx Admin",
    "site_header": "Sphinx",
    "site_brand": "Sphinx Tasks",
    "site_logo": "img/logo.png", # Path relative to STATICFILES_DIRS or app's static dir
    "login_logo": "img/logo.png",
    "welcome_sign": "Welcome to Sphinx Admin",
    "copyright": "Sphinx Ltd.",
    "search_model": ["user_profiles.User", "tasks.Task", "tasks.Project"], # Models for global admin search
    "topmenu_links": [
        {"name": "Home", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"model": "user_profiles.User"},
        {"app": "tasks"},
        {"app": "checklists"},
        {"app": "room"},
        # {"name": "Support", "url": "https://github.com/farridav/django-jazzmin/issues", "new_window": True},
    ],
    "usermenu_links": [
        # {"name": "Support", "url": "https://github.com/farridav/django-jazzmin/issues", "new_window": True},
        {"model": "user_profiles.user"}
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "hide_apps": [],
    "hide_models": [],
    "order_with_respect_to": ["auth", "user_profiles", "tasks", "checklists", "room"], # Order apps
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "user_profiles.User": "fas fa-user-tie",
        "user_profiles.Team": "fas fa-users-cog",
        "user_profiles.Department": "fas fa-building",
        "tasks.Task": "fas fa-tasks",
        "tasks.Project": "fas fa-project-diagram",
        "tasks.TaskCategory": "fas fa-folder-open",
        "tasks.TaskSubcategory": "fas fa-stream",
        "tasks.TaskComment": "far fa-comment-dots",
        "tasks.TaskPhoto": "far fa-image",
        "checklists.ChecklistTemplate": "fas fa-clipboard-list",
        "checklists.ChecklistRun": "fas fa-clipboard-check",
        "room.Room": "fas fa-comments",
        "room.Message": "far fa-comment-alt",
        # Add more icons as needed
    },
    "default_icon_parents": "fas fa-chevron-circle-right",
    "default_icon_children": "fas fa-dot-circle",
    "related_modal_active": False,
    "custom_css": "css/jazzmin_custom.css", # Optional custom CSS
    "custom_js": None,
    "show_ui_builder": DEBUG, # Show UI builder only in debug
    "changeform_format": "horizontal_tabs",
    "changeform_format_overrides": {
        "auth.user": "collapsible",
        "auth.group": "vertical_tabs",
        "tasks.Task": "collapsible", # Example override
    },
    "language_chooser": True, # Enable language dropdown in admin
}
JAZZMIN_UI_TWEAKS = {
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "brand_colour": "navbar-teal", # Example: "navbar-indigo" or False
    "accent": "accent-primary",
    "navbar": "navbar-white navbar-light", # Example: "navbar-dark navbar-primary"
    "no_navbar_border": False,
    "navbar_fixed": True,
    "layout_boxed": False,
    "footer_fixed": True,
    "sidebar_fixed": True,
    "sidebar": "sidebar-dark-primary", # Example: "sidebar-light-indigo"
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": False,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme": "default", # "flatly", "cerulean", "cosmo", "lumen", "simplex", "darkly"
    "dark_mode_theme": "darkly", # Theme to use in dark mode
    "button_classes": {
        "primary": "btn-primary",
        "secondary": "btn-secondary",
        "info": "btn-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success"
    }
}