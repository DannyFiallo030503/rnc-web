"""Unit tests for catalog completeness checks."""

from pathlib import Path
import tempfile
import unittest

import polib
from scripts.audit_unmarked_template_text import MARKED_BLOCK

from scripts.check_translations import (
    catalog_inventory_extras,
    catalog_plural_mismatches,
    complete_translation,
    brand_acronym_issues,
    literals,
    placeholder_names,
    plural_literals,
)


class TranslationCheckerTests(unittest.TestCase):
    def test_institutional_acronym_is_preserved_in_translations(self):
        self.assertEqual(brand_acronym_issues("Administración RNC", "RNC administration"), [])
        self.assertTrue(brand_acronym_issues("Administración RNC", "NCR administration"))
        self.assertTrue(brand_acronym_issues("Administración RNC", "Registry administration"))
        self.assertEqual(brand_acronym_issues("Administración", "Administration"), [])

    def test_plural_entry_requires_every_form(self):
        entry = polib.POEntry(
            msgid="%(count)s item",
            msgid_plural="%(count)s items",
            msgstr_plural={0: "%(count)s item", 1: ""},
        )
        self.assertFalse(complete_translation(entry))
        entry.msgstr_plural[1] = "%(count)s items"
        self.assertTrue(complete_translation(entry))

    def test_fuzzy_entry_does_not_count_as_translation(self):
        entry = polib.POEntry(msgid="Open", msgstr="Open", flags=["fuzzy"])
        self.assertFalse(complete_translation(entry))

    def test_interpolation_names_can_be_compared(self):
        self.assertEqual(
            placeholder_names("Page %(page)s of %(pages)s"),
            placeholder_names("Página %(page)s de %(pages)s"),
        )
        self.assertNotEqual(
            placeholder_names("%(page)s / %(pages)s"),
            placeholder_names("%(page)s"),
        )

    def test_python_translation_literals_include_concatenated_strings(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "mail.py"
            path.write_text(
                'from django.utils.translation import gettext as _\n'
                '_("Primer párrafo.\\n\\n" "Segundo párrafo %(link)s")\n',
                encoding="utf-8",
            )
            self.assertEqual(
                literals(path),
                {"Primer párrafo.\n\nSegundo párrafo %(link)s"},
            )

    def test_python_context_translation_uses_message_not_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "labels.py"
            path.write_text(
                'from django.utils.translation import pgettext\n'
                'pgettext("button label", "Open")\n',
                encoding="utf-8",
            )
            self.assertEqual(literals(path), {"Open"})

    def test_python_ngettext_extracts_source_plural_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "counts.py"
            path.write_text(
                'from django.utils.translation import ngettext\n'
                'ngettext("%(count)s item", "%(count)s items", count)\n',
                encoding="utf-8",
            )
            self.assertEqual(
                plural_literals(path),
                {("%(count)s item", "%(count)s items")},
            )

    def test_template_blocktrans_extracts_singular_with_interpolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "notice.html"
            path.write_text(
                "{% load i18n %}\n"
                "{% blocktrans count counter=counter %}"
                "You have {{ counter }} result"
                "{% plural %}You have {{ counter }} results"
                "{% endblocktrans %}",
                encoding="utf-8",
            )
            self.assertEqual(literals(path), {"You have %(counter)s result"})
            self.assertEqual(
                plural_literals(path),
                {("You have %(counter)s result", "You have %(counter)s results")},
            )

    def test_template_audit_excludes_both_blocktrans_spellings(self):
        for tag, end_tag in (("blocktrans", "endblocktrans"), ("blocktranslate", "endblocktranslate")):
            with self.subTest(tag=tag):
                source = f"Before {{% {tag} %}}Marked words{{% {end_tag} %}} after."
                self.assertEqual(MARKED_BLOCK.sub(" ", source), "Before   after.")

    def test_javascript_translation_markers_cover_format_plural_and_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "offline.js"
            path.write_text(
                'fmt("Uso %(used)s de %(quota)s", values);\n'
                'plural("categoría", "categorías", count);\n'
                'ngettext("%(count)s option", "%(count)s options", count);\n'
                'pgettext("button label", "Open");\n',
                encoding="utf-8",
            )
            self.assertEqual(
                literals(path),
                {
                    "Uso %(used)s de %(quota)s",
                    "categoría",
                    "%(count)s option",
                    "Open",
                },
            )
            self.assertEqual(
                plural_literals(path),
                {
                    ("categoría", "categorías"),
                    ("%(count)s option", "%(count)s options"),
                },
            )

    def test_catalog_inventory_reports_unreferenced_nonobsolete_messages(self):
        catalog = polib.POFile()
        catalog.append(polib.POEntry(msgid="Current", msgstr="Current"))
        catalog.append(polib.POEntry(msgid="Old", msgstr="Old"))
        obsolete = polib.POEntry(msgid="Legacy", msgstr="Legacy")
        obsolete.obsolete = True
        catalog.append(obsolete)

        self.assertEqual(catalog_inventory_extras({"Current"}, catalog), ["Old"])

    def test_plural_catalog_msgid_must_match_source(self):
        catalog = polib.POFile()
        catalog.append(polib.POEntry(
            msgid="%(count)s item",
            msgid_plural="%(count)s articles",
            msgstr_plural={0: "item", 1: "items"},
        ))
        self.assertEqual(
            catalog_plural_mismatches(
                {("%(count)s item", "%(count)s items")}, catalog
            ),
            [("%(count)s item", "%(count)s items", "%(count)s articles")],
        )


if __name__ == "__main__":
    unittest.main()
