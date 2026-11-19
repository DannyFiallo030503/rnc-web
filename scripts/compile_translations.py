"""Compile gettext catalogs using the project test dependency polib.

All configured active catalogs are validated before any .mo output is written,
so a missing or incomplete locale cannot leave a partially updated catalog set.
"""

from pathlib import Path
import sys

import polib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config.languages import ACTIVE_TRANSLATION_DOMAINS


ROOT = Path(__file__).resolve().parents[1]
LOCALE_ROOT = ROOT / "locale"


def catalog_paths(locale_root, active_domains):
    return sorted(
        locale_root / language / "LC_MESSAGES" / f"{domain}.po"
        for language, domains in active_domains.items()
        for domain in domains
    )


def approved_catalog(catalog):
    approved = polib.POFile()
    approved.metadata = dict(catalog.metadata)
    approved.metadata_is_fuzzy = catalog.metadata_is_fuzzy
    approved.wrapwidth = catalog.wrapwidth
    for entry in catalog:
        if "fuzzy" not in entry.flags:
            approved.append(entry)
    return approved


def validated_catalogs(locale_root, active_domains):
    """Load and validate every active catalog before producing any output."""
    paths = catalog_paths(locale_root, active_domains)
    if not paths:
        return [], ["No hay catálogos activos configurados para compilar."]
    errors = []
    loaded = []
    for path in paths:
        if not path.is_file():
            display_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            errors.append(f"Falta el catálogo activo {display_path}")
            continue
        catalog = polib.pofile(str(path), check_for_duplicates=True)
        untranslated = [entry.msgid for entry in catalog if not entry.obsolete and not entry.translated()]
        if untranslated:
            display_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            errors.append(f"{display_path}: {len(untranslated)} mensajes sin traducir")
        loaded.append((path, catalog))
    return (loaded, []) if not errors else ([], errors)


def compile_catalogs(locale_root, active_domains):
    loaded, errors = validated_catalogs(locale_root, active_domains)
    if errors:
        return [], errors
    compiled = []
    for path, catalog in loaded:
        output = path.with_suffix(".mo")
        # Fuzzy PO entries are suggestions, never runtime translations.
        approved_catalog(catalog).save_as_mofile(str(output))
        compiled.append((path, output, len(catalog)))
    return compiled, []


def main():
    compiled, errors = compile_catalogs(LOCALE_ROOT, ACTIVE_TRANSLATION_DOMAINS)
    for path, output, count in compiled:
        print(f"{path.relative_to(ROOT)} → {output.relative_to(ROOT)} ({count} mensajes)")
    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
