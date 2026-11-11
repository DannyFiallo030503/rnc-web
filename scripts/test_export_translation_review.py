"""Tests for reproducible, non-approving translation review bundles."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import polib

from scripts.export_translation_review import export_review_bundle
from scripts.apply_translation_review import apply_review_bundle
from scripts.translation_release_gate import validate_locale


class TranslationReviewExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "locale"
        for locale in ("en", "fr", "es"):
            (self.root / locale / "LC_MESSAGES").mkdir(parents=True)
        self._write("en", "django", "Hello", "Hola", comment="Context: greeting", extracted="Use as a short label")
        self._write("en", "djangojs", "Next", "Siguiente")
        self._write("fr", "django", "Bonjour", "Hola", flags=["fuzzy"])
        self._write("fr", "djangojs", "Suivant", "Siguiente", flags=["fuzzy"])
        self._write("es", "djangojs", "Siguiente", "Siguiente")

    def _write(self, locale, domain, target, source, *, comment="", extracted="", flags=None):
        catalog = polib.POFile()
        entry = polib.POEntry(
            msgid=source,
            msgstr=target,
            comment=comment,
            tcomment=extracted,
            occurrences=[("templates/base.html", "20")],
            flags=flags or [],
        )
        catalog.append(entry)
        catalog.save(str(self.root / locale / "LC_MESSAGES" / f"{domain}.po"))

    def test_bundle_contains_source_english_reference_target_and_review_columns(self):
        output = Path(self.temp.name) / "review.zip"
        records = export_review_bundle(["fr"], output, self.root)
        self.assertEqual([record["entries"] for record in records], [1, 1])
        with zipfile.ZipFile(output) as bundle:
            rows = list(csv.DictReader(io.StringIO(bundle.read("fr/django.csv").decode("utf-8-sig"))))
            manifest = json.loads(bundle.read("REVIEW-MANIFEST.json"))
        row = rows[0]
        self.assertEqual(row["source_spanish"], "Hola")
        self.assertEqual(row["english_reference"], "Hello")
        self.assertEqual(row["current_translation"], "Bonjour")
        self.assertEqual(row["translator_comments"], "Context: greeting")
        self.assertEqual(row["review_comments"], "Use as a short label")
        self.assertEqual(row["fuzzy"], "yes")
        self.assertEqual(row["review_decision"], "")
        self.assertEqual(manifest["format"], "rnc-translation-review-csv-v1")
        self.assertEqual(manifest["catalogs"][0]["entries"], 1)

    def test_spanish_source_review_uses_msgid_when_there_is_no_spanish_django_po(self):
        output = Path(self.temp.name) / "review.zip"
        export_review_bundle(["es"], output, self.root)
        with zipfile.ZipFile(output) as bundle:
            rows = list(csv.DictReader(io.StringIO(bundle.read("es/django.csv").decode("utf-8-sig"))))
            manifest = json.loads(bundle.read("REVIEW-MANIFEST.json"))
        self.assertEqual(rows[0]["source_spanish"], "Hola")
        self.assertEqual(rows[0]["current_translation"], "Hola")
        self.assertTrue(manifest["catalogs"][0]["source_copy_review"])

    def test_inventory_mismatch_and_repeated_or_unknown_locales_fail(self):
        output = Path(self.temp.name) / "review.zip"
        path = self.root / "fr/LC_MESSAGES/django.po"
        catalog = polib.pofile(str(path))
        catalog.append(polib.POEntry(msgid="Otro", msgstr="Autre"))
        catalog.save(str(path))
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            export_review_bundle(["fr"], output, self.root)
        with self.assertRaisesRegex(ValueError, "must not be repeated"):
            export_review_bundle(["fr", "fr"], output, self.root)
        with self.assertRaisesRegex(ValueError, "priority locales"):
            export_review_bundle(["xx"], output, self.root)

    def _completed_bundle(self, locale="fr", *, decision="approved", correction=""):
        source = Path(self.temp.name) / "source.zip"
        reviewed = Path(self.temp.name) / f"{locale}-reviewed.zip"
        export_review_bundle([locale], source, self.root)
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(reviewed, "w", zipfile.ZIP_DEFLATED) as output:
            manifest = json.loads(original.read("REVIEW-MANIFEST.json"))
            manifest["linguistic_attestation"] = {
                "reviewer": "Revisora de prueba",
                "qualification": "Competencia lingüística declarada para pruebas",
                "reviewed_at": "2026-11-11",
            }
            output.writestr("REVIEW-MANIFEST.json", json.dumps(manifest, ensure_ascii=False))
            for member in original.namelist():
                if member == "REVIEW-MANIFEST.json":
                    continue
                payload = original.read(member)
                if member.endswith(".csv"):
                    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
                    for row in rows:
                        row["review_decision"] = decision
                        if correction and not row["source_plural_spanish"]:
                            row["corrected_translation"] = correction
                            row["reviewer_notes"] = "Corrección revisada en prueba"
                    buffer = io.StringIO(newline="")
                    writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                    payload = ("\ufeff" + buffer.getvalue()).encode("utf-8")
                output.writestr(member, payload)
        return reviewed

    def test_only_fully_approved_rows_apply_and_report_post_review_hashes(self):
        bundle = self._completed_bundle(correction="Bonjour corrigé")
        report_path = Path(self.temp.name) / "review-report.json"
        report = apply_review_bundle(bundle, "fr", self.root, report_path)
        catalog = polib.pofile(str(self.root / "fr/LC_MESSAGES/django.po"))
        entry = catalog.find("Hola")
        self.assertEqual(entry.msgstr, "Bonjour corrigé")
        self.assertNotIn("fuzzy", entry.flags)
        self.assertEqual(report["catalogs"]["django"]["reviewed_entries"], 1)
        self.assertEqual(
            set(report["linguistic_review"]),
            {"status", "reviewer", "qualification", "reviewed_at"},
        )
        self.assertEqual(json.loads(report_path.read_text())["linguistic_review"]["reviewer"], "Revisora de prueba")
        self.assertEqual(report["catalogs"]["django"]["sha256"], __import__("hashlib").sha256((self.root / "fr/LC_MESSAGES/django.po").read_bytes()).hexdigest())

    def test_unapproved_or_placeholder_mismatched_reviews_do_not_modify_catalogs(self):
        path = self.root / "fr/LC_MESSAGES/django.po"
        before = path.read_bytes()
        incomplete = self._completed_bundle(decision="")
        with self.assertRaisesRegex(ValueError, "every row must be approved"):
            apply_review_bundle(incomplete, "fr", self.root)
        self.assertEqual(path.read_bytes(), before)

        # The source fixture is replaced with an interpolated message to cover
        # placeholder protection before any write.
        source = polib.pofile(str(self.root / "en/LC_MESSAGES/django.po"))
        source[0].msgid = "Hola %(name)s"
        source[0].msgstr = "Hello %(name)s"
        source.save(str(self.root / "en/LC_MESSAGES/django.po"))
        target = polib.pofile(str(path))
        target[0].msgid = "Hola %(name)s"
        target[0].msgstr = "Bonjour %(name)s"
        target.save(str(path))
        malformed = self._completed_bundle(correction="Bonjour %(other)s")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "changed placeholders"):
            apply_review_bundle(malformed, "fr", self.root)
        self.assertEqual(path.read_bytes(), before)

    def test_spanish_source_review_is_evidenced_without_creating_django_catalog(self):
        bundle = self._completed_bundle("es")
        report = apply_review_bundle(bundle, "es", self.root)
        self.assertNotIn("django.po", [path.name for path in (self.root / "es/LC_MESSAGES").glob("*.po")])
        self.assertEqual(report["source_copy_review"]["reviewed_entries"], 1)
        self.assertIn("djangojs", report["catalogs"])

    def test_catalog_hash_mismatch_stops_before_writing(self):
        bundle = self._completed_bundle()
        path = self.root / "fr/LC_MESSAGES/django.po"
        before = path.read_bytes()
        catalog = polib.pofile(str(path))
        catalog[0].msgstr = "Changed after export"
        catalog.save(str(path))
        changed = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "catalog changed since export"):
            apply_review_bundle(bundle, "fr", self.root)
        self.assertNotEqual(changed, before)
        self.assertEqual(path.read_bytes(), changed)

    def test_failed_multi_catalog_commit_rolls_back_prior_catalog_writes(self):
        bundle = self._completed_bundle()
        paths = [self.root / f"fr/LC_MESSAGES/{domain}.po" for domain in ("django", "djangojs")]
        before = {path: path.read_bytes() for path in paths}
        report_path = Path(self.temp.name) / "report.json"
        real_replace = os.replace
        calls = 0

        def fail_second_replace(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second catalog write failure")
            return real_replace(source, target)

        with patch("scripts.apply_translation_review.os.replace", side_effect=fail_second_replace):
            with self.assertRaisesRegex(OSError, "simulated second catalog write failure"):
                apply_review_bundle(bundle, "fr", self.root, report_path)
        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        self.assertFalse(report_path.exists())

    def test_report_path_cannot_overwrite_catalogs_or_the_input_bundle(self):
        bundle = self._completed_bundle()
        protected = [
            bundle,
            self.root / "fr/LC_MESSAGES/django.po",
            self.root / "en/LC_MESSAGES/django.po",
        ]
        before = {path: path.read_bytes() for path in protected}
        for path in protected:
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "cannot replace a catalog or input review bundle"):
                    apply_review_bundle(bundle, "fr", self.root, path)
        self.assertEqual({path: path.read_bytes() for path in protected}, before)

    def test_applied_review_report_integrates_with_release_gate(self):
        bundle = self._completed_bundle()
        project_root = Path(self.temp.name)
        linguistic_path = project_root / "linguistic-review.json"
        report = apply_review_bundle(bundle, "fr", self.root, linguistic_path)
        functional_path = project_root / "functional-report.json"
        functional_path.write_text('{"checks": "synthetic integration fixture"}\n', encoding="utf-8")
        manifest = {
            "locale": "fr",
            "catalogs": report["catalogs"],
            "linguistic_review": {
                **report["linguistic_review"],
                "report": {
                    "path": "linguistic-review.json",
                    "sha256": hashlib.sha256(linguistic_path.read_bytes()).hexdigest(),
                },
            },
            "institutional_review": {
                "status": "approved",
                "authority": "synthetic test fixture",
                "reviewed_at": "2026-11-11",
                "evidence": "synthetic test evidence",
            },
            "functional_validation": {
                "status": "passed",
                "revision": "a" * 40,
                "validated_at": "2026-11-11",
                "report": {
                    "path": "functional-report.json",
                    "sha256": hashlib.sha256(functional_path.read_bytes()).hexdigest(),
                },
                "surfaces": ["public", "admin", "javascript", "exports", "offline", "formats"],
            },
            "release": {"status": "complete", "approved_by": "synthetic test fixture", "approved_at": "2026-11-11"},
        }
        reviews = self.root / "reviews"
        reviews.mkdir()
        (reviews / "fr.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertEqual(validate_locale("fr", project_root), [])

    def test_plural_review_updates_every_form_and_preserves_placeholder_names(self):
        for locale, forms in (
            ("en", {0: "%(count)s case", 1: "%(count)s cases"}),
            ("fr", {0: "%(count)s cas", 1: "%(count)s cas"}),
        ):
            path = self.root / locale / "LC_MESSAGES/djangojs.po"
            catalog = polib.pofile(str(path))
            catalog.metadata["Plural-Forms"] = "nplurals=2; plural=(n != 1);"
            catalog.append(polib.POEntry(
                msgid="%(count)s caso",
                msgid_plural="%(count)s casos",
                msgstr_plural=forms,
                flags=["fuzzy"] if locale == "fr" else [],
            ))
            catalog.save(str(path))
        source = Path(self.temp.name) / "review-source.zip"
        reviewed = Path(self.temp.name) / "reviewed.zip"
        export_review_bundle(["fr"], source, self.root)
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(reviewed, "w", zipfile.ZIP_DEFLATED) as output:
            manifest = json.loads(original.read("REVIEW-MANIFEST.json"))
            manifest["linguistic_attestation"] = {
                "reviewer": "Revisora",
                "qualification": "Competencia declarada",
                "reviewed_at": "2026-11-11",
            }
            output.writestr("REVIEW-MANIFEST.json", json.dumps(manifest, ensure_ascii=False))
            for member in original.namelist():
                if member == "REVIEW-MANIFEST.json":
                    continue
                payload = original.read(member)
                if member == "fr/djangojs.csv":
                    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
                    plural = next(row for row in rows if row["source_plural_spanish"])
                    plural["review_decision"] = "approved"
                    plural["corrected_plural_translations"] = json.dumps({
                        "0": "%(count)s cas corrigé",
                        "1": "%(count)s cas corrigés",
                    })
                    plural["reviewer_notes"] = "Corrección plural revisada en prueba"
                    for row in rows:
                        row["review_decision"] = "approved"
                    buffer = io.StringIO(newline="")
                    writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                    payload = ("\ufeff" + buffer.getvalue()).encode("utf-8")
                elif member.endswith(".csv"):
                    rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
                    for row in rows:
                        row["review_decision"] = "approved"
                    buffer = io.StringIO(newline="")
                    writer = csv.DictWriter(buffer, fieldnames=rows[0].keys())
                    writer.writeheader()
                    writer.writerows(rows)
                    payload = ("\ufeff" + buffer.getvalue()).encode("utf-8")
                output.writestr(member, payload)

        apply_review_bundle(reviewed, "fr", self.root)
        catalog = polib.pofile(str(self.root / "fr/LC_MESSAGES/djangojs.po"))
        entry = next(entry for entry in catalog if entry.msgid_plural)
        self.assertEqual(entry.msgstr_plural[0], "%(count)s cas corrigé")
        self.assertEqual(entry.msgstr_plural[1], "%(count)s cas corrigés")
        self.assertNotIn("fuzzy", entry.flags)


if __name__ == "__main__":
    unittest.main()
