import tempfile
import unittest
from pathlib import Path

from scripts.build_translation_review_site import build, build_data


class TranslationReviewSiteTests(unittest.TestCase):
    def test_every_priority_language_has_both_domains_and_review_state(self):
        data = build_data()
        self.assertEqual(len(data["languages"]), 11)
        by_code = {language["code"]: language for language in data["languages"]}
        for code in ("zh-hans", "hi", "ar", "fr", "bn", "pt-br", "id", "ur", "ru"):
            language = by_code[code]
            self.assertTrue(language["draft"])
            self.assertEqual(set(language["domains"]), {"django", "djangojs"})
            self.assertEqual(len(language["domains"]["django"]), 727)
            self.assertEqual(len(language["domains"]["djangojs"]), 158)
            self.assertTrue(all(row["fuzzy"] for domain in language["domains"].values() for row in domain))

    def test_arabic_and_urdu_are_rtl_and_spanish_portal_is_source_text(self):
        by_code = {language["code"]: language for language in build_data()["languages"]}
        self.assertTrue(by_code["ar"]["rtl"])
        self.assertTrue(by_code["ur"]["rtl"])
        spanish_portal = by_code["es"]["domains"]["django"]
        self.assertTrue(spanish_portal)
        self.assertTrue(all(row["origin"] == "source" for row in spanish_portal))
        self.assertTrue(all(row["source"] == row["target"] for row in spanish_portal))

    def test_build_writes_static_assets_and_catalog_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "site"
            build(output)
            self.assertEqual(
                {path.name for path in output.iterdir()},
                {"index.html", "review.js", "style.css", "translations.json"},
            )
            payload = (output / "translations.json").read_text(encoding="utf-8")
            self.assertIn('"zh-hans"', payload)
            self.assertIn('"fuzzy":true', payload)


if __name__ == "__main__":
    unittest.main()
