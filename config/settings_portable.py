"""Read-only public website distributed with its aggregate publication."""
from .settings_public import *  # noqa: F403,F401

DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
ADMIN_SITE_URL = ""
PUBLIC_PWA_ENABLED = True
