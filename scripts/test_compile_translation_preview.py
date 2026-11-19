"""Tests for the opt-in, hash-pinned draft catalog preview bundle."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import polib

from scripts.compile_translation_preview import compile_translation_preview
from config.languages import ACTIVE_LANGUAGES, selectable_languages, translation_preview_enabled


ROOT = Path(__file__).resolve().parents[1]


class TranslationPreviewCompilerTests(unittest.TestCase):
    def test_preview_is_opt_in_and_does_not_change_production_selector(self):
        self.assertFalse(translation_preview_enabled({}))
        self.assertTrue(translation_preview_enabled({"RNC_TRANSLATION_PREVIEW": "yes"}))
        self.assertEqual(selectable_languages(False), ACTIVE_LANGUAGES)
        self.assertEqual(len(selectable_languages(True)), 11)

    def test_compiles_all_candidates_to_an_isolated_hash_pinned_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "locale-preview"
            manifest = compile_translation_preview(output)

            self.assertEqual(manifest["schema"], "rnc-translation-preview-v1")
            self.assertEqual(len(manifest["catalogs"]), 18)
            self.assertEqual(
                sum(record["fuzzy_entries_included"] for record in manifest["catalogs"].values()),
                sum(record["entries"] for record in manifest["catalogs"].values()),
            )
            self.assertTrue((output / "manifest.json").is_file())
            for record in manifest["catalogs"].values():
                self.assertTrue((output / record["mo"]).is_file())

    def test_preview_setting_requires_complete_current_manifest_and_enables_languages(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "locale-preview"
            compile_translation_preview(output)
            environment = os.environ.copy()
            environment.update({
                "DJANGO_SETTINGS_MODULE": "config.settings",
                "RNC_TRANSLATION_PREVIEW": "1",
                "RNC_TRANSLATION_PREVIEW_LOCALE_PATH": str(output),
            })
            check = subprocess.run(
                [sys.executable, "manage.py", "check"], cwd=ROOT,
                env=environment, text=True, capture_output=True, check=False,
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            inventory = subprocess.run(
                [sys.executable, "-c", (
                    "import django; django.setup(); "
                    "from django.conf import settings; "
                    "assert settings.TRANSLATION_PREVIEW_ENABLED; "
                    "assert len(settings.LANGUAGES) == 11; "
                    "assert len(settings.DRAFT_TRANSLATION_LOCALES) == 9"
                )], cwd=ROOT, env=environment, text=True,
                capture_output=True, check=False,
            )
            self.assertEqual(inventory.returncode, 0, inventory.stderr)

            missing_environment = environment.copy()
            missing_environment["RNC_TRANSLATION_PREVIEW_LOCALE_PATH"] = str(
                Path(temporary) / "missing-preview"
            )
            missing = subprocess.run(
                [sys.executable, "manage.py", "check"], cwd=ROOT,
                env=missing_environment, text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("falta manifiesto legible", missing.stderr)

            manifest_path = output / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["catalogs"]["fr/django"]["mo"] = "ar/LC_MESSAGES/django.mo"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            stale = subprocess.run(
                [sys.executable, "manage.py", "check"], cwd=ROOT,
                env=environment, text=True, capture_output=True, check=False,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("ruta .mo inesperada", stale.stderr)

    def test_preview_compiler_refuses_production_catalog_directory(self):
        with self.assertRaises(ValueError):
            compile_translation_preview(ROOT / "locale")

    def test_preview_compiler_rejects_placeholder_mismatch_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            locale_root = root / "locale/fr/LC_MESSAGES"
            locale_root.mkdir(parents=True)
            for domain, value in (("django", "Nombre traduit"), ("djangojs", "Texte")):
                catalog = polib.POFile()
                catalog.metadata = {
                    "Language": "fr",
                    "Plural-Forms": "nplurals=2; plural=(n > 1);",
                }
                catalog.append(polib.POEntry(
                    msgid="Count %(count)s", msgstr=value, flags=["fuzzy"],
                ))
                catalog.save(str(locale_root / f"{domain}.po"))
            with patch("scripts.compile_translation_preview.ROOT", root):
                with patch("config.languages.PRIORITY_LANGUAGES", (
                    ("fr", "French", "Français", False),
                )):
                    with self.assertRaisesRegex(ValueError, "placeholders incompatibles"):
                        compile_translation_preview(root / "preview")
            self.assertFalse((root / "preview").exists())


if __name__ == "__main__":
    unittest.main()
