"""Apply only a fully approved, hash-matched human translation review bundle."""

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import zipfile

import polib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.languages import ACTIVE_TRANSLATION_DOMAINS, PRIORITY_LANGUAGES
from scripts.export_translation_review import (
    DOMAINS,
    FIELDS,
    LOCALES,
    _entry_key,
    review_rows,
)
from scripts.translation_release_gate import source_language_inventory

PLACEHOLDER = re.compile(r"%\(([^)]+)\)[#0 +\-]?(?:\d+)?(?:\.\d+)?[diouxXeEfFgGcrsa]|%%")
MAX_BUNDLE_BYTES = 20 * 1024 * 1024


def _plural_count(catalog):
    match = re.search(r"nplurals\s*=\s*(\d+)", catalog.metadata.get("Plural-Forms", ""))
    return int(match.group(1)) if match else 0


def _parse_plural(value, count, source, label):
    if not value:
        return None
    try:
        forms = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label}: corrected plural forms must be JSON") from exc
    if not isinstance(forms, dict) or set(forms) != {str(index) for index in range(count)}:
        raise ValueError(f"{label}: corrected plural forms must include every locale form")
    if any(not isinstance(text, str) or not text.strip() for text in forms.values()):
        raise ValueError(f"{label}: corrected plural forms cannot be empty")
    expected = sorted(PLACEHOLDER.findall(source))
    if any(sorted(PLACEHOLDER.findall(text)) != expected for text in forms.values()):
        raise ValueError(f"{label}: plural placeholders do not match the source")
    return {int(index): text for index, text in forms.items()}


def _read_rows(payload, expected_rows, locale, domain):
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{locale}/{domain}: CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != list(FIELDS):
        raise ValueError(f"{locale}/{domain}: review CSV columns changed")
    rows = list(reader)
    if len(rows) != len(expected_rows):
        raise ValueError(f"{locale}/{domain}: review row count changed")
    fixed_fields = [field for field in FIELDS if field not in {
        "review_decision", "corrected_translation", "corrected_plural_translations", "reviewer_notes"
    }]
    for index, (row, expected) in enumerate(zip(rows, expected_rows), start=2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"{locale}/{domain}:{index}: malformed CSV row")
        if any(row.get(field) != expected[field] for field in fixed_fields):
            raise ValueError(f"{locale}/{domain}:{index}: source or catalog row was altered")
        if row["review_decision"].strip().lower() != "approved":
            raise ValueError(f"{locale}/{domain}:{index}: every row must be approved before applying")
    return rows


def _stage(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
        os.fchmod(stream.fileno(), mode)
        return Path(stream.name)


def _atomic_commit(writes):
    """Commit staged byte payloads and restore already replaced files on failure."""
    staged = {}
    originals = {}
    committed = []
    try:
        for path, data in writes.items():
            path = Path(path)
            staged[path] = _stage(path, data)
        originals = {path: path.read_bytes() if path.is_file() else None for path in staged}
        for path, temporary in staged.items():
            os.replace(temporary, path)
            committed.append(path)
    except OSError:
        for path in reversed(committed):
            original = originals[path]
            if original is None:
                path.unlink(missing_ok=True)
            else:
                rollback = _stage(path, original)
                os.replace(rollback, path)
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def apply_review_bundle(bundle_path, locale, locale_root=None, report_path=None):
    """Validate every review row before atomically applying the locale PO files."""
    if locale not in LOCALES:
        raise ValueError(f"locale is not in the configured priority list: {locale}")
    locale_root = Path(locale_root or ROOT / "locale")
    bundle_path = Path(bundle_path)
    if not bundle_path.is_file() or bundle_path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("review bundle is missing or exceeds the 20 MB limit")

    try:
        with zipfile.ZipFile(bundle_path) as bundle:
            if "REVIEW-MANIFEST.json" not in bundle.namelist():
                raise ValueError("review bundle has no manifest")
            if len(bundle.namelist()) != len(set(bundle.namelist())):
                raise ValueError("review bundle contains duplicate member names")
            if sum(info.file_size for info in bundle.infolist()) > MAX_BUNDLE_BYTES:
                raise ValueError("review bundle expands beyond the 20 MB limit")
            manifest = json.loads(bundle.read("REVIEW-MANIFEST.json"))
            if manifest.get("format") != "rnc-translation-review-csv-v1":
                raise ValueError("unsupported review bundle format")
            records = [record for record in manifest.get("catalogs", []) if record.get("locale") == locale]
            if len(records) != len(DOMAINS) or {item.get("domain") for item in records} != set(DOMAINS):
                raise ValueError(f"bundle does not contain both catalogs for {locale}")
            attestation = manifest.get("linguistic_attestation")
            if not isinstance(attestation, dict) or any(
                not isinstance(attestation.get(field), str) or not attestation[field].strip()
                for field in ("reviewer", "qualification", "reviewed_at")
            ):
                raise ValueError("bundle needs reviewer, qualification, and review date attestation")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", attestation["reviewed_at"]):
                raise ValueError("review date must use YYYY-MM-DD")
            try:
                from datetime import date
                date.fromisoformat(attestation["reviewed_at"])
            except ValueError as exc:
                raise ValueError("review date is invalid") from exc

            staged_catalogs = {}
            reviewed = {}
            protected_paths = {bundle_path.resolve()}
            for record in records:
                domain = record["domain"]
                expected_rows, target_path, english_path, source_only = review_rows(locale, domain, locale_root)
                protected_paths.update({target_path.resolve(), english_path.resolve()})
                if record.get("entries") != len(expected_rows):
                    raise ValueError(f"{locale}/{domain}: manifest row count changed")
                if record.get("target_catalog") != str(target_path.relative_to(locale_root.parent)):
                    raise ValueError(f"{locale}/{domain}: manifest target path changed")
                if record.get("target_catalog_sha256") != hashlib.sha256(target_path.read_bytes()).hexdigest():
                    raise ValueError(f"{locale}/{domain}: catalog changed since export")
                if record.get("english_reference_sha256") != hashlib.sha256(english_path.read_bytes()).hexdigest():
                    raise ValueError(f"{locale}/{domain}: English reference changed since export")
                member = record.get("file")
                if member != f"{locale}/{domain}.csv" or member not in bundle.namelist():
                    raise ValueError(f"{locale}/{domain}: review CSV is missing or misnamed")
                rows = _read_rows(bundle.read(member), expected_rows, locale, domain)
                reviewed[domain] = len(rows)
                if source_only:
                    for row, expected in zip(rows, expected_rows):
                        corrected = row["corrected_translation"].strip()
                        corrected_plural = row["corrected_plural_translations"].strip()
                        if (
                            (corrected and corrected != expected["current_translation"])
                            or corrected_plural
                        ):
                            raise ValueError(
                                "Spanish source-copy changes must be applied to source code and re-extracted"
                            )
                    continue

                target = polib.pofile(str(target_path), check_for_duplicates=True)
                target_entries = {_entry_key(entry): entry for entry in target if entry.msgid and not entry.obsolete}
                for row, expected in zip(rows, expected_rows):
                    key = (expected["context"], expected["source_spanish"], expected["source_plural_spanish"])
                    entry = target_entries[key]
                    corrected = row["corrected_translation"].strip()
                    translation = corrected or row["current_translation"]
                    expected_placeholders = sorted(PLACEHOLDER.findall(entry.msgid))
                    plural = _parse_plural(
                        row["corrected_plural_translations"],
                        _plural_count(target),
                        entry.msgid,
                        f"{locale}/{domain}",
                    )
                    if entry.msgid_plural:
                        if corrected:
                            raise ValueError(f"{locale}/{domain}: plural entries must use corrected_plural_translations")
                        if row["corrected_plural_translations"].strip() and not row["reviewer_notes"].strip():
                            raise ValueError(f"{locale}/{domain}: plural correction needs reviewer notes")
                        if plural is not None:
                            entry.msgstr_plural = plural
                        if any(not entry.msgstr_plural.get(index, "").strip() for index in range(_plural_count(target))):
                            raise ValueError(f"{locale}/{domain}: approved plural forms are incomplete")
                        if any(
                            sorted(PLACEHOLDER.findall(text)) != expected_placeholders
                            for text in entry.msgstr_plural.values()
                        ):
                            raise ValueError(f"{locale}/{domain}: plural placeholders do not match source")
                    elif row["corrected_plural_translations"].strip():
                        raise ValueError(f"{locale}/{domain}: singular entry cannot define plural forms")
                    else:
                        if not translation.strip() or sorted(PLACEHOLDER.findall(translation)) != expected_placeholders:
                            raise ValueError(f"{locale}/{domain}: approved singular text has empty or changed placeholders")
                        if corrected and corrected != entry.msgstr and not row["reviewer_notes"].strip():
                            raise ValueError(f"{locale}/{domain}: changed translation needs reviewer notes")
                    entry.msgstr = translation
                    entry.flags = [flag for flag in entry.flags if flag != "fuzzy"]
                staged_catalogs[target_path] = str(target).encode("utf-8")

    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("review bundle is corrupt or internally inconsistent") from exc

    report = {
        "locale": locale,
        "linguistic_review": {
            "status": "approved",
            "reviewer": attestation["reviewer"].strip(),
            "qualification": attestation["qualification"].strip(),
            "reviewed_at": attestation["reviewed_at"],
        },
        "review_bundle": {
            "name": bundle_path.name,
            "sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        },
        "catalogs": {},
    }
    for domain in ACTIVE_TRANSLATION_DOMAINS.get(locale, DOMAINS):
        path = locale_root / locale / "LC_MESSAGES" / f"{domain}.po"
        payload = staged_catalogs.get(path, path.read_bytes())
        report["catalogs"][domain] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "reviewed_entries": reviewed[domain],
        }
    if locale == "es":
        digest, count = source_language_inventory(locale_root.parent)
        report["source_copy_review"] = {"sha256": digest, "reviewed_entries": reviewed["django"]}

    writes = dict(staged_catalogs)
    if report_path:
        report_path = Path(report_path)
        if report_path.resolve() in protected_paths:
            raise ValueError("report path cannot replace a catalog or input review bundle")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        writes[report_path] = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if writes:
        _atomic_commit(writes)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", required=True, choices=LOCALES)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True, help="linguistic evidence JSON to create")
    parser.add_argument("--locale-root", type=Path, default=ROOT / "locale")
    args = parser.parse_args(argv)
    try:
        report = apply_review_bundle(args.bundle, args.locale, args.locale_root, args.report)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Applied reviewed catalogs for {args.locale}; {sum(x['reviewed_entries'] for x in report['catalogs'].values())} entries reviewed.")
    print(f"Linguistic evidence: {args.report}")
    print(f"Report SHA-256: {hashlib.sha256(args.report.read_bytes()).hexdigest()}")
    print("Locale activation and institutional/functional release approvals remain separate gate steps.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
