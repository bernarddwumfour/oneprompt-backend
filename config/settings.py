"""
Django settings for the OnePrompt backend.

Env-driven per BACKEND-RULES.main.md §2 — every secret/URL comes from an
environment variable, SECRET_KEY has no fallback, DEBUG defaults to False,
SQLite is the local-dev fallback until DATABASE_URL points at Postgres.
"""

from pathlib import Path

import dj_database_url
from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Core ---------------------------------------------------------------

SECRET_KEY = config("SECRET_KEY")
DEBUG = config("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
if "testserver" not in ALLOWED_HOSTS:
    # Django's test Client sends Host: testserver; harmless to always allow.
    ALLOWED_HOSTS.append("testserver")
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000",
    cast=Csv(),
)
GOOGLE_CLIENT_ID = config("GOOGLE_CLIENT_ID", default="")
GOOGLE_CLIENT_SECRET = config("GOOGLE_CLIENT_SECRET", default="")
GOOGLE_REDIRECT_URI = config("GOOGLE_REDIRECT_URI", default="")

# --- Providers (Plan 0002) -----------------------------------------------
DEEPSEEK_API_KEY = config("DEEPSEEK_API_KEY", default="")
DEEPSEEK_BASE_URL = config("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")
QWEN_API_KEY = config("QWEN_API_KEY", default="")
QWEN_BASE_URL = config(
    "QWEN_BASE_URL",
    default="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
)
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
GEMINI_BASE_URL = config(
    "GEMINI_BASE_URL",
    default="https://generativelanguage.googleapis.com/v1beta/openai",
)
OPENAI_API_KEY = config("OPENAI_API_KEY", default="")
OPENAI_BASE_URL = config(
    "OPENAI_BASE_URL", default="https://api.openai.com/v1"
)
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")
ANTHROPIC_BASE_URL = config("ANTHROPIC_BASE_URL", default="")

# --- Paystack (Plan 0002) ------------------------------------------------
PAYSTACK_SECRET_KEY = config("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_PUBLIC_KEY = config("PAYSTACK_PUBLIC_KEY", default="")

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")

# --- Bootstrap admin (Plan 0003) ---------------------------------------------
# If both are set, apps.accounts ensures this admin exists after every
# `migrate` (see apps/accounts/signals.py) — creates it once if missing,
# never overwrites an existing account. Leave DJANGO_ADMIN_PASSWORD empty to
# disable auto-creation entirely.
DJANGO_ADMIN_EMAIL = config("DJANGO_ADMIN_EMAIL", default="")
DJANGO_ADMIN_PASSWORD = config("DJANGO_ADMIN_PASSWORD", default="")
DJANGO_ADMIN_FULL_NAME = config("DJANGO_ADMIN_FULL_NAME", default="Admin")
DJANGO_ADMIN_COUNTRY = config("DJANGO_ADMIN_COUNTRY", default="GH")

# --- Applications ---------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "shared",
    "apps.accounts",
    "apps.credits",
    "apps.providers",
    "apps.conversations",
    "apps.billing",
    "apps.operations",
    "apps.platform",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# SQLite for local dev; set DATABASE_URL to switch to Postgres before
# production, per the pay-as-you-go / African-countries scope decisions in
# plans/0001-repo-scaffolding-auth-ledger-mvp-chat.md.

DATABASE_URL = config("DATABASE_URL", default="")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=not DEBUG,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Passwords ---------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- i18n ---------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files ---------------------------------------------------------------

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- JWT (Stage 2 wires the actual encode/decode helpers) -------------------

JWT_SECRET_KEY = config("JWT_SECRET_KEY", default="").strip() or SECRET_KEY
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = 60 * 15
REFRESH_TOKEN_TTL = 60 * 60 * 24 * 7

# --- Security headers (production only) -------------------------------------

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
