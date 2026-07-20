"""
Django settings for SHERIA-CENTRIC.

Most values auto-pick — including the public domain from each request.
Put only secrets / DB overrides in `.env`.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Prefer project .env over empty/stale process environment variables.
load_dotenv(BASE_DIR / ".env", override=True)


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name, default) or "").strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _load_or_create_secret_key() -> str:
    """Use SECRET_KEY from env, else a persistent local file, else generate one."""
    from_env = _env("SECRET_KEY")
    if from_env and from_env not in {"change-me-in-production", "changeme"}:
        return from_env

    key_path = BASE_DIR / ".secret_key"
    if key_path.is_file():
        stored = key_path.read_text(encoding="utf-8").strip()
        if stored:
            return stored

    generated = secrets.token_urlsafe(50)
    try:
        key_path.write_text(generated + "\n", encoding="utf-8")
    except OSError:
        pass
    return generated


def _under_passenger() -> bool:
    return any(key.startswith("PASSENGER_") for key in os.environ)


# cPanel Passenger (or PRODUCTION=1) ⇒ production defaults.
IS_PRODUCTION = _env_bool("PRODUCTION", False) or _under_passenger()

SECRET_KEY = _load_or_create_secret_key()
DEBUG = _env_bool("DEBUG", default=not IS_PRODUCTION)

# Domain auto-picks from the request Host header (see AutoDomainMiddleware).
_allowed_raw = _env("ALLOWED_HOSTS")
ALLOWED_HOSTS = (
    [h.strip() for h in _allowed_raw.split(",") if h.strip()]
    if _allowed_raw
    else ["*"]
)

# Filled at runtime from each request; localhost kept for local forms/OAuth.
_csrf_raw = _env("CSRF_TRUSTED_ORIGINS")
CSRF_TRUSTED_ORIGINS = (
    [o.strip() for o in _csrf_raw.split(",") if o.strip()]
    if _csrf_raw
    else [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
)

# cPanel / reverse proxies terminate SSL in front of the app.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "accounts.apps.AccountsConfig",  # before staticfiles so our runserver wins
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.auto_domain.AutoDomainMiddleware",
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
        "DIRS": [BASE_DIR / "templates"],
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

# MySQL — defaults suit local MariaDB/MySQL; override only what differs.
DB_NAME = _env("DB_NAME") or "v.2-sheria-centric-db"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": DB_NAME,
        "USER": _env("DB_USER") or "root",
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": _env("DB_HOST") or "127.0.0.1",
        "PORT": _env("DB_PORT") or "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

AUTH_USER_MODEL = "accounts.Employee"

# Passwords: min 6 chars; digits or words allowed (e.g. 000000). Stored hashed.
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 6},
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:employees_home"
LOGOUT_REDIRECT_URL = "accounts:home"

# Allow Google Identity Services (and other OAuth) popups to postMessage back.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

# Google OAuth — only client id/secret belong in .env; redirect URI auto-picks domain.
GOOGLE_CLIENT_ID = _env("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _env("GOOGLE_CLIENT_SECRET")
GOOGLE_OAUTH_REDIRECT_URI = _env("GOOGLE_OAUTH_REDIRECT_URI")

FIRM_DRIVE_ROOT_NAME = _env("FIRM_DRIVE_ROOT_NAME") or "Sheria-Centric"
FIRM_DISPLAY_NAME = _env("FIRM_DISPLAY_NAME") or "Sheria Law Firm"

# M-Pesa Daraja (optional). When unset, invoice STK uses a simulated push for local/demo.
MPESA_CONSUMER_KEY = _env("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = _env("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE = _env("MPESA_SHORTCODE")
MPESA_PASSKEY = _env("MPESA_PASSKEY")
MPESA_CALLBACK_URL = _env("MPESA_CALLBACK_URL")
MPESA_ENV = _env("MPESA_ENV") or "sandbox"

FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024
