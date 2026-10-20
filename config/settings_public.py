"""Public service settings with no private database, storage, or admin routes."""

from .settings import *  # noqa: F401,F403

ROOT_URLCONF = "config.urls_public"
DEPLOYMENT_ROLE = "public"

# The public process has no application models or authentication routes installed.
INSTALLED_APPS = ["django.contrib.staticfiles"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "config.public_context.navigation",
            ],
        },
    }
]

# Fail closed if a future public view accidentally tries to access a database.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.dummy",
    }
}
PRIVATE_STORAGE_ROOT = None
EMAIL_FILE_PATH = None
PUBLIC_RELEASE_ROOT = Path(
    os.environ.get("RNC_PUBLIC_RELEASE_ROOT", BASE_DIR / "public_releases")
)
