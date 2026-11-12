"""Unit tests for localized PDF text extraction in the PWA review."""

import unittest
from io import BytesIO

from PIL import Image

from scripts.review_pwa import pdf_contains_glyphs, png_has_rendered_pixels


class PdfGlyphCoverageTests(unittest.TestCase):
    def test_latin_label_requires_all_letters(self):
        self.assertTrue(pdf_contains_glyphs("Localized chart", "Localized chart"))
        self.assertFalse(pdf_contains_glyphs("Localized chart", "Localized char"))

    def test_rtl_word_order_does_not_hide_glyph_coverage(self):
        self.assertTrue(pdf_contains_glyphs("مجموعة مواقع السرطان", "السرطان مواقع مجموعة"))

    def test_shaped_indic_glyph_repetitions_do_not_hide_coverage(self):
        self.assertTrue(pdf_contains_glyphs("कैंसर स्थल समूह", "कैं कैं सर स्थल समूमूह"))
        self.assertTrue(
            pdf_contains_glyphs(
                "ক্যান্সারের স্থানভিত্তিক গোষ্ঠী",
                "ক্যাক্যাক্যান্সান্সারেরের স্থাস্থানভিভিত্তিত্তিক গোগোগোষ্ঠীষ্ঠী",
            )
        )

    def test_missing_combining_mark_is_detected(self):
        self.assertFalse(pdf_contains_glyphs("कैंसर", "कसर"))

    def test_nonuniform_png_decodes_as_rendered_content(self):
        image = Image.new("RGB", (8, 8), "white")
        image.putpixel((4, 4), (20, 80, 120))
        output = BytesIO()
        image.save(output, format="PNG")
        self.assertTrue(png_has_rendered_pixels(output.getvalue()))

    def test_uniform_png_is_rejected_as_empty_render(self):
        output = BytesIO()
        Image.new("RGB", (8, 8), "white").save(output, format="PNG")
        self.assertFalse(png_has_rendered_pixels(output.getvalue()))

    def test_corrupt_png_is_rejected(self):
        self.assertFalse(png_has_rendered_pixels(b"\x89PNG\r\n\x1a\ncorrupt"))


if __name__ == "__main__":
    unittest.main()
