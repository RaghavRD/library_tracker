import os
from pathlib import Path
from dotenv import load_dotenv
from django.urls import reverse_lazy

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.github",
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "libtrack_ai.urls"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "tracker" / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ],
    },
}]

WSGI_APPLICATION = "libtrack_ai.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "libtracker_db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "tracker" / "static",
]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication settings (resolved against the current URLConf)
LOGIN_URL = reverse_lazy("login")
LOGIN_REDIRECT_URL = reverse_lazy("dashboard")
LOGOUT_REDIRECT_URL = reverse_lazy("login")
SITE_ID = int(os.getenv("DJANGO_SITE_ID", "1"))

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "").strip()
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "").strip()
GITHUB_LOGIN_ENABLED = bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET)

ACCOUNT_EMAIL_VERIFICATION = os.getenv("ACCOUNT_EMAIL_VERIFICATION", "none")
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_STORE_TOKENS = False
SOCIALACCOUNT_PROVIDERS = {
    "github": {
        "SCOPE": ["read:user", "user:email"],
    }
}

if GITHUB_LOGIN_ENABLED:
    SOCIALACCOUNT_PROVIDERS["github"]["APPS"] = [
        {
            "client_id": GITHUB_CLIENT_ID,
            "secret": GITHUB_CLIENT_SECRET,
            "key": "",
        }
    ]

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'libtrack.log',
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'libtrack_errors.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'libtrack': {
            'handlers': ['console', 'file', 'error_file'],
            'level': 'INFO',
            'propagate': False,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        # Reduce verbosity of external libraries
        'httpx': {
            'handlers': ['error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
        'httpcore': {
            'handlers': ['error_file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ============================================================================
# LibTrack AI Configuration Settings
# ============================================================================

# Notification Service Settings
LIBTRACK_MAX_NOTIFICATION_RETRIES = os.getenv("LIBTRACK_MAX_NOTIFICATION_RETRIES", "3")
try:
    LIBTRACK_MAX_NOTIFICATION_RETRIES = int(LIBTRACK_MAX_NOTIFICATION_RETRIES)
except (ValueError, TypeError):
    LIBTRACK_MAX_NOTIFICATION_RETRIES = 3

# Future Update Detection Settings
LIBTRACK_MIN_FUTURE_CONFIDENCE = os.getenv("LIBTRACK_MIN_FUTURE_CONFIDENCE", "50")
try:
    LIBTRACK_MIN_FUTURE_CONFIDENCE = int(LIBTRACK_MIN_FUTURE_CONFIDENCE)
except (ValueError, TypeError):
    LIBTRACK_MIN_FUTURE_CONFIDENCE = 50

LIBTRACK_MAX_FUTURE_CONFIDENCE = os.getenv("LIBTRACK_MAX_FUTURE_CONFIDENCE", "100")
try:
    LIBTRACK_MAX_FUTURE_CONFIDENCE = int(LIBTRACK_MAX_FUTURE_CONFIDENCE)
except (ValueError, TypeError):
    LIBTRACK_MAX_FUTURE_CONFIDENCE = 100

# Version Fetch Service Settings
LIBTRACK_USE_OFFICIAL_APIS = os.getenv("LIBTRACK_USE_OFFICIAL_APIS", "True") == "True"
LIBTRACK_FETCH_DEBUG_MODE = os.getenv("LIBTRACK_FETCH_DEBUG_MODE", "False") == "True"

# Email / Notification Settings
LIBTRACK_ENABLE_EMAIL_NOTIFICATIONS = os.getenv("LIBTRACK_ENABLE_EMAIL_NOTIFICATIONS", "True") == "True"
LIBTRACK_EMAIL_BATCH_SIZE = os.getenv("LIBTRACK_EMAIL_BATCH_SIZE", "5")
try:
    LIBTRACK_EMAIL_BATCH_SIZE = int(LIBTRACK_EMAIL_BATCH_SIZE)
except (ValueError, TypeError):
    LIBTRACK_EMAIL_BATCH_SIZE = 5

LIBTRACK_EMAIL_PACKAGE_LIMIT = os.getenv("LIBTRACK_EMAIL_PACKAGE_LIMIT", "20")
try:
    LIBTRACK_EMAIL_PACKAGE_LIMIT = max(1, int(LIBTRACK_EMAIL_PACKAGE_LIMIT))
except (ValueError, TypeError):
    LIBTRACK_EMAIL_PACKAGE_LIMIT = 20

# Deduplication & Rate Limiting
LIBTRACK_DEDUP_WINDOW_HOURS = os.getenv("LIBTRACK_DEDUP_WINDOW_HOURS", "24")
try:
    LIBTRACK_DEDUP_WINDOW_HOURS = int(LIBTRACK_DEDUP_WINDOW_HOURS)
except (ValueError, TypeError):
    LIBTRACK_DEDUP_WINDOW_HOURS = 24

LIBTRACK_API_RATE_LIMIT_SECONDS = os.getenv("LIBTRACK_API_RATE_LIMIT_SECONDS", "1.5")
try:
    LIBTRACK_API_RATE_LIMIT_SECONDS = float(LIBTRACK_API_RATE_LIMIT_SECONDS)
except (ValueError, TypeError):
    LIBTRACK_API_RATE_LIMIT_SECONDS = 1.5

# Logging Configuration
LIBTRACK_LOG_DETECTION_METHOD = os.getenv("LIBTRACK_LOG_DETECTION_METHOD", "True") == "True"
LIBTRACK_LOG_HTTP_STATUS = os.getenv("LIBTRACK_LOG_HTTP_STATUS", "True") == "True"
LIBTRACK_LOG_RAW_PAYLOADS = os.getenv("LIBTRACK_LOG_RAW_PAYLOADS", "False") == "True"
LIBTRACK_LOG_LEVEL = os.getenv("LIBTRACK_LOG_LEVEL", "INFO")

# ============================================================================
