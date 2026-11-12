"""Settings for the RNC academic prototype."""

import os
import hashlib
import json
from pathlib import Path

from .languages import (
    DRAFT_LANGUAGES,
    selectable_languages,
    translation_preview_enabled,
)

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "development-only-change-before-any-shared-deployment",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "1").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "public_site.apps.RNCAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "public_site.apps.PublicSiteConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
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
            "libraries": {
                "locale_format": "public_site.templatetags.locale_format",
            },
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "public_site.context_processors.navigation",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Development database only. The institutional production database is not selected.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(
            os.environ.get("RNC_DATABASE_PATH", BASE_DIR / "db.sqlite3")
        ),
    }
}

LANGUAGE_CODE = "es"
TRANSLATION_PREVIEW_ENABLED = translation_preview_enabled()
DRAFT_TRANSLATION_LOCALES = tuple(code for code, _name in DRAFT_LANGUAGES)
LANGUAGES = selectable_languages(TRANSLATION_PREVIEW_ENABLED)
LOCALE_PATHS = [BASE_DIR / "locale"]
if TRANSLATION_PREVIEW_ENABLED:
    TRANSLATION_PREVIEW_LOCALE_ROOT = Path(os.environ.get(
        "RNC_TRANSLATION_PREVIEW_LOCALE_PATH", BASE_DIR / "locale-preview"
    )).resolve()
    manifest_path = TRANSLATION_PREVIEW_LOCALE_ROOT / "manifest.json"
    preview_problems = []
    try:
        preview_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        preview_manifest = {}
        preview_problems.append("falta manifiesto legible")
    expected_preview_keys = {
        f"{code}/{domain}"
        for code in DRAFT_TRANSLATION_LOCALES
        for domain in ("django", "djangojs")
    }
    preview_catalogs = preview_manifest.get("catalogs", {})
    if preview_manifest.get("schema") != "rnc-translation-preview-v1":
        preview_problems.append("versión de manifiesto desconocida")
    if not isinstance(preview_catalogs, dict) or set(preview_catalogs) != expected_preview_keys:
        preview_problems.append("inventario de catálogos incompleto")
        preview_catalogs = preview_catalogs if isinstance(preview_catalogs, dict) else {}
    from django.utils.translation.trans_real import to_locale

    for key in expected_preview_keys:
        record = preview_catalogs.get(key)
        if not isinstance(record, dict):
            continue
        code, domain = key.split("/", 1)
        expected_source = f"locale/{code}/LC_MESSAGES/{domain}.po"
        if record.get("source") != expected_source:
            preview_problems.append(f"fuente inesperada para {key}")
            continue
        expected_mo = (Path(to_locale(code)) / "LC_MESSAGES" / f"{domain}.mo").as_posix()
        if record.get("mo") != expected_mo:
            preview_problems.append(f"ruta .mo inesperada para {key}")
            continue
        source_path = BASE_DIR / expected_source
        mo_relative = Path(record.get("mo", ""))
        if mo_relative.is_absolute() or ".." in mo_relative.parts:
            preview_problems.append(f"ruta .mo inválida para {key}")
            continue
        mo_path = (TRANSLATION_PREVIEW_LOCALE_ROOT / mo_relative).resolve()
        if not mo_path.is_relative_to(TRANSLATION_PREVIEW_LOCALE_ROOT):
            preview_problems.append(f"ruta .mo fuera del directorio de vista previa para {key}")
            continue
        if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest() != record.get("source_sha256"):
            preview_problems.append(f"el catálogo fuente cambió para {key}")
        if not mo_path.is_file() or hashlib.sha256(mo_path.read_bytes()).hexdigest() != record.get("mo_sha256"):
            preview_problems.append(f"el catálogo compilado falta o cambió para {key}")
    if preview_problems:
        from django.core.exceptions import ImproperlyConfigured

        raise ImproperlyConfigured(
            "RNC_TRANSLATION_PREVIEW=1 requiere un bundle hash-pinned íntegro: "
            + "; ".join(sorted(set(preview_problems)))
        )
    LOCALE_PATHS.append(TRANSLATION_PREVIEW_LOCALE_ROOT)
LANGUAGE_COOKIE_NAME = "rnc_language"
LANGUAGE_COOKIE_HTTPONLY = True
LANGUAGE_COOKIE_SAMESITE = "Lax"
LANGUAGE_COOKIE_SECURE = not DEBUG
TIME_ZONE = "America/Havana"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(os.environ.get("RNC_STATIC_ROOT", BASE_DIR / "staticfiles"))
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "public_site.passwords.UserAttributeSimilarityValidator"
    },
    {"NAME": "public_site.passwords.MinimumLengthValidator"},
    {"NAME": "public_site.passwords.CommonPasswordValidator"},
    {"NAME": "public_site.passwords.NumericPasswordValidator"},
]

LOGIN_URL = "public_site:login"
LOGIN_REDIRECT_URL = "public_site:intake_prototype"
LOGOUT_REDIRECT_URL = "public_site:home"

# Private files are never mounted under STATIC_URL or a public MEDIA_URL.
PRIVATE_STORAGE_ROOT = Path(os.environ.get("RNC_PRIVATE_STORAGE", BASE_DIR / "private"))
PUBLIC_RELEASE_ROOT = Path(
    os.environ.get("RNC_PUBLIC_RELEASE_ROOT", BASE_DIR / "public_releases")
)
RNC_CODING_CATALOG = os.environ.get("RNC_CODING_CATALOG", "")
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.filebased.EmailBackend"
)
EMAIL_FILE_PATH = PRIVATE_STORAGE_ROOT / "mail"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "RNC <noreply@example.invalid>"
)
PASSWORD_RESET_TIMEOUT = 3600
PUBLIC_ORIGIN = os.environ.get("RNC_PUBLIC_ORIGIN", "http://127.0.0.1:8010")
PUBLIC_SITE_URL = os.environ.get("RNC_PUBLIC_SITE_URL", "http://127.0.0.1:8010")
DATA_UPLOAD_MAX_MEMORY_SIZE = 13 * 1024 * 1024
MIDDLEWARE.append("public_site.middleware.AccountSecurityMiddleware")
if not DEBUG and SECRET_KEY == "development-only-change-before-any-shared-deployment":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "Configure DJANGO_SECRET_KEY antes de un despliegue compartido."
    )
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = os.environ.get(
    "DJANGO_SECURE_SSL_REDIRECT", str(not DEBUG)
).lower() in {"1", "true", "yes"}

CSRF_FAILURE_VIEW = "public_site.errors.csrf_failure"
