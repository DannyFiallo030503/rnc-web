"""Unit tests for placeholder and gettext-shape safeguards in draft generation."""

import unittest

import polib

from scripts.draft_machine_translations import apply_draft_overrides, plural_targets, protect, restore, translation_units


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

    def test_curated_override_updates_translation_but_keeps_it_fuzzy(self):
        catalog = polib.POFile()
        entry = polib.POEntry(msgid="Menú", msgstr="Tidak bisa", flags=["fuzzy"])
        catalog.append(entry)
        count = apply_draft_overrides(
            catalog, "id", "django", {"id": {"django": {"Menú": "Menu"}}}
        )
        self.assertEqual(count, 1)
        self.assertEqual(entry.msgstr, "Menu")
        self.assertIn("fuzzy", entry.flags)

    def test_curated_override_rejects_unknown_source_message(self):
        catalog = polib.POFile()
        with self.assertRaises(ValueError):
            apply_draft_overrides(
                catalog, "id", "django", {"id": {"django": {"Missing": "Menu"}}}
            )


if __name__ == "__main__":
    unittest.main()
