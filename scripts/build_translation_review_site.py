"""Build a static, browser-based review site from the current PO catalogs."""

import argparse
import json
from pathlib import Path
import sys

import polib

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "translation-review-site"
sys.path.insert(0, str(ROOT))
DOMAINS = ("django", "djangojs")


def read_catalog(locale, domain):
    path = ROOT / "locale" / locale / "LC_MESSAGES" / f"{domain}.po"
    if not path.is_file():
        return {}
    catalog = polib.pofile(str(path), check_for_duplicates=True)
    return {
        (entry.msgctxt or "", entry.msgid): entry
        for entry in catalog
        if entry.msgid and not entry.obsolete
    }


def build_data():
    from config.languages import PRIORITY_LANGUAGES

    source_catalogs = {domain: read_catalog("en", domain) for domain in DOMAINS}
    languages = []
    for code, english_name, native_name, active in PRIORITY_LANGUAGES:
        language = {
            "code": code,
            "englishName": english_name,
            "nativeName": native_name,
            "active": active,
            "draft": not active,
            "rtl": code in {"ar", "ur"},
            "domains": {},
        }
        for domain in DOMAINS:
            target_catalog = read_catalog(code, domain)
            rows = []
            for (_context, msgid), source_entry in source_catalogs[domain].items():
                target_entry = target_catalog.get((source_entry.msgctxt or "", msgid))
                if code == "es" and domain == "django":
                    target = msgid
                    flags = []
                    origin = "source"
                else:
                    target = target_entry.msgstr if target_entry else ""
                    flags = target_entry.flags if target_entry else []
                    origin = "catalog"
                if not target.strip() and source_entry.msgid_plural:
                    target = " / ".join(
                        value for _, value in sorted(
                            (target_entry.msgstr_plural.items() if target_entry else []),
                            key=lambda item: int(item[0]),
                        ) if value.strip()
                    )
                rows.append({
                    "source": msgid,
                    "pluralSource": source_entry.msgid_plural,
                    "target": target,
                    "context": source_entry.msgctxt or "",
                    "references": [
                        f"{filename}:{line}".rstrip(":")
                        for filename, line in source_entry.occurrences[:4]
                    ],
                    "fuzzy": "fuzzy" in flags,
                    "missing": not bool(target.strip()),
                    "origin": origin,
                })
            language["domains"][domain] = rows
        languages.append(language)
    return {
        "title": "RNC Web · Revisión de traducciones",
        "generatedFrom": "locale/*.po",
        "languages": languages,
    }


def build(output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(
        (SITE / "index.html").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (output_dir / "review.js").write_text(
        (SITE / "review.js").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (output_dir / "style.css").write_text(
        (SITE / "style.css").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (output_dir / "translations.json").write_text(
        json.dumps(build_data(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    build(args.output_dir.resolve())
    print(f"Sitio de revisión creado en {args.output_dir.resolve()}")


if __name__ == "__main__":
    main()
