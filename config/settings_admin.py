"""Restricted administration service settings."""

import os

from .settings import *  # noqa: F401,F403

ROOT_URLCONF = "config.urls_admin"
DEPLOYMENT_ROLE = "admin"
PUBLIC_ORIGIN = os.environ.get("RNC_ADMIN_ORIGIN", PUBLIC_ORIGIN)
