"""Tests for the locale release evidence gate."""

from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import polib

from scripts.translation_release_gate import (
    catalog_problems,
    source_language_inventory,
    validate_active_locales,
    validate_locale,
)


SURFACES = ["public", "admin", "javascript", "exports", "offline", "formats"]


def evidence_file(root, relative, content):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def make_catalog(path, msgstr="Approved %(count)s", flags=None):
    catalog = polib.POFile()
    catalog.metadata = {
        "Language": "en",
        "Content-Type": "text/plain; charset=UTF-8",
        "Plural-Forms": "nplurals=2; plural=(n != 1);",
    }
    catalog.append(polib.POEntry(
        msgid="Source %(count)s", msgstr=msgstr,
        flags=list(flags or []),
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    catalog.save(str(path))
    return path


def valid_manifest(root):
    catalog_specs = {}
    for domain in ("django", "djangojs"):
        path = make_catalog(
            root / "locale/en/LC_MESSAGES" / f"{domain}.po",
            msgstr="Approved %(count)s",
        )
        count, problems = catalog_problems(path)
        assert not problems
        catalog_specs[domain] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "reviewed_entries": count,
        }
    linguistic_report = evidence_file(root, "reports/linguistic.md", "Synthetic reviewer report\n")
    functional_report = evidence_file(root, "reports/functional.md", "Synthetic functional report\n")
    return {
        "locale": "en",
        "catalogs": catalog_specs,
        "linguistic_review": {
            "status": "approved", "reviewer": "Reviewer Example",
            "qualification": "Qualified linguist", "reviewed_at": date.today().isoformat(),
            "report": linguistic_report,
        },
        "institutional_review": {
            "status": "approved", "authority": "Authorized RNC reviewer",
            "reviewed_at": date.today().isoformat(), "evidence": "SRC-RNC-approved-reference",
        },
        "functional_validation": {
            "status": "passed", "revision": "a" * 40,
            "validated_at": date.today().isoformat(), "report": functional_report,
            "surfaces": SURFACES,
        },
        "release": {
            "status": "complete", "approved_by": "Release owner",
            "approved_at": date.today().isoformat(),
        },
    }


def valid_spanish_manifest(root):
    manifest = valid_manifest(root)
    manifest["locale"] = "es"
    djangojs = make_catalog(
        root / "locale/es/LC_MESSAGES/djangojs.po",
        msgstr="Aprobado %(count)s",
    )
    count, problems = catalog_problems(djangojs)
    assert not problems
    manifest["catalogs"] = {
        "djangojs": {
            "sha256": hashlib.sha256(djangojs.read_bytes()).hexdigest(),
            "reviewed_entries": count,
        }
    }
    manifest["source_copy_review"] = dict(zip(
        ("sha256", "reviewed_entries"), source_language_inventory(root)
    ))
    return manifest


class TranslationReleaseGateTests(unittest.TestCase):
    def test_additional_selectable_locale_requires_complete_release_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problems = validate_active_locales(
                [("en", "English"), ("es", "Español"), ("fr", "Français")],
                root=root,
                manifest_dir=root / "locale/reviews",
            )
            self.assertEqual(len(problems), 1)
            self.assertEqual(problems[0][0], "fr")
            self.assertTrue(any("falta evidencia de revisión" in item for item in problems[0][1]))

    def test_mandatory_languages_may_remain_partial_without_blocking_activation_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            problems = validate_active_locales(
                [("en", "English"), ("es", "Español")],
                root=root,
                manifest_dir=root / "locale/reviews",
            )
            self.assertEqual(problems, [])

    def test_valid_complete_evidence_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_dir = root / "locale/reviews"
            manifest_dir.mkdir(parents=True)
            manifest = valid_manifest(root)
            (manifest_dir / "en.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_locale("en", root=root, manifest_dir=manifest_dir)

            self.assertEqual(errors, [])

    def test_missing_manifest_keeps_locale_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for domain in ("django", "djangojs"):
                make_catalog(
                    root / "locale/fr/LC_MESSAGES" / f"{domain}.po",
                    flags=["fuzzy"],
                )
            errors = validate_locale(
                "fr", root=root, manifest_dir=root / "reviews"
            )

        self.assertTrue(any("falta evidencia de revisión" in error for error in errors))
        self.assertTrue(any("contiene entradas fuzzy" in error for error in errors))
        self.assertTrue(any("revisión lingüística humana" in error for error in errors))
        self.assertTrue(any("aprobación institucional" in error for error in errors))
        self.assertTrue(any("pruebas funcionales" in error for error in errors))
        self.assertTrue(any("salida debe seguir parcial" in error for error in errors))

    def test_catalog_edit_invalidates_its_review_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_dir = root / "reviews"
            manifest_dir.mkdir()
            manifest = valid_manifest(root)
            make_catalog(
                root / "locale/en/LC_MESSAGES/django.po",
                msgstr="Changed %(count)s",
            )
            (manifest_dir / "en.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_locale("en", root=root, manifest_dir=manifest_dir)

        self.assertTrue(any("hash actual" in error for error in errors))

    def test_fuzzy_entries_cannot_pass_even_with_complete_approvals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_dir = root / "reviews"
            manifest_dir.mkdir()
            manifest = valid_manifest(root)
            path = root / "locale/en/LC_MESSAGES/djangojs.po"
            make_catalog(path, flags=["fuzzy"])
            manifest["catalogs"]["djangojs"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            (manifest_dir / "en.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_locale("en", root=root, manifest_dir=manifest_dir)

        self.assertTrue(any("fuzzy" in error for error in errors))

    def test_functional_approval_without_all_surfaces_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_dir = root / "reviews"
            manifest_dir.mkdir()
            manifest = valid_manifest(root)
            manifest["functional_validation"]["surfaces"] = ["public", "admin"]
            (manifest_dir / "en.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_locale("en", root=root, manifest_dir=manifest_dir)

        self.assertTrue(any("cobertura incompleta" in error for error in errors))

    def test_modified_functional_report_invalidates_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_dir = root / "reviews"
            manifest_dir.mkdir()
            manifest = valid_manifest(root)
            (root / manifest["functional_validation"]["report"]["path"]).write_text(
                "changed after approval\n", encoding="utf-8"
            )
            (manifest_dir / "en.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_locale("en", root=root, manifest_dir=manifest_dir)

        self.assertTrue(any("reporte vigente" in error for error in errors))

    def test_spanish_requires_review_of_source_language_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_dir = root / "reviews"
            manifest_dir.mkdir()
            manifest = valid_spanish_manifest(root)
            (manifest_dir / "es.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_locale("es", root=root, manifest_dir=manifest_dir)

        self.assertEqual(errors, [])

    def test_changed_source_copy_invalidates_spanish_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_dir = root / "reviews"
            manifest_dir.mkdir()
            manifest = valid_spanish_manifest(root)
            source_path = root / "locale/en/LC_MESSAGES/django.po"
            source_catalog = polib.pofile(str(source_path))
            source_catalog.find("Source %(count)s").msgid = "Changed Spanish source %(count)s"
            source_catalog.save(str(source_path))
            (manifest_dir / "es.json").write_text(json.dumps(manifest), encoding="utf-8")

            errors = validate_locale("es", root=root, manifest_dir=manifest_dir)

        self.assertTrue(any("texto fuente español" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
