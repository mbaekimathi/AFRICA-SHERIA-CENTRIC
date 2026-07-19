"""
Django settings for SHERIA-CENTRIC.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Prefer project .env over empty/stale process environment variables.
load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-69)v=mv&ge_@hf%5iv-*v)qkf@5mqpg5*aou%9r(6c*f0!2rg2",
)

DEBUG = os.getenv("DEBUG", "True").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
    if host.strip()
]
# Allow phones/tablets on the LAN (Host header is the PC's IP, not localhost).
if DEBUG and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("*")

# Comma-separated HTTPS origins for production (cPanel), e.g.
# CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]

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

DB_NAME = os.getenv("DB_NAME", "v.2-sheria-centric-db")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": DB_NAME,
        "USER": os.getenv("DB_USER", "root"),
        "PASSWORD": os.getenv("DB_PASSWORD", ""),
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "3306"),
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
# Django 4+ defaults to "same-origin", which blanks the GIS popup and breaks sign-in.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

# Google OAuth — client portal sign-in + firm Google Drive connection.
# Google rejects private LAN IPs for OAuth — use localhost / 127.0.0.1 in Console.
# Client GIS login needs Authorized JavaScript origins (not redirect URIs):
#   http://localhost:8000
#   http://127.0.0.1:8000
# Drive connect needs Authorized redirect URIs:
#   http://localhost:8000/integrations/google/callback/
#   http://127.0.0.1:8000/integrations/google/callback/
GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID", "") or "").strip()
GOOGLE_CLIENT_SECRET = (os.getenv("GOOGLE_CLIENT_SECRET", "") or "").strip()
GOOGLE_OAUTH_REDIRECT_URI = (
    os.getenv(
        "GOOGLE_OAUTH_REDIRECT_URI",
        "http://localhost:8000/integrations/google/callback/",
    )
    or ""
).strip()
# Root folder name created on the connected Google Drive account.
FIRM_DRIVE_ROOT_NAME = (
    os.getenv("FIRM_DRIVE_ROOT_NAME", "") or ""
).strip() or "Sheria-Centric"
# Display name shown in the workspace top bar.
FIRM_DISPLAY_NAME = (
    os.getenv("FIRM_DISPLAY_NAME", "") or ""
).strip() or "Sheria Law Firm"

FILE_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024
