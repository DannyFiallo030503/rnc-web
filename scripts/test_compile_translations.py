"""Tests ensuring draft locales cannot leak into compiled runtime catalogs."""

from pathlib import Path
import tempfile
import unittest

import polib

from scripts.compile_translations import approved_catalog, catalog_paths, compile_catalogs


class TranslationCompilerTests(unittest.TestCase):
    def test_only_explicit_active_domains_are_selected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active = root / "en/LC_MESSAGES/django.po"
            draft = root / "fr/LC_MESSAGES/django.po"
            active.parent.mkdir(parents=True)
            draft.parent.mkdir(parents=True)
            polib.POFile().save(str(active))
            polib.POFile().save(str(draft))

            selected = catalog_paths(root, {"en": ("django",)})

            self.assertEqual(selected, [active])
            self.assertNotIn(draft, selected)

    def test_fuzzy_entries_are_excluded_from_mo_output(self):
        catalog = polib.POFile()
        catalog.append(polib.POEntry(msgid="Approved", msgstr="Approuvé"))
        catalog.append(polib.POEntry(msgid="Draft", msgstr="Brouillon", flags=["fuzzy"]))
        compiled = polib.mofile(approved_catalog(catalog).to_binary())
        self.assertEqual(compiled.find("Approved").msgstr, "Approuvé")
        self.assertIsNone(compiled.find("Draft"))

    def test_invalid_active_catalogs_do_not_write_any_mo_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid_path = root / "en/LC_MESSAGES/django.po"
            invalid_path = root / "es/LC_MESSAGES/djangojs.po"
            valid_path.parent.mkdir(parents=True)
            invalid_path.parent.mkdir(parents=True)
            valid = polib.POFile()
            valid.append(polib.POEntry(msgid="Approved", msgstr="Aprobado"))
            valid.save(str(valid_path))
            invalid = polib.POFile()
            invalid.append(polib.POEntry(msgid="Missing", msgstr=""))
            invalid.save(str(invalid_path))

            compiled, errors = compile_catalogs(
                root, {"en": ("django",), "es": ("djangojs",)}
            )

            self.assertEqual(compiled, [])
            self.assertTrue(errors)
            self.assertFalse(valid_path.with_suffix(".mo").exists())
            self.assertFalse(invalid_path.with_suffix(".mo").exists())

    def test_all_valid_catalogs_compile_as_a_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root / "en/LC_MESSAGES/django.po", root / "es/LC_MESSAGES/djangojs.po"]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                catalog = polib.POFile()
                catalog.append(polib.POEntry(msgid="Approved", msgstr="Aprobado"))
                catalog.save(str(path))

            compiled, errors = compile_catalogs(
                root, {"en": ("django",), "es": ("djangojs",)}
            )

            self.assertEqual(errors, [])
            self.assertEqual(len(compiled), 2)
            self.assertTrue(all(output.is_file() for _source, output, _count in compiled))


if __name__ == "__main__":
    unittest.main()
