"""Unit tests for placeholder and gettext-shape safeguards in draft generation."""

import unittest

import polib

from scripts.draft_machine_translations import plural_targets, protect, restore, translation_units


class MachineTranslationDraftTests(unittest.TestCase):
    def test_placeholders_urls_tags_and_line_breaks_round_trip(self):
        source = 'Page %(page)s of %(pages)s: <strong>open</strong> https://example.test/a\nContinue'
        protected, tokens = protect(source, "TEST")
        restored = restore(protected, tokens, "TEST")
        self.assertEqual(restored, source)

    def test_missing_placeholder_is_rejected(self):
        _, tokens = protect("Count %(count)s", "TEST")
        with self.assertRaises(ValueError):
            restore("Count", tokens, "TEST")

    def test_plural_translation_units_use_english_catalog_values(self):
        entry = polib.POEntry(
            msgid="categoría",
            msgid_plural="categorías",
            msgstr="category",
            msgstr_plural={0: "category", 1: "categories"},
        )
        self.assertEqual(translation_units(entry), ["category", "categories"])

    def test_plural_target_forms_follow_locale_form_count(self):
        entry = polib.POEntry(msgid="category", msgid_plural="categories")
        singular, one_form = plural_targets(entry, ["catégorie", "catégories"], 1)
        self.assertEqual((singular, one_form), ("catégorie", {0: "catégorie"}))
        _, six_forms = plural_targets(entry, ["فئة", "فئات"], 6)
        self.assertEqual(set(six_forms), set(range(6)))


if __name__ == "__main__":
    unittest.main()
