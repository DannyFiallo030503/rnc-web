"""Verify terminal offline messages exist for every active locale.

The service worker cannot load gettext at runtime while disconnected, so these
two cold-start messages are mirrored from the active Django catalog. Once a
locale is activated, this check requires the worker mirror to match its PO.
"""

import json
from pathlib import Path
import re
import sys

import polib


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "static/js/service-worker.js"
REGISTER_WORKER = ROOT / "static/js/register-service-worker.js"
SOURCE_MESSAGE = "La consulta local aún no está disponible en este dispositivo."
MAP = re.compile(r"const\s+FALLBACK_MESSAGES\s*=\s*\{(?P<body>.*?)\}\s*;", re.S)
ENTRY = re.compile(r"(?P<locale>[a-z][a-z0-9-]*)\s*:\s*(?P<value>\"(?:\\.|[^\"\\])*\")", re.I)


def extract_fallback_messages(source):
    match = MAP.search(source)
    if not match:
        return {}
    messages = {}
    for entry in ENTRY.finditer(match.group("body")):
        locale = entry.group("locale").lower()
        try:
            messages[locale] = json.loads(entry.group("value"))
        except json.JSONDecodeError:
            messages[locale] = None
    return messages


def expected_fallbacks(active_languages, catalogs_root=ROOT / "locale"):
    expected = {}
    english_catalog = polib.pofile(
        str(catalogs_root / "en/LC_MESSAGES/django.po")
    )
    english_entry = english_catalog.find(SOURCE_MESSAGE)
    for locale, _display_name in active_languages:
        if locale == "es":
            expected[locale] = SOURCE_MESSAGE
            continue
        catalog_path = catalogs_root / locale / "LC_MESSAGES/django.po"
        if not catalog_path.exists():
            expected[locale] = None
            continue
        entry = polib.pofile(str(catalog_path)).find(SOURCE_MESSAGE)
        expected[locale] = (
            entry.msgstr
            if entry and entry.msgstr.strip() and "fuzzy" not in entry.flags
            else None
        )
    if english_entry and english_entry.msgstr.strip() and "fuzzy" not in english_entry.flags:
        expected["en"] = english_entry.msgstr
    else:
        expected["en"] = None
    return expected


def validate_fallback_messages(messages, expected):
    failures = []
    if set(messages) != set(expected):
        failures.append(
            "Locales del mapa service worker distintos a los idiomas activos: "
            f"mapa={sorted(messages)}, activos={sorted(expected)}"
        )
    for locale, translated in expected.items():
        if not translated:
            failures.append(f"{locale}: falta traducción activa de {SOURCE_MESSAGE!r}")
        elif messages.get(locale) != translated:
            failures.append(
                f"{locale}: mensaje de fallback no coincide con su catálogo activo"
            )
    return failures


def validate_offline_language_precedence(source):
    """Keep a device's confirmed language ahead of a stale server cookie."""
    resolution = re.compile(
        r"const\s+language\s*=\s*validLanguage\(requested\)\s*\?\s*requested\s*:\s*saved\s*\|\|\s*cookie"
    )
    if not resolution.search(source):
        return ["El idioma guardado localmente debe prevalecer sobre la cookie al desconectarse"]
    return []


def validate_language_change_sync_guard(source):
    """Avoid a delayed page-load sync overwriting a newer locale submission."""
    pending_flag = re.search(r"let\s+languageChangePending\s*=\s*false", source)
    guarded_sync = re.search(
        r"const\s+syncLanguage\s*=\s*\(\)\s*=>\s*languageChangePending\s*\?",
        source,
    )
    submission_guard = re.search(
        r"languageChangePending\s*=\s*true\s*;\s*await\s+postLanguage\(selected\)",
        source,
    )
    if not (pending_flag and guarded_sync and submission_guard):
        return [
            "El envío de idioma debe impedir que una sincronización tardía restablezca el locale anterior"
        ]
    return []


def validate_language_message_queue(source):
    """Serialize worker writes so overlapping page messages cannot win out of order."""
    queue = re.search(r"let\s+languageMessageQueue\s*=\s*Promise\.resolve\(\)", source)
    queued_save = re.search(
        r"const\s+saveLanguage\s*=\s*languageMessageQueue\.then\(\(\)\s*=>\s*caches\.open\(CACHE\)",
        source,
    )
    queue_update = re.search(
        r"languageMessageQueue\s*=\s*saveLanguage\.catch\(\(\)\s*=>\s*\{\}\)",
        source,
    )
    awaited_save = re.search(r"event\.waitUntil\(saveLanguage\)", source)
    if not all((queue, queued_save, queue_update, awaited_save)):
        return [
            "Los mensajes de idioma del service worker deben serializar escrituras de caché para conservar el último locale solicitado"
        ]
    return []


def main():
    sys.path.insert(0, str(ROOT))
    from config.languages import ACTIVE_LANGUAGES

    source = WORKER.read_text(encoding="utf-8")
    register_source = REGISTER_WORKER.read_text(encoding="utf-8")
    messages = extract_fallback_messages(source)
    expected = expected_fallbacks(ACTIVE_LANGUAGES)
    failures = validate_fallback_messages(messages, expected)
    failures.extend(validate_offline_language_precedence(source))
    failures.extend(validate_language_message_queue(source))
    failures.extend(validate_language_change_sync_guard(register_source))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(
        "OK: fallback terminal del service worker coincide con gettext para "
        + ", ".join(sorted(expected))
        + "; cambio de locale protege la caché frente a sincronizaciones obsoletas"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
