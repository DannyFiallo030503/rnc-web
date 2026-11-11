"""Unit tests for draft catalog invariants."""

import unittest

from scripts.audit_translation_drafts import (
    looks_like_untranslated_english,
    looks_like_untranslated_spanish,
    placeholders,
    semantic_translation_issues,
)


class DraftAuditTests(unittest.TestCase):
    def test_exact_spanish_copy_is_flagged_but_shared_names_and_cognates_are_allowed(self):
        self.assertTrue(looks_like_untranslated_spanish("Población denominadora", "Población denominadora"))
        self.assertTrue(looks_like_untranslated_spanish("Tasa por edad", "Tasa por edad"))
        self.assertFalse(looks_like_untranslated_spanish("Próstata", "Próstata"))
        self.assertFalse(looks_like_untranslated_spanish("NCI/SEER", "NCI/SEER"))
        self.assertFalse(looks_like_untranslated_spanish("Población denominadora", "Population de référence"))

    def test_non_latin_drafts_cannot_fall_back_to_english_copy(self):
        self.assertTrue(looks_like_untranslated_english("zh-hans", "Chart title", "Chart title"))
        self.assertTrue(looks_like_untranslated_english("ru", "Pie chart", "Pie chart"))
        self.assertFalse(looks_like_untranslated_english("zh-hans", "Excel", "Excel"))
        self.assertFalse(looks_like_untranslated_english("ru", "NCI/SEER · SEER*Explorer", "NCI/SEER · SEER*Explorer"))
        self.assertFalse(looks_like_untranslated_english("zh-hans", "Chart title", "图表标题"))

    def test_known_chart_and_rate_false_friends_are_flagged(self):
        self.assertTrue(semantic_translation_issues("zh-hans", "Barras agrupadas por sexo", "按性别分组的酒吧"))
        self.assertTrue(semantic_translation_issues("zh-hans", "Circular", "馅饼"))
        self.assertTrue(semantic_translation_issues("ru", "Tasa ajustada", "Ставка с поправкой"))
        self.assertTrue(semantic_translation_issues("ru", "Barras horizontales", "Турники"))
        self.assertEqual(semantic_translation_issues("ru", "Tasa ajustada", "Стандартизованный показатель"), [])
        self.assertTrue(semantic_translation_issues("fr", "Circular", "Tarte"))
        self.assertTrue(semantic_translation_issues("fr", "Barras agrupadas por sexo", "Barres agrupadas par sexe"))
        self.assertTrue(semantic_translation_issues("fr", "Barras porcentuales por sexo", "Barres porcentuelles pour le sexe"))
        self.assertTrue(semantic_translation_issues("pt-br", "Circular", "Torta"))
        self.assertTrue(semantic_translation_issues("pt-br", "Barras agrupadas por sexo", "Bares agrupados por sexo"))
        self.assertTrue(semantic_translation_issues("pt-br", "Cada barra suma 100 %", "Cada barra totaliza 100% and mostra a distribuição"))
        self.assertTrue(semantic_translation_issues("id", "Circular", "pai"))
        self.assertTrue(semantic_translation_issues("id", "Barras agrupadas por sexo", "Mengelompokkan bar berdasarkan jenis kelamin"))
        self.assertTrue(semantic_translation_issues("id", "Tasa ajustada", "Tarif yang disesuaikan"))
        self.assertTrue(semantic_translation_issues("id", "Tasa ajustada Segi–Doll", "Tarif Segi–Boneka"))
        self.assertTrue(semantic_translation_issues("id", "Cada barra suma 100 %", "Setiap batang berjumlah 100% a dan menunjukkan distribusi"))
        self.assertEqual(semantic_translation_issues("fr", "Circular", "Diagramme circulaire"), [])
        self.assertEqual(semantic_translation_issues("pt-br", "Circular", "Gráfico circular"), [])
        self.assertEqual(semantic_translation_issues("id", "Circular", "Diagram lingkaran"), [])

    def test_russian_draft_flags_leftover_english_function_words(self):
        self.assertTrue(semantic_translation_issues("ru", "Cada barra suma 100 %", "Столбец равен 100% and показывает распределение"))
        self.assertTrue(semantic_translation_issues("ru", "Texto institucional", "Утверждение для the RNC"))
        self.assertEqual(semantic_translation_issues("ru", "Cada barra suma 100 %", "Столбец равен 100% и показывает распределение"), [])
        self.assertTrue(semantic_translation_issues("ru", "El RNC publica estadísticas", "СРН публикует статистику"))
        self.assertTrue(semantic_translation_issues("ru", "El RNC publica estadísticas", "NCR публикует статистику"))
        self.assertEqual(semantic_translation_issues("ru", "El RNC publica estadísticas", "RNC публикует статистику"), [])

    def test_french_and_portuguese_numeric_constraints_and_package_terms(self):
        self.assertTrue(semantic_translation_issues("fr", "El gráfico circular necesita hasta ocho categorías.", "Le graphique circulaire nécessite une ou plusieurs catégories."))
        self.assertTrue(semantic_translation_issues("fr", "Este gráfico necesita al menos dos categorías con datos.", "Ce graphique nécessite moins de deux catégories de données."))
        self.assertTrue(semantic_translation_issues("fr", "Enter at least %(length)s characters.", "Saisissez au moins les caractères %(length)s."))
        self.assertTrue(semantic_translation_issues("fr", "Text was not added: enter no more than %(length)s characters.", "ne saisissez pas plus de caractères %(length)s"))
        self.assertTrue(semantic_translation_issues("fr", "Puedes combinar varios valores", "sélectionnez une valeur maximale dans chaque filtre"))
        self.assertTrue(semantic_translation_issues("pt-br", "Enter no more than %(length)s characters.", "Insira no máximo caracteres %(length)s."))
        self.assertTrue(semantic_translation_issues("pt-br", "Este prototipo solo admite el paquete sintético autorizado para pruebas.", "Este protótipo aceita apenas a embalagem sintética autorizada para teste."))
        self.assertEqual(semantic_translation_issues("fr", "El gráfico circular necesita hasta ocho categorías.", "Les graphiques circulaires acceptent jusqu’à huit catégories."), [])
        self.assertEqual(semantic_translation_issues("fr", "Este gráfico necesita al menos dos categorías con datos.", "Ce graphique doit présenter au moins deux catégories de données."), [])
        self.assertEqual(semantic_translation_issues("fr", "Text was not added: enter no more than %(length)s characters.", "saisissez au maximum %(length)s caractères"), [])
        self.assertEqual(semantic_translation_issues("pt-br", "Este prototipo solo admite el paquete sintético autorizado para pruebas.", "Este protótipo aceita apenas o pacote sintético autorizado para testes."), [])

    def test_deduplication_and_municipality_breakdown_meanings(self):
        source = "El corte agregado no permite deduplicar personas distintas al combinar varios valores."
        self.assertTrue(semantic_translation_issues("hi", source, "लोगों को डुप्लिकेट नहीं कर सकती"))
        self.assertTrue(semantic_translation_issues("bn", source, "লোকেদের অনুলিপি করতে পারে না"))
        self.assertTrue(semantic_translation_issues("ur", source, "لوگوں کی نقل نہیں کر سکتی"))
        municipality = "El corte activo no incluye desglose por municipio; solo contiene provincia de residencia."
        self.assertTrue(semantic_translation_issues("hi", municipality, "नगर पालिका टूटना नहीं है"))
        self.assertTrue(semantic_translation_issues("bn", municipality, "পৌরসভা ভাঙ্গন নেই"))
        self.assertTrue(semantic_translation_issues("ur", municipality, "میونسپلٹی کی کوئی خرابی نہیں"))
        self.assertEqual(semantic_translation_issues("bn", source, "একাধিক নির্বাচিত মান জুড়ে একই ব্যক্তিকে একাধিকবার গণনা এড়ানো যায় না"), [])

    def test_arabic_minimum_placeholder_and_russian_package_terms(self):
        self.assertTrue(semantic_translation_issues("ar", "Enter at least %(length)s characters.", "أدخل حرف %(length)s على الأقل."))
        self.assertTrue(semantic_translation_issues("ru", "Este prototipo solo admite el paquete sintético autorizado para pruebas.", "Этот прототип принимает только синтетическую упаковку, разрешенную для испытаний."))
        self.assertEqual(semantic_translation_issues("ar", "Enter at least %(length)s characters.", "أدخل ما لا يقل عن %(length)s أحرف."), [])
        self.assertEqual(semantic_translation_issues("ru", "Este prototipo solo admite el paquete sintético autorizado para pruebas.", "Этот прототип принимает только пакет синтетических данных, разрешённый для тестирования."), [])

    def test_statistical_labels_use_locale_specific_meanings(self):
        for locale, source, old in (
            ("zh-hans", "Personas distintas", "独特的人"),
            ("zh-hans", "Grupo de localización", "站点组"),
            ("zh-hans", "Anillo", "甜甜圈"),
            ("hi", "Sexo", "सेक्स"),
            ("hi", "Frecuencia absoluta", "पूर्ण आवृत्ति"),
            ("hi", "Población denominadora", "भाजक जनसंख्या"),
            ("ar", "Personas distintas", "أشخاص مميزون"),
            ("ar", "Población denominadora", "السكان القاسم"),
            ("fr", "Personas distintas", "Personas distinctes"),
            ("fr", "Anillo", "Beignet"),
            ("fr", "Tasa cruda / específica por 100 000", "Tasa cruda / spécifique pour 100 000"),
            ("bn", "Sexo", "সেক্স"),
            ("pt-br", "Grupo de localización", "Grupo de sites de câncer"),
            ("id", "Personas distintas", "Orang yang berbeda"),
            ("id", "Grupo de localización", "Grup situs"),
            ("ur", "Sexo", "سیکس"),
            ("ru", "Sexo", "Секс"),
            ("ru", "Anillo", "Пончик"),
        ):
            with self.subTest(locale=locale, source=source):
                self.assertTrue(semantic_translation_issues(locale, source, old))

        for locale, source, corrected in (
            ("zh-hans", "Personas distintas", "去重人数"),
            ("zh-hans", "Anillo", "环形图"),
            ("hi", "Sexo", "लिंग"),
            ("ar", "Personas distintas", "أشخاص فريدون"),
            ("fr", "Personas distintas", "Personnes distinctes"),
            ("fr", "Anillo", "Graphique en anneau"),
            ("fr", "Tasa cruda / específica por 100 000", "Taux brut / spécifique selon l’âge pour 100 000"),
            ("bn", "Sexo", "লিঙ্গ"),
            ("pt-br", "Circular", "Gráfico de pizza"),
            ("id", "Sexo", "Jenis kelamin"),
            ("ur", "Sexo", "جنس"),
            ("ru", "Sexo", "Пол"),
        ):
            with self.subTest(locale=locale, source=source, corrected=corrected):
                self.assertEqual(semantic_translation_issues(locale, source, corrected), [])
        self.assertEqual(semantic_translation_issues("pt-br", "Circular", "Gráfico circular"), [])

    def test_plural_forms_are_audited_for_false_friends(self):
        source = "categoría con el mismo valor"
        for locale, old in (
            ("zh-hans", "勇气类别"),
            ("hi", "वीरता की श्रेणी"),
            ("ar", "الفئة بنفس الشجاعة"),
            ("bn", "ক্যাটাগরি কন এল মিসমো বীরত্ব"),
            ("id", "kategori dengan keberanian yang sama"),
            ("ur", "categoría con el mismo valor"),
            ("ru", "категория с доблестью"),
        ):
            with self.subTest(locale=locale):
                self.assertTrue(semantic_translation_issues(locale, source, old))
        for locale, corrected in (
            ("zh-hans", "数值相同的类别"),
            ("hi", "समान मान वाली श्रेणी"),
            ("ar", "فئة لها القيمة نفسها"),
            ("bn", "একই মানের বিভাগ"),
            ("id", "Kategori dengan nilai yang sama"),
            ("ur", "ایک ہی قدر والا زمرہ"),
            ("ru", "категория с тем же значением"),
        ):
            with self.subTest(locale=locale, corrected=corrected):
                self.assertEqual(semantic_translation_issues(locale, source, corrected), [])

    def test_institutional_rnc_acronym_is_preserved_in_latin_script_drafts(self):
        for locale, target in (("fr", "RCN Cuba"), ("fr", "NCR Cuba"), ("pt-br", "Cuba pelo NCR"), ("id", "Statistik NCR")):
            with self.subTest(locale=locale, target=target):
                self.assertTrue(semantic_translation_issues(locale, "RNC · Estadísticas de Cuba", target))
        self.assertEqual(semantic_translation_issues("pt-br", "RNC · Estadísticas de Cuba", "RNC · Estatísticas de Cuba"), [])

    def test_placeholder_signature_ignores_translation_order_but_keeps_names(self):
        self.assertEqual(placeholders("Page %(page)s of %(pages)s"), ["page", "pages"])
        self.assertNotEqual(placeholders("Page %(page)s"), placeholders("Page %(pages)s"))


if __name__ == "__main__":
    unittest.main()
