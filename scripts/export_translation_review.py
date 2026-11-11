"""Create a hash-pinned CSV review bundle for one or more priority locales."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import polib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.languages import PRIORITY_LANGUAGES

LOCALES = tuple(code for code, _english, _native, _active in PRIORITY_LANGUAGES)
DOMAINS = ("django", "djangojs")
FIELDS = (
    "domain", "context", "source_spanish", "source_plural_spanish",
    "english_reference", "english_plural_reference", "current_translation",
    "current_plural_translations", "translator_comments", "review_comments",
    "references", "fuzzy", "review_decision", "corrected_translation",
    "corrected_plural_translations", "reviewer_notes",
)


def _entry_key(entry):
    return entry.msgctxt or "", entry.msgid, entry.msgid_plural or ""


def _plural_json(forms):
    return json.dumps(
        {str(index): value for index, value in sorted(forms.items())},
        ensure_ascii=False,
        sort_keys=True,
    ) if forms else ""


def review_rows(locale, domain, locale_root):
    """Return source-aligned review rows; Spanish Django reviews source copy."""
    locale_root = Path(locale_root)
    english_path = locale_root / "en/LC_MESSAGES" / f"{domain}.po"
    if not english_path.is_file():
        raise ValueError(f"missing English reference catalog: {english_path}")
    english = polib.pofile(str(english_path), check_for_duplicates=True)
    english_entries = {
        _entry_key(entry): entry for entry in english if entry.msgid and not entry.obsolete
    }

    source_only = locale == "es" and domain == "django"
    target_path = locale_root / locale / "LC_MESSAGES" / f"{domain}.po"
    if source_only:
        target_entries = english_entries
    else:
        if not target_path.is_file():
            raise ValueError(f"missing target catalog: {target_path}")
        target = polib.pofile(str(target_path), check_for_duplicates=True)
        target_entries = {
            _entry_key(entry): entry for entry in target if entry.msgid and not entry.obsolete
        }
    if target_entries.keys() != english_entries.keys():
        raise ValueError(f"catalog inventory mismatch: {locale}/{domain}")

    rows = []
    for key, reference in english_entries.items():
        entry = target_entries[key]
        if source_only:
            translation = reference.msgid
            plural_translation = (
                {index: text for index, text in enumerate((reference.msgid_plural,))}
                if reference.msgid_plural else {}
            )
        else:
            translation = entry.msgstr
            plural_translation = entry.msgstr_plural
        rows.append({
            "domain": domain,
            "context": reference.msgctxt or "",
            "source_spanish": reference.msgid,
            "source_plural_spanish": reference.msgid_plural or "",
            "english_reference": reference.msgstr,
            "english_plural_reference": _plural_json(reference.msgstr_plural),
            "current_translation": translation,
            "current_plural_translations": _plural_json(plural_translation),
            "translator_comments": reference.comment,
            "review_comments": reference.tcomment,
            "references": " ".join(
                f"{filename}:{line}" for filename, line in reference.occurrences
            ),
            "fuzzy": "yes" if "fuzzy" in entry.flags else "no",
            "review_decision": "",
            "corrected_translation": "",
            "corrected_plural_translations": "",
            "reviewer_notes": "",
        })
    return rows, target_path if not source_only else english_path, english_path, source_only


def _csv_bytes(rows):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, extrasaction="raise")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def export_review_bundle(locales, output_path, locale_root=None):
    locale_root = Path(locale_root or ROOT / "locale")
    output_path = Path(output_path)
    if not locales or any(locale not in LOCALES for locale in locales):
        raise ValueError("choose one or more configured priority locales")
    if len(set(locales)) != len(locales):
        raise ValueError("locales must not be repeated")

    records = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for locale in locales:
            for domain in DOMAINS:
                rows, target_path, english_path, source_only = review_rows(
                    locale, domain, locale_root
                )
                member = f"{locale}/{domain}.csv"
                payload = _csv_bytes(rows)
                bundle.writestr(member, payload)
                target_digest = hashlib.sha256(target_path.read_bytes()).hexdigest()
                records.append({
                    "locale": locale,
                    "domain": domain,
                    "file": member,
                    "entries": len(rows),
                    "target_catalog": str(target_path.relative_to(locale_root.parent)),
                    "target_catalog_sha256": target_digest,
                    "english_reference_sha256": hashlib.sha256(english_path.read_bytes()).hexdigest(),
                    "source_copy_review": source_only,
                })
        manifest = {
            "format": "rnc-translation-review-csv-v1",
            "instruction": "Review every row. Set linguistic_attestation reviewer, qualification and reviewed_at. Keep identifiers/placeholders intact. Set review_decision to approved or needs_changes; record reviewer notes for changes. This bundle is not release approval.",
            "catalogs": records,
            "linguistic_attestation": {
                "reviewer": "",
                "qualification": "",
                "reviewed_at": "",
            },
        }
        bundle.writestr(
            "REVIEW-MANIFEST.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )
        bundle.writestr(
            "README.txt",
            "RNC web translation review bundle\n\n"
            "Review every row in each CSV. source_spanish is the canonical source; "
            "english_reference is a cross-check, not an authority for institutional "
            "or epidemiological meaning. Mark review_decision as approved or "
            "needs_changes, enter corrected_translation or corrected_plural_translations "
            "when needed, and record "
            "reviewer_notes. In REVIEW-MANIFEST.json fill linguistic_attestation with "
            "reviewer, qualification and reviewed_at (YYYY-MM-DD). Do not change "
            "codes, placeholders, or source meanings.\n\n"
            "Return this completed bundle as the linguistic review report. The "
            "release gate still requires independent institutional and functional "
            "evidence. The manifest pins the catalogs reviewed when this bundle "
            "was created; any later catalog edits require a fresh review.\n",
        )
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", choices=LOCALES, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True, help="destination .zip")
    parser.add_argument("--locale-root", type=Path, default=ROOT / "locale")
    args = parser.parse_args(argv)
    try:
        records = export_review_bundle(args.locale, args.output, args.locale_root)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.error(str(exc))
    for record in records:
        print(f"{record['locale']}/{record['domain']}: {record['entries']} filas → {record['file']}")
    print(f"Bundle: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
