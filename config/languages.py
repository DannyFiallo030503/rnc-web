"""Language rollout priority and explicit draft-preview configuration."""

import os

PRIORITY_LANGUAGES = (
    ("en", "English", "English", True),
    ("zh-hans", "Mandarin Chinese (Simplified)", "简体中文", False),
    ("hi", "Hindi", "हिन्दी", False),
    ("es", "Spanish", "Español", True),
    ("ar", "Modern Standard Arabic", "العربية", False),
    ("fr", "French", "Français", False),
    ("bn", "Bengali", "বাংলা", False),
    ("pt-br", "Brazilian Portuguese", "Português (Brasil)", False),
    ("id", "Indonesian", "Bahasa Indonesia", False),
    ("ur", "Urdu", "اردو", False),
    ("ru", "Russian", "Русский", False),
)

# English and Spanish remain selectable because they are mandatory product
# languages. English coverage is partial; this list is not a claim of completion.
ACTIVE_LANGUAGES = tuple(
    (code, native_name)
    for code, _english_name, native_name, active in PRIORITY_LANGUAGES
    if active
)

DRAFT_LANGUAGES = tuple(
    (code, native_name)
    for code, _english_name, native_name, active in PRIORITY_LANGUAGES
    if not active
)


def translation_preview_enabled(environment=None):
    """Return whether unapproved catalogs are explicitly requested for preview."""
    environment = os.environ if environment is None else environment
    return environment.get("RNC_TRANSLATION_PREVIEW", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def selectable_languages(preview_enabled=False):
    """Production selection stays approved-only unless preview is explicitly enabled."""
    if preview_enabled:
        return ACTIVE_LANGUAGES + DRAFT_LANGUAGES
    return ACTIVE_LANGUAGES

# Domains served by the normal product build. English/Spanish are mandatory
# and still gated as partial; draft locales use a separate preview bundle.
ACTIVE_TRANSLATION_DOMAINS = {
    "en": ("django", "djangojs"),
    "es": ("djangojs",),
}
