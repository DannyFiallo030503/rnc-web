"""Backend regression: isolated DB/files, fictitious identities and no SMTP."""

import io
import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings, tag
from django.utils.translation import override as override_language
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from .models import Delivery, Publication, AuditEvent, AccountPolicy, AccountMail
from .services import ingest, transition, delivery_records
from .testing import uploaded, synthetic_rows, csv_bytes

PASSWORD = "Review-test<> 'Secure-2026!"


@override_settings(
    DEBUG=True,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class PortalTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="rnc-backend-")
        self.addCleanup(self.temporary.cleanup)
        self.override = override_settings(
            PRIVATE_STORAGE_ROOT=Path(self.temporary.name),
            EMAIL_FILE_PATH=Path(self.temporary.name) / "mail",
            PUBLIC_ORIGIN="https://rnc.example.invalid",
            PUBLIC_RELEASE_ROOT=Path(self.temporary.name) / "public-releases",
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        cache.clear()
        delivery_records.cache_clear()
        self.User = get_user_model()
        self.root = self.User.objects.create_superuser(
            "qa_root",
            email="root@example.invalid",
            password=PASSWORD,
            first_name="Elena",
            last_name="García",
        )
        self.reader = self.User.objects.create_user(
            "qa_reader", email="reader@example.invalid", password=PASSWORD
        )
        self.operator = self.User.objects.create_user("qa_operator", password=PASSWORD)
        self.operator.groups.add(Group.objects.get(name="operator"))
        self.publisher = self.User.objects.create_user(
            "qa_publisher", password=PASSWORD
        )
        self.publisher.groups.add(Group.objects.get(name="publisher"))

    def account_data(self, **updates):
        data = {
            "username": "cuenta_nueva",
            "first_name": "María José",
            "last_name": "O’Neill-Pérez",
            "email": "nueva@example.invalid",
            "role": "operator",
            "is_active": "on",
            "initial_password": "",
            "confirm_password": PASSWORD,
        }
        data.update(updates)
        return data

    def delivery(self, extra=1, publish=False):
        d = ingest(uploaded(extra), "Corte sintético 2023–2024", self.root)
        if publish:
            self.apply_transition(
                d.pk,
                "publish",
                self.root,
                "Publicación sintética autorizada para la prueba.",
            )
        return d

    def apply_transition(self, *args, **kwargs):
        with self.captureOnCommitCallbacks(execute=True):
            return transition(*args, **kwargs)

    def post_account(self, **updates):
        self.client.force_login(self.root)
        return self.client.post(
            "/administracion/usuarios/nuevo/", self.account_data(**updates)
        )

    def test_public_pages_and_no_redundant_home_button(self):
        for path in ["/", "/el-rnc/", "/consulta/", "/acceso/", "/cuenta/recuperar/"]:
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, "sidebar-home")
                self.assertNotContains(r, 'href="/administracion/cortes/"')
                if path in {"/", "/el-rnc/", "/consulta/"}:
                    self.assertContains(r, 'aria-label="Páginas"')

    def test_language_switch_is_persistent_and_preserves_the_current_page(self):
        self.delivery(publish=True)
        spanish = self.client.get("/consulta/")
        self.assertEqual(spanish.status_code, 200)
        self.assertContains(spanish, '<html lang="es" dir="ltr"', html=False)
        response = self.client.post(
            "/i18n/setlang/",
            {"language": "en", "next": "/consulta/"},
        )
        self.assertRedirects(response, "/consulta/", fetch_redirect_response=False)
        self.assertEqual(response.cookies["rnc_language"].value, "en")

        english = self.client.get("/consulta/")
        self.assertEqual(english.status_code, 200)
        self.assertContains(english, '<html lang="en" dir="ltr"', html=False)
        self.assertContains(english, "Statistical explorer")
        self.assertContains(english, 'name="language"')
        self.assertContains(english, '<option value="en" selected>', html=False)
        self.assertContains(english, "Year of diagnosis")
        self.assertContains(english, "Chart type")
        self.assertContains(english, "Horizontal bars")
        self.assertContains(english, "Visualization")
        self.assertContains(english, "Update results")
        self.assertContains(english, "Denominator population")

        home = self.client.get("/")
        self.assertContains(home, "Information to understand cancer incidence")
        self.assertContains(home, "Explore statistics")
        self.assertNotContains(home, "Información para comprender la incidencia del cáncer")

        about = self.client.get("/el-rnc/")
        self.assertContains(about, "The National Cancer Registry")
        self.assertContains(
            about,
            "<title>The RNC · National Cancer Registry of Cuba</title>",
            html=False,
        )
        self.assertContains(about, "What we do")
        self.assertContains(about, 'aria-label="Sections about the NCR"', html=False)
        self.assertContains(about, "The documented coverage includes all 15 provinces")
        self.client.cookies["rnc_language"] = "es"
        spanish_about = self.client.get("/el-rnc/")
        self.assertContains(
            spanish_about,
            "<title>El RNC · Registro Nacional de Cáncer de Cuba</title>",
            html=False,
        )
        self.client.cookies["rnc_language"] = "en"

        nomenclators = self.client.get("/nomencladores/")
        self.assertEqual(nomenclators.status_code, 200)
        self.assertContains(nomenclators, '<html lang="en" dir="ltr"', html=False)
        self.assertContains(nomenclators, "Cancer code catalogues")
        self.assertContains(nomenclators, "No authorized catalogue is available yet")

        localized_query = self.client.get(
            "/consulta/", {"dimension": "site", "site": "Mama"}
        )
        self.assertEqual(localized_query.status_code, 200)
        self.assertIn(
            ("Mama", "Breast"),
            localized_query.context["form"].fields["site"].choices,
        )
        self.assertContains(localized_query, "<th scope=\"row\">Breast</th>", html=False)
        self.assertContains(localized_query, "720,000")
        self.assertIn(
            "Illustrative synthetic group",
            localized_query.context["chart_payload"]["label_descriptions"]["Breast"],
        )
        localized_csv = self.client.get(
            "/consulta/", {"dimension": "site", "site": "Mama", "format": "csv"}
        )
        self.assertContains(localized_csv, "Breast")
        self.assertNotContains(localized_csv, "Mama")

        self.client.cookies["rnc_language"] = "es"
        spanish_query = self.client.get(
            "/consulta/", {"dimension": "site", "site": "Mama"}
        )
        from django.utils.formats import number_format

        expected_population = number_format(
            spanish_query.context["table"][0]["population"],
            decimal_pos=0,
            use_l10n=True,
            force_grouping=True,
        )
        self.assertContains(spanish_query, f"<td>{expected_population}</td>", html=False)
        self.client.cookies["rnc_language"] = "en"

        csv_export = self.client.get("/consulta/?format=csv")
        self.assertEqual(csv_export.status_code, 200)
        self.assertContains(csv_export, "Query context")
        self.assertContains(csv_export, "Chart metric")

        from config.settings_public import TEMPLATES as public_templates

        with override_settings(
            ROOT_URLCONF="config.urls_public",
            DEPLOYMENT_ROLE="public",
            TEMPLATES=public_templates,
        ):
            offline = self.client.get("/consulta-offline/")
        self.assertEqual(offline.status_code, 200)
        self.assertContains(offline, "Offline consultation")
        self.assertContains(offline, "Calculate on this device")

    def test_english_server_exports_translate_embedded_text(self):
        from openpyxl import load_workbook

        self.delivery(publish=True)
        self.client.cookies["rnc_language"] = "en"

        csv_response = self.client.get("/consulta/", {"format": "csv"})
        csv_text = csv_response.content.decode("utf-8-sig")
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("Query context", csv_text)
        self.assertIn("Tumors (absolute frequency)", csv_text)
        self.assertNotIn("Contexto de la consulta", csv_text)

        xlsx_response = self.client.get("/consulta/", {"format": "xlsx"})
        workbook = load_workbook(io.BytesIO(xlsx_response.content), read_only=True)
        self.assertEqual(workbook.active.title, "Query")
        cells = [cell for row in workbook.active.iter_rows(values_only=True) for cell in row]
        self.assertIn("Query context", cells)
        self.assertIn("Tumors (absolute frequency)", cells)
        workbook.close()

        svg_response = self.client.get("/consulta/", {"format": "svg"})
        svg_text = svg_response.content.decode("utf-8")
        self.assertEqual(svg_response.status_code, 200)
        self.assertIn("Breast", svg_text)
        self.assertNotIn("Mama", svg_text)

        for fmt, signature in (("png", bytes.fromhex("89504e47")), ("pdf", b"%PDF")):
            with self.subTest(format=fmt):
                response = self.client.get("/consulta/", {"format": fmt})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content.startswith(signature))

        self.client.cookies["rnc_language"] = "es"
        csv_response = self.client.get("/consulta/", {"format": "csv"})
        csv_text = csv_response.content.decode("utf-8-sig")
        self.assertIn("Contexto de la consulta", csv_text)
        self.assertIn("Tumores (frecuencia absoluta)", csv_text)

        xlsx_response = self.client.get("/consulta/", {"format": "xlsx"})
        workbook = load_workbook(io.BytesIO(xlsx_response.content), read_only=True)
        self.assertEqual(workbook.active.title, "Consulta")
        cells = [cell for row in workbook.active.iter_rows(values_only=True) for cell in row]
        self.assertIn("Contexto de la consulta", cells)
        self.assertIn("Tumores (frecuencia absoluta)", cells)
        workbook.close()

        svg_response = self.client.get("/consulta/", {"format": "svg"})
        self.assertIn("Mama", svg_response.content.decode("utf-8"))

    def test_export_font_fallback_covers_prioritized_writing_systems(self):
        import io
        import warnings
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.figure import Figure
        from public_site.exports import _apply_export_font_fallback

        samples = (
            "乳腺癌与结直肠癌",
            "स्तन कैंसर और आँत का कैंसर",
            "স্তন ক্যান্সার ও অন্ত্রের ক্যান্সার",
            "سرطان الثدي وسرطان القولون",
            "چھاتی اور بڑی آنت کا کینسر",
            "Рак молочной железы и толстой кишки",
        )
        figure = Figure(figsize=(8, 4))
        FigureCanvasAgg(figure)
        for index, sample in enumerate(samples):
            figure.text(0.05, 0.95 - index * 0.14, sample)
        table_axes = figure.add_axes([0.52, 0.05, 0.45, 0.9])
        table_axes.axis("off")
        table_axes.table(cellText=[[sample] for sample in samples])
        _apply_export_font_fallback(figure)
        with warnings.catch_warnings(record=True) as emitted:
            warnings.simplefilter("always")
            figure.canvas.draw()
            figure.savefig(io.BytesIO(), format="svg")
            figure.savefig(io.BytesIO(), format="png")
            with PdfPages(io.BytesIO()) as pdf:
                pdf.savefig(figure)

        missing_glyphs = [
            str(warning.message)
            for warning in emitted
            if "Glyph" in str(warning.message)
            and "missing from font" in str(warning.message)
        ]
        self.assertEqual(missing_glyphs, [])

    def test_english_covers_administration_accounts_and_authentication(self):
        delivery = self.delivery(publish=True)
        self.client.force_login(self.root)
        self.client.cookies["rnc_language"] = "en"

        cases = [
            ("/administracion/cortes/", ("Information management", "Administration", "Upload and validate CSV")),
            ("/administracion/usuarios/", ("Users and permissions", "Last email", "Responsibilities")),
            ("/administracion/usuarios/nuevo/", ("Create account", "Temporary password", "Your support password")),
            (f"/administracion/cortes/{delivery.pk}/", ("Technical report", "Release history", "Withdraw publication")),
        ]
        for path, expected in cases:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, '<html lang="en" dir="ltr"', html=False)
                for text in expected:
                    self.assertContains(response, text)

        self.client.logout()
        self.client.cookies["rnc_language"] = "en"
        login = self.client.get("/acceso/")
        self.assertContains(login, "Welcome back")
        self.assertContains(login, "Forgot your password?")
        recovery = self.client.get("/cuenta/recuperar/")
        self.assertContains(recovery, "Recover account")

    def test_javascript_translation_catalog_follows_selected_language(self):
        spanish = self.client.get("/jsi18n/")
        self.assertEqual(spanish.status_code, 200)
        self.assertContains(spanish, "Complete este campo.")

        self.client.cookies["rnc_language"] = "en"
        english = self.client.get("/jsi18n/")
        self.assertEqual(english.status_code, 200)
        self.assertContains(english, "Check this box to continue.")
        self.assertContains(english, "The local calculation encountered an error.")
        self.assertContains(english, "categories with the same values")
        self.assertContains(english, "Age-adjusted rate per 100,000")

    @override_settings(ROOT_URLCONF="config.urls_public", DEPLOYMENT_ROLE="public")
    def test_public_worker_uses_public_origin_scope_and_excludes_private_routes(self):
        response = self.client.get("/service-worker.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertEqual(response["Cache-Control"], "no-store")
        source = response.content.decode()
        for private_prefix in ('"/admin/"', '"/acceso/"', '"/administracion/"', '"/cuenta/"'):
            self.assertIn(private_prefix, source)
        self.assertIn("/paquete-offline.json", source)
        self.assertIn('"/consulta/"', source)
        from django.urls import resolve
        from .public_portal import not_found

        self.assertIs(resolve("/admin/", urlconf="config.urls_public").func, not_found)

    @override_settings(ROOT_URLCONF="config.urls_public", DEPLOYMENT_ROLE="public")
    def test_offline_package_contains_synthetic_aggregate_and_shared_query_contract(self):
        self.delivery(publish=True)
        response = self.client.get("/paquete-offline.json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        payload = json.loads(response.content)
        self.assertIs(payload["synthetic"], True)
        self.assertEqual(set(payload["query_contract"]["charts"]), {
            "bar", "ranking", "scatter", "strip", "swarm", "column", "line",
            "grouped", "stacked", "percent", "pie", "doughnut",
        })
        self.assertEqual(set(payload["query_contract"]["metrics"]), {"count", "share", "rate", "asr"})
        self.assertNotIn("person_id", response.content.decode())
        self.assertNotIn("tumor_id", response.content.decode())

    def test_install_manifest_starts_at_public_site_root_and_combined_site_does_not_register_worker(self):
        from django.conf import settings

        manifest = json.loads((Path(settings.BASE_DIR) / "static/pwa/manifest.webmanifest").read_text())
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        response = self.client.get("/")
        self.assertNotContains(response, "register-service-worker.js")

    def test_institutional_page_and_home_explain_the_registry_and_portal(self):
        self.delivery(publish=True)
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "¿Qué es el RNC?")
        self.assertContains(home, "¿Qué puedes hacer aquí?")
        self.assertContains(home, "Consultar estadísticas")
        self.assertContains(home, "De la pregunta al resultado")
        self.assertContains(home, "Distingue el número de casos")
        self.assertNotContains(home, "Tumores sintéticos")
        self.assertNotContains(home, 'id="result-chart"')

        about = self.client.get("/el-rnc/")
        self.assertEqual(about.status_code, 200)
        for section in (
            "Qué hacemos",
            "Dónde trabajamos",
            "Cómo trabajamos",
            "Oficina central",
            "Registros provinciales",
            "Contactos",
        ):
            with self.subTest(section=section):
                self.assertContains(about, section)
        self.assertContains(about, "supervivencia poblacional")
        self.assertContains(about, "comisiones provinciales")
        for method in (
            "Métodos y cálculos estadísticos",
            "Frecuencia relativa",
            "Tasa cruda de incidencia",
            "Tasa específica por edad",
            "Tasa ajustada directamente por edad",
            "Tasa indirecta e intervalos de confianza",
            "Fuentes, versiones y límites de comparación",
        ):
            with self.subTest(method=method):
                self.assertContains(about, method)
        self.assertContains(about, "casos nuevos / población correspondiente")
        self.assertContains(about, "Segi–Doll de 18 grupos quinquenales")
        self.assertContains(about, "no acredita cifras oficiales")
        self.assertContains(about, "Cancer Today")
        self.assertContains(about, "European Cancer Information System (ECIS)")
        self.assertContains(about, "definición y cálculo de tasas ajustadas por edad")

    def test_explorer_hides_redundant_summary_and_demo_banner(self):
        self.delivery(publish=True)
        response = self.client.get("/consulta/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Datos sintéticos de demostración; no son cifras oficiales.")
        self.assertNotContains(response, "Explorador de incidencia")
        self.assertNotContains(response, "Selecciona los filtros y el tipo de visualización")
        self.assertNotContains(response, "Tumores seleccionados")
        self.assertNotContains(response, 'class="badge">Datos sintéticos')
        self.assertContains(response, "Provincia de residencia")
        self.assertContains(response, "Municipio de residencia")
        self.assertContains(response, "El corte activo no incluye desglose por municipio")
        self.assertTrue(response.context["form"].fields["municipality"].disabled)

    def test_municipality_filter_uses_release_code_and_label(self):
        from unittest.mock import patch

        fields = ["period", "territory", "municipality", "sex", "age_group", "site"]
        values = {
            "period": "2024",
            "territory": "Pinar del Río",
            "municipality": "MUNI-DEMO-01",
            "sex": "Mujeres",
            "age_group": "45-49",
            "site": "Mama",
        }
        cube = {}
        for mask in range(1 << len(fields)):
            subset = [field for index, field in enumerate(fields) if mask & (1 << index)]
            cube[",".join(subset)] = [
                {
                    **{field: values[field] for field in subset},
                    "tumors": 2,
                    "persons": 1,
                    "population": 100,
                }
            ]
        release = {
            "synthetic": True,
            "title": "Corte sintético de prueba",
            "release_id": "a7a7a7a7-a7a7-47a7-a7a7-a7a7a7a7a7a7",
            "published_at": None,
            "fields": fields,
            "options": {
                "period": ["2024"],
                "territory": ["Pinar del Río"],
                "municipality": [["MUNI-DEMO-01", "Municipio ficticio"]],
                "sex": ["Mujeres"],
                "age_group": ["45-49"],
                "site": ["Mama"],
            },
            "cube": cube,
        }
        with patch("public_site.public_portal.current_public_release", return_value=release):
            response = self.client.get("/consulta/?municipality=MUNI-DEMO-01")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["tumors"], 2)
        self.assertContains(response, "Municipio ficticio")
        self.assertIn(
            "Municipio de residencia: Municipio ficticio",
            response.context["chart_payload"]["filter_summary"],
        )

    def test_query_sidebar_help_and_required_markers(self):
        self.delivery(publish=True)
        response = self.client.get("/consulta/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Filtros de la consulta"')
        self.assertContains(response, 'role="tooltip"')
        self.assertContains(response, "provincia y municipio de residencia")
        self.assertContains(response, "Grupo de localización")
        self.assertContains(response, "Año de incidencia")
        form_html = re.search(
            r'<form[^>]*id="query-form".*?</form>',
            response.content.decode(),
            re.DOTALL,
        ).group()
        self.assertNotIn("Opcional", form_html)
        self.assertNotIn("Grupo de localización ilustrativo", form_html)
        self.assertNotContains(response, "Grupo de localización ilustrativo")
        self.assertNotIn(">Todos</option>", form_html)
        self.assertEqual(
            form_html.count('<span class="required-mark" aria-hidden="true"> *</span>'),
            4,
        )
        self.assertContains(response, 'data-chart-required-indicator data-required-filter="site"')
        self.assertContains(response, 'data-required-filter="year" aria-hidden="true" hidden')
        self.assertNotContains(response, "Datos necesarios para este gráfico")

    def test_coding_nomenclators_explains_missing_authorized_catalog(self):
        response = self.client.get("/nomencladores/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Catálogo oficial aún no disponible")
        self.assertContains(response, "OMS · ICD‑O‑3")
        self.assertContains(response, "IARC · ICCC‑3")
        self.assertContains(response, "ICD‑O‑4")

        self.client.cookies["rnc_language"] = "en"
        english = self.client.get("/nomencladores/")
        self.assertEqual(english.status_code, 200)
        self.assertContains(english, "Cancer code catalogues")
        self.assertContains(english, "No authorized catalogue is available yet")
        self.assertContains(english, "WHO · ICD‑O‑3")

    def test_coding_nomenclators_fails_closed_on_invalid_file(self):
        path = Path(self.temporary.name) / "invalid-catalog.json"
        path.write_text("{not-json", encoding="utf-8")
        with override_settings(RNC_CODING_CATALOG=path):
            response = self.client.get("/nomencladores/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No se pudo cargar el catálogo")
        self.assertContains(response, 'role="alert"')

    def test_coding_nomenclators_searches_versioned_file_and_shows_provenance(self):
        path = Path(self.temporary.name) / "catalog.json"
        path.write_text(json.dumps({
            "version": "test-catalog-v1",
            "source": "https://example.invalid/catalog",
            "concepts": [{
                "concept_id": "concept-alpha", "name": "Example concept",
                "description": "Structural test concept description", "language": "es",
                "source": "https://example.invalid/catalog", "license": "Test-only",
                "publication_status": "authorized", "codes": [{
                    "system": "TEST", "edition": "test-edition", "axis": "other",
                    "code": "alpha", "name": "Example entry", "description": "Structural test description",
                    "status": "current", "source": "https://example.invalid/catalog",
                    "license": "Test-only", "relationship": "primary",
                    "relationship_status": "source-declared",
                }, {
                    "system": "TEST", "edition": "test-edition", "axis": "other",
                    "code": "gamma", "name": "Pending relation", "description": "Relation awaiting validation",
                    "status": "current", "source": "https://example.invalid/catalog",
                    "license": "Test-only", "relationship": "exact",
                    "relationship_status": "pending",
                }],
            }, {
                "concept_id": "concept-beta", "name": "Draft concept",
                "description": "Unapproved test concept", "language": "es",
                "source": "https://example.invalid/catalog", "license": "Test-only",
                "publication_status": "draft", "codes": [{
                    "system": "TEST", "edition": "test-edition", "axis": "other",
                    "code": "beta", "name": "Draft entry", "description": "Unapproved test term",
                    "status": "current", "source": "https://example.invalid/catalog",
                    "license": "Test-only", "relationship": "primary",
                    "relationship_status": "source-declared",
                }],
            }],
        }), encoding="utf-8")
        with override_settings(RNC_CODING_CATALOG=path):
            response = self.client.get("/nomencladores/?q=structural")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alpha")
        self.assertContains(response, "Structural test description")
        self.assertContains(response, "Test-only")
        self.assertNotContains(response, "beta")
        self.assertNotContains(response, "gamma")
        validation_output = io.StringIO()
        call_command("validate_coding_catalog", str(path), stdout=validation_output)
        self.assertIn("Catálogo válido", validation_output.getvalue())
        self.assertIn("códigos: 3", validation_output.getvalue())
        self.assertNotIn("alpha", validation_output.getvalue())

    def test_normalized_coding_csv_import_preserves_literal_codes(self):
        from analytics.coding_nomenclators import load_catalog

        csv_path = Path(self.temporary.name) / "normalized.csv"
        output_path = Path(self.temporary.name) / "catalog.json"
        fields = [
            "concept_id", "concept_name", "concept_description", "language",
            "concept_source", "concept_license", "publication_status", "system",
            "edition", "axis", "code", "code_name", "code_description",
            "code_status", "code_source", "code_license", "relationship",
            "relationship_status",
        ]
        base = [
            "example-concept", "Example concept", "Generic test concept", "es",
            "https://example.invalid/test", "Test-only", "draft", "TEST",
            "edition-test", "classification", "0007", "Example code", "Generic test code",
            "current", "https://example.invalid/test", "Test-only", "primary",
            "pending",
        ]
        import csv
        with csv_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(fields)
            writer.writerow(base)
            writer.writerow([*base[:10], "0010", *base[11:]])

        call_command(
            "import_coding_catalog_csv", str(csv_path), str(output_path),
            catalog_version="test-v1", source="https://example.invalid/catalog",
        )
        catalog = load_catalog(output_path)
        self.assertEqual(catalog["concepts"][0]["codes"][0]["code"], "0007")
        self.assertEqual(catalog["concepts"][0]["codes"][1]["code"], "0010")
        self.assertEqual(len(catalog["concepts"]), 1)

    def test_normalized_coding_csv_import_rejects_inconsistent_concept_metadata(self):
        from django.core.management.base import CommandError
        import csv

        csv_path = Path(self.temporary.name) / "conflicting.csv"
        output_path = Path(self.temporary.name) / "should-not-exist.json"
        fields = [
            "concept_id", "concept_name", "concept_description", "language",
            "concept_source", "concept_license", "publication_status", "system",
            "edition", "axis", "code", "code_name", "code_description",
            "code_status", "code_source", "code_license", "relationship",
            "relationship_status",
        ]
        base = [
            "example-concept", "Example concept", "Generic test concept", "es",
            "https://example.invalid/test", "Test-only", "draft", "TEST",
            "edition-test", "other", "A1", "Example code", "Generic test code",
            "current", "https://example.invalid/test", "Test-only", "primary",
            "pending",
        ]
        conflict = list(base)
        conflict[1] = "Conflicting concept name"
        with csv_path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(fields)
            writer.writerow(base)
            writer.writerow(conflict)

        with self.assertRaisesRegex(CommandError, "metadatos del concepto"):
            call_command(
                "import_coding_catalog_csv", str(csv_path), str(output_path),
                catalog_version="test-v1", source="https://example.invalid/catalog",
            )
        self.assertFalse(output_path.exists())

    def test_home_and_query_explain_synthetic_site_categories(self):
        self.delivery(publish=True)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Qué es el RNC?")
        self.assertNotIn("top", response.context)
        query = self.client.get("/consulta/")
        self.assertContains(query, 'class="query-workspace"')
        self.assertContains(query, 'action="#visualizacion"')
        self.assertContains(query, 'href="#filtros"')
        self.assertContains(query, "no forman un catálogo completo")
        self.assertTrue(query.context["table"][0]["description"])
        self.assertIn(
            query.context["table"][0]["description"],
            query.context["chart_payload"]["label_descriptions"].values(),
        )

    def test_anonymous_requires_login_on_every_private_route(self):
        for path in [
            "/administracion/cortes/",
            "/administracion/cortes/ejemplo/",
            "/administracion/usuarios/",
            "/administracion/usuarios/nuevo/",
        ]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 302)

    def test_capability_matrix_enforced_by_backend(self):
        for user, uploads, accounts in [
            (self.reader, 403, 403),
            (self.operator, 200, 403),
            (self.publisher, 200, 403),
            (self.root, 200, 200),
        ]:
            self.client.force_login(user)
            with self.subTest(user=user.username):
                self.assertEqual(
                    self.client.get("/administracion/cortes/").status_code, uploads
                )
                self.assertEqual(
                    self.client.get("/administracion/usuarios/").status_code, accounts
                )

    def test_old_admin_cannot_bypass_account_policies(self):
        self.assertRedirects(
            self.client.get("/admin/"),
            "/administracion/usuarios/",
            fetch_redirect_response=False,
        )
        self.client.force_login(self.root)
        self.assertEqual(self.client.get("/admin/auth/user/add/").status_code, 404)

    def test_role_revocation_and_deactivation_are_immediate(self):
        self.client.force_login(self.operator)
        self.operator.groups.clear()
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 403)
        self.operator.is_active = False
        self.operator.save()
        self.assertEqual(self.client.get("/administracion/cortes/").status_code, 302)

    def test_login_redirects_and_external_next_rejected(self):
        for user, destination in [
            (self.reader, "/"),
            (self.operator, "/administracion/cortes/"),
            (self.root, "/administracion/cortes/"),
        ]:
            self.client.logout()
            r = self.client.post(
                "/acceso/",
                {
                    "username": user.username,
                    "password": PASSWORD,
                    "next": "https://evil.invalid",
                },
            )
            self.assertRedirects(r, destination)

    def test_login_empty_fields_and_generic_invalid_credentials(self):
        r = self.client.post("/acceso/", {})
        self.assertIn("username", r.context["form"].errors)
        self.assertIn("password", r.context["form"].errors)
        r = self.client.post(
            "/acceso/", {"username": self.reader.username, "password": "Incorrecta"}
        )
        self.assertTrue(r.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_csrf_and_logout_post(self):
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(c.post("/acceso/", {}).status_code, 403)
        c.force_login(self.root)
        self.assertEqual(c.get("/salir/").status_code, 405)
        self.assertEqual(c.post("/salir/").status_code, 403)
        c.get("/administracion/cortes/")
        token = c.cookies["csrftoken"].value
        self.assertRedirects(
            c.post("/salir/", {"csrfmiddlewaretoken": token}), "/acceso/"
        )

    def test_create_invited_account_persists_role_hash_policy_audit_and_mail(self):
        r = self.post_account()
        self.assertRedirects(r, "/administracion/usuarios/")
        u = self.User.objects.get(username="cuenta_nueva")
        self.assertFalse(u.has_usable_password())
        self.assertFalse(u.is_superuser)
        self.assertTrue(u.groups.filter(name="operator").exists())
        self.assertEqual(u.email, "nueva@example.invalid")
        self.assertTrue(
            AccountPolicy.objects.filter(user=u, must_change_password=False).exists()
        )
        self.assertEqual(AccountMail.objects.get(user=u).status, "pending")
        self.assertTrue(
            AuditEvent.objects.filter(target=str(u.pk), action="Cuenta creada").exists()
        )

    def test_empty_account_has_field_errors_and_no_writes(self):
        self.client.force_login(self.root)
        before = self.User.objects.count()
        r = self.client.post("/administracion/usuarios/nuevo/", {})
        self.assertEqual(self.User.objects.count(), before)
        for name in [
            "username",
            "first_name",
            "last_name",
            "email",
            "confirm_password",
            "role",
        ]:
            self.assertIn(name, r.context["form"].errors)
        self.assertContains(r, 'aria-invalid="true"')
        self.assertContains(r, 'id="id_email_error"')

    def test_account_contract_rejects_invalid_names_usernames_and_email(self):
        for name, value in [
            ("username", "<script>"),
            ("first_name", "Ana123"),
            ("last_name", "Pérez<script>"),
            ("email", "correo@@mal"),
            ("first_name", "Ana\x00"),
            ("username", "a"),
            ("role", "superusuario_inventado"),
        ]:
            with self.subTest(field=name, value=value):
                r = self.post_account(**{name: value})
                self.assertIn(name, r.context["form"].errors)
                self.assertFalse(
                    self.User.objects.filter(username="cuenta_nueva").exists()
                )

    def test_duplicate_username_case_and_email_rejected_on_correct_field(self):
        for field, value in [
            ("username", "QA_ROOT"),
            ("email", "ROOT@EXAMPLE.INVALID"),
        ]:
            with self.subTest(field=field):
                r = self.post_account(**{field: value})
                self.assertIn(field, r.context["form"].errors)

    def test_bad_support_password_does_not_create_account(self):
        r = self.post_account(confirm_password="No-es-correcta")
        self.assertIn("confirm_password", r.context["form"].errors)
        self.assertFalse(self.User.objects.filter(username="cuenta_nueva").exists())

    def test_weak_or_long_temporary_password_rejected(self):
        for secret in ["123", "123456789012", "password", "a" * 129, "cuenta_nueva"]:
            with self.subTest(length=len(secret)):
                r = self.post_account(initial_password=secret)
                self.assertIn("initial_password", r.context["form"].errors)

    def test_password_symbols_and_accented_names_are_legitimate(self):
        self.post_account(initial_password=PASSWORD)
        u = self.User.objects.get(username="cuenta_nueva")
        self.assertNotEqual(u.password, PASSWORD)
        self.assertTrue(u.check_password(PASSWORD))
        self.assertEqual(u.first_name, "María José")
        self.assertTrue(AccountPolicy.objects.get(user=u).must_change_password)

    def test_temporary_password_forces_change_and_hash_stored(self):
        self.post_account(initial_password=PASSWORD)
        u = self.User.objects.get(username="cuenta_nueva")
        c = Client()
        c.login(username=u.username, password=PASSWORD)
        self.assertRedirects(c.get("/"), "/cuenta/contrasena/")
        self.assertEqual(
            c.post(
                "/cuenta/contrasena/",
                {
                    "old_password": "wrong",
                    "new_password1": "Better<> 'Private-2026!",
                    "new_password2": "Better<> 'Private-2026!",
                },
            ).status_code,
            200,
        )
        self.assertTrue(AccountPolicy.objects.get(user=u).must_change_password)
        self.assertRedirects(
            c.post(
                "/cuenta/contrasena/",
                {
                    "old_password": PASSWORD,
                    "new_password1": "Better<> 'Private-2026!",
                    "new_password2": "Better<> 'Private-2026!",
                },
            ),
            "/cuenta/contrasena/actualizada/",
        )
        u.refresh_from_db()
        self.assertTrue(u.check_password("Better<> 'Private-2026!"))
        self.assertFalse(AccountPolicy.objects.get(user=u).must_change_password)
        self.assertEqual(c.get("/administracion/cortes/").status_code, 200)

    def test_mismatched_and_overlong_new_passwords_not_saved(self):
        self.client.force_login(self.reader)
        for p1, p2 in [("A-new-pass-2026!", "Different-pass!"), ("x" * 129, "x" * 129)]:
            with self.subTest(length=len(p1)):
                r = self.client.post(
                    "/cuenta/contrasena/",
                    {
                        "old_password": PASSWORD,
                        "new_password1": p1,
                        "new_password2": p2,
                    },
                )
                self.assertTrue(r.context["form"].errors)
                self.reader.refresh_from_db()
                self.assertTrue(self.reader.check_password(PASSWORD))

    def test_self_deactivation_and_self_demotion_forbidden(self):
        self.client.force_login(self.root)
        for updates in [{"is_active": ""}, {"role": "reader"}]:
            data = (
                self.account_data(
                    username=self.root.username,
                    email=self.root.email,
                    role="superadmin",
                    **updates,
                )
                if "role" not in updates
                else self.account_data(
                    username=self.root.username, email=self.root.email, **updates
                )
            )
            r = self.client.post(f"/administracion/usuarios/{self.root.pk}/", data)
            self.assertTrue(r.context["form"].non_field_errors())
            self.root.refresh_from_db()
            self.assertTrue(self.root.is_active)
            self.assertTrue(self.root.is_superuser)

    def test_edit_deactivate_reactivate_and_reassign_roles(self):
        self.client.force_login(self.root)
        r = self.client.post(
            f"/administracion/usuarios/{self.reader.pk}/",
            self.account_data(
                username=self.reader.username,
                email=self.reader.email,
                role="publisher",
                is_active="",
            ),
        )
        self.assertEqual(r.status_code, 302)
        self.reader.refresh_from_db()
        self.assertFalse(self.reader.is_active)
        self.assertTrue(self.reader.groups.filter(name="publisher").exists())
        self.client.post(
            f"/administracion/usuarios/{self.reader.pk}/",
            self.account_data(
                username=self.reader.username, email=self.reader.email, role="reader"
            ),
        )
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.is_active)
        self.assertFalse(self.reader.groups.exists())

    def test_search_pagination_and_injection_as_data(self):
        self.client.force_login(self.root)
        for n in range(15):
            self.User.objects.create_user(f"pagination_{n}")
        self.assertEqual(
            len(
                self.client.get("/administracion/usuarios/", {"page": 2}).context[
                    "page"
                ]
            ),
            7,
        )
        r = self.client.get("/administracion/usuarios/", {"q": "qa_root"})
        self.assertEqual(r.context["page"].paginator.count, 1)
        r = self.client.get("/administracion/usuarios/", {"q": "' OR '1'='1"})
        self.assertTrue(r.context["search_form"].errors)
        self.assertEqual(r.context["page"].paginator.count, 0)
        self.assertEqual(self.User.objects.count(), 19)

    def test_mail_worker_and_invitation_activation_end_to_end(self):
        self.client.cookies["rnc_language"] = "en"
        self.post_account()
        u = self.User.objects.get(username="cuenta_nueva")
        queued_mail = AccountMail.objects.get(user=u)
        self.assertEqual(queued_mail.language, "en")
        call_command("deliver_account_mail", stdout=io.StringIO())
        queued_mail.refresh_from_db()
        self.assertEqual(queued_mail.status, "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Set password · NCR")
        self.assertIn("A password has been requested for your NCR account.", mail.outbox[0].body)
        link = next(
            line
            for line in mail.outbox[0].body.splitlines()
            if line.startswith("https://")
        )
        self.assertTrue(link.startswith("https://rnc.example.invalid/"))
        path = link.split("example.invalid", 1)[1]
        c = Client()
        r = c.get(path, follow=True)
        self.assertTrue(r.context["validlink"])
        action = r.request["PATH_INFO"]
        new = "Invited<> 'Private-2026!"
        self.assertRedirects(
            c.post(action, {"new_password1": new, "new_password2": new}),
            "/cuenta/restablecida/",
        )
        u.refresh_from_db()
        self.assertTrue(u.check_password(new))
        self.assertFalse(Client().get(path, follow=True).context["validlink"])

    def test_recovery_email_uses_selected_language(self):
        self.client.cookies["rnc_language"] = "en"
        response = self.client.post(
            "/cuenta/recuperar/", {"email": self.reader.email}
        )
        self.assertRedirects(response, "/cuenta/recuperar/solicitado/")
        queued_mail = AccountMail.objects.get(user=self.reader)
        self.assertEqual(queued_mail.language, "en")

        call_command("deliver_account_mail", stdout=io.StringIO())
        queued_mail.refresh_from_db()
        self.assertEqual(queued_mail.status, "sent")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Set password · NCR")
        self.assertIn("A password has been requested for your NCR account.", mail.outbox[0].body)

    def test_recovery_unknown_inactive_and_known_account_have_same_public_result(self):
        for address in ["reader@example.invalid", "missing@example.invalid"]:
            r = self.client.post("/cuenta/recuperar/", {"email": address})
            self.assertRedirects(r, "/cuenta/recuperar/solicitado/")
        self.assertEqual(AccountMail.objects.count(), 1)
        self.reader.is_active = False
        self.reader.save()
        AccountMail.objects.all().delete()
        self.client.post("/cuenta/recuperar/", {"email": self.reader.email})
        self.assertFalse(AccountMail.objects.exists())

    def test_recovery_rate_limit_deduplicates_mail(self):
        for _ in range(8):
            self.assertEqual(
                self.client.post(
                    "/cuenta/recuperar/", {"email": self.reader.email}
                ).status_code,
                302,
            )
        self.assertEqual(AccountMail.objects.count(), 1)

    def test_expired_invalid_tokens_and_deactivated_account(self):
        uid = urlsafe_base64_encode(force_bytes(self.reader.pk))
        token = default_token_generator.make_token(self.reader)
        path = f"/cuenta/restablecer/{uid}/{token}/"
        now = default_token_generator._now()
        with patch.object(
            default_token_generator, "_now", return_value=now + timedelta(hours=2)
        ):
            self.assertFalse(self.client.get(path, follow=True).context["validlink"])
        self.assertFalse(
            self.client.get(
                f"/cuenta/restablecer/{uid}/bad-token/", follow=True
            ).context["validlink"]
        )
        self.reader.is_active = False
        self.reader.save()
        r = self.client.get(path, follow=True)
        if r.context["validlink"]:
            self.client.post(
                r.request["PATH_INFO"],
                {
                    "new_password1": "Changed-safe-2026!",
                    "new_password2": "Changed-safe-2026!",
                },
            )
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.check_password(PASSWORD))

    def test_smtp_failure_recorded_without_exposing_secret(self):
        AccountMail.objects.create(user=self.reader)
        with patch(
            "public_site.accounts.send_mail",
            side_effect=RuntimeError("private-transport-details"),
        ):
            call_command("deliver_account_mail", stdout=io.StringIO())
        self.assertEqual(AccountMail.objects.get().status, "failed")
        self.client.force_login(self.root)
        r = self.client.get("/administracion/usuarios/")
        self.assertContains(r, "Falló el envío")
        self.assertNotContains(r, "private-transport-details")

    def test_upload_stores_private_original_json_and_metadata(self):
        d = self.delivery()
        self.assertEqual(d.row_count, 73)
        self.assertEqual(d.person_count, 36)
        self.assertEqual(d.report["accepted_rows"], 73)
        path = Path(self.temporary.name) / d.storage_key
        self.assertTrue(path.exists())
        self.assertTrue(path.with_suffix(".csv").exists())
        self.assertEqual(len(json.loads(path.read_text())), 73)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            d.checksum, __import__("hashlib").sha256(csv_bytes()).hexdigest()
        )

    def test_upload_duplicate_is_not_another_delivery(self):
        self.delivery()
        with self.assertRaisesMessage(ValueError, "ya está registrada"):
            self.delivery()
        self.assertEqual(Delivery.objects.count(), 1)

    def test_upload_empty_missing_file_or_confirmation_is_field_specific(self):
        self.client.force_login(self.root)
        r = self.client.post("/administracion/cortes/", {})
        for field in ["title", "file", "synthetic"]:
            self.assertIn(field, r.context["form"].errors)
        self.assertFalse(Delivery.objects.exists())

    def test_required_checkbox_message_is_correct_in_spanish_and_english(self):
        from .forms import UploadForm

        with override_language("es"):
            form = UploadForm({})
            self.assertFalse(form.is_valid())
            self.assertEqual(
                str(form.errors["synthetic"][0]),
                "Marque esta casilla para continuar.",
            )
        with override_language("en"):
            form = UploadForm({})
            self.assertFalse(form.is_valid())
            self.assertEqual(
                str(form.errors["synthetic"][0]),
                "Check this box to continue.",
            )

    def test_upload_wrong_extension_and_title_rejected_before_storage(self):
        self.client.force_login(self.root)
        for title, name, field in [
            ("Corte válido", "sintetico.exe", "file"),
            ("<script>alert(1)</script>", "sintetico.csv", "title"),
        ]:
            r = self.client.post(
                "/administracion/cortes/",
                {"title": title, "file": uploaded(name=name), "synthetic": "on"},
            )
            self.assertIn(field, r.context["form"].errors)
        self.assertFalse(Delivery.objects.exists())

    def test_uploaded_oversize_file_rejected(self):
        from .forms import UploadForm

        file = uploaded()
        file.size = 12 * 1024 * 1024 + 1
        f = UploadForm({"title": "Corte válido", "synthetic": "on"}, {"file": file})
        self.assertFalse(f.is_valid())
        self.assertIn("file", f.errors)

    def test_bad_csv_variants_are_rejected_atomically_and_audited(self):
        variants = []
        variants.append(b"header,no-compatible\n1,2\n")
        variants.append(b"\xff\xfeinvalid")
        for field, value in [
            ("synthetic", "FALSE"),
            ("person_id", "real-id"),
            ("tumor_id", "real-tumor"),
            ("period", "2024<script>"),
            ("population", "0"),
            ("standard_weight", "99"),
            ("sex_id", "99"),
            ("site_id", "999"),
            ("territory_id", "999"),
        ]:
            rows = synthetic_rows()
            rows[0][field] = value
            variants.append(csv_bytes(rows))
        rows = synthetic_rows()
        rows[1]["tumor_id"] = rows[0]["tumor_id"]
        variants.append(csv_bytes(rows))
        rows = synthetic_rows()
        rows.pop(0)
        variants.append(csv_bytes(rows))
        for index, raw in enumerate(variants):
            with self.subTest(variant=index):
                with self.assertRaises(ValueError):
                    ingest(
                        SimpleUploadedFile("invalid.csv", raw),
                        "Carga inválida",
                        self.root,
                    )
                self.assertFalse(Delivery.objects.filter(status="validated").exists())
        self.assertEqual(
            Delivery.objects.filter(status="rejected").count(), len(variants)
        )
        self.assertEqual(
            AuditEvent.objects.filter(action="Carga rechazada técnicamente").count(),
            len(variants),
        )

    def test_bad_upload_renders_file_error_and_preserves_title(self):
        self.client.force_login(self.root)
        r = self.client.post(
            "/administracion/cortes/",
            {
                "title": "Mi corte",
                "synthetic": "on",
                "file": SimpleUploadedFile("invalid.csv", b"wrong\n"),
            },
        )
        self.assertIn("file", r.context["form"].errors)
        self.assertContains(r, 'value="Mi corte"')

    @patch("public_site.portal.ingest", side_effect=OverflowError)
    def test_upload_numeric_overflow_message_uses_selected_language(self, ingest_mock):
        self.client.force_login(self.root)
        self.client.cookies["rnc_language"] = "en"
        response = self.client.post(
            "/administracion/cortes/",
            {
                "title": "Synthetic test release",
                "synthetic": "on",
                "file": uploaded(),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Numeric value is out of range.",
            status_code=200,
        )
        ingest_mock.assert_called_once()

    def test_publish_replace_revoke_and_audit_are_persistent(self):
        first = self.delivery(publish=True)
        second = self.delivery(extra=2)
        self.apply_transition(
            second.pk, "publish", self.publisher, "Nueva versión sintética revisada."
        )
        first.refresh_from_db()
        self.assertEqual(first.status, "revoked")
        self.assertEqual(Publication.objects.get(pk=1).delivery_id, second.pk)
        active_home = self.client.get("/")
        self.assertContains(active_home, "¿Qué es el RNC?")
        self.assertNotContains(active_home, "home-publication-note")
        self.apply_transition(
            second.pk, "revoke", self.publisher, "Revocación sintética para revisión."
        )
        self.assertIsNone(Publication.objects.get(pk=1).delivery_id)
        self.assertFalse(self.client.get("/consulta/").context["table"])
        self.assertTrue(
            AuditEvent.objects.filter(
                action="Revocación", actor=self.publisher, target=str(second.pk)
            ).exists()
        )

    def test_admin_upload_publish_public_profile_and_revoke_flow(self):
        self.client.force_login(self.root)
        upload = self.client.post(
            "/administracion/cortes/",
            {
                "title": "Corte sintético para flujo público",
                "synthetic": "on",
                "file": uploaded(extra=1),
            },
        )
        self.assertEqual(upload.status_code, 302)
        delivery = Delivery.objects.get(title="Corte sintético para flujo público")
        self.assertEqual(delivery.status, "validated")

        publish_path = f"/administracion/cortes/{delivery.pk}/estado/"
        with self.captureOnCommitCallbacks(execute=True):
            publish = self.client.post(
                publish_path,
                {
                    "action": "publish",
                    "reason": "Publicación sintética para probar el flujo.",
                },
            )
        self.assertEqual(publish.status_code, 302)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "published")

        release_root = Path(self.temporary.name) / "public-releases"
        artifact = release_root / f"{delivery.pk}.json"
        artifact_text = artifact.read_text(encoding="utf-8")
        self.assertNotIn("SYN-P-", artifact_text)
        self.assertNotIn("SYN-T-", artifact_text)
        self.assertNotIn('"person_id"', artifact_text)
        self.assertNotIn('"tumor_id"', artifact_text)

        public_settings = {
            "ROOT_URLCONF": "config.urls_public",
            "MIDDLEWARE": [
                "django.middleware.security.SecurityMiddleware",
                "django.middleware.common.CommonMiddleware",
                "django.middleware.clickjacking.XFrameOptionsMiddleware",
            ],
            "TEMPLATES": [
                {
                    "BACKEND": "django.template.backends.django.DjangoTemplates",
                    "DIRS": [Path(__file__).resolve().parent.parent / "templates"],
                    "APP_DIRS": True,
                    "OPTIONS": {
                        "context_processors": [
                            "django.template.context_processors.request"
                        ]
                    },
                }
            ],
            "DATABASES": {"default": {"ENGINE": "django.db.backends.dummy"}},
            "PRIVATE_STORAGE_ROOT": None,
            "PUBLIC_RELEASE_ROOT": release_root,
        }
        with override_settings(**public_settings):
            public_client = Client()
            home = public_client.get("/")
            self.assertEqual(home.status_code, 200)
            self.assertIsNotNone(home.context["delivery"])
            self.assertNotIn("summary", home.context)
            self.assertNotContains(home, "SYN-P-")
            self.assertNotContains(home, "SYN-T-")

            explorer = public_client.get("/consulta/", {"unit": "persons"})
            self.assertEqual(explorer.status_code, 200)
            self.assertEqual(explorer.context["summary"]["persons"], 36)
            self.assertEqual(public_client.get("/administracion/cortes/").status_code, 404)
            self.assertEqual(public_client.get("/acceso/").status_code, 404)

        with self.captureOnCommitCallbacks(execute=True):
            revoke = self.client.post(
                publish_path,
                {
                    "action": "revoke",
                    "reason": "Revocación sintética para probar el flujo.",
                },
            )
        self.assertEqual(revoke.status_code, 302)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, "revoked")
        empty_home = self.client.get("/")
        self.assertEqual(empty_home.status_code, 200)
        self.assertIsNone(empty_home.context["delivery"])
        self.assertNotIn("summary", empty_home.context)

    def test_operator_cannot_publish_even_with_forged_post(self):
        d = self.delivery()
        self.client.force_login(self.operator)
        self.assertEqual(
            self.client.post(
                f"/administracion/cortes/{d.pk}/estado/",
                {"action": "publish", "reason": "Intento sin autorización."},
            ).status_code,
            403,
        )
        d.refresh_from_db()
        self.assertEqual(d.status, "validated")

    def test_decision_invalid_reason_action_and_stale_state_not_saved(self):
        d = self.delivery()
        self.client.force_login(self.root)
        path = f"/administracion/cortes/{d.pk}/estado/"
        for data in [
            {"action": "publish", "reason": "corto"},
            {"action": "publish", "reason": "<script>alert(1)</script>"},
            {"action": "drop_database", "reason": "Una razón de longitud suficiente."},
        ]:
            r = self.client.post(path, data)
            self.assertEqual(r.status_code, 400)
            self.assertTrue(r.context["decision_form"].errors)
            d.refresh_from_db()
            self.assertEqual(d.status, "validated")
        self.apply_transition(d.pk, "publish", self.root, "Publicación inicial de prueba.")
        self.client.cookies["rnc_language"] = "en"
        r = self.client.post(
            path, {"action": "publish", "reason": "Acción antigua repetida."}
        )
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.context["decision_form"].non_field_errors())
        self.assertContains(
            r,
            "This action is no longer valid for the current status.",
            status_code=400,
        )

    def test_home_query_and_exports_never_include_private_people(self):
        self.delivery(publish=True)
        for path in ["/", "/consulta/", "/consulta/?format=csv"]:
            r = self.client.get(path)
            self.assertNotContains(r, "Ana O’Neill")
            self.assertNotContains(r, "SYN-P-")
            self.assertNotContains(r, "SYN-T-")
        self.assertEqual(
            self.client.get("/private/ejemplo_sintetico.csv").status_code, 404
        )

    def test_people_unique_across_tumors_years_and_denominators_deduplicated(self):
        self.delivery(publish=True)
        r = self.client.get("/consulta/", {"unit": "persons"})
        self.assertEqual(r.context["summary"]["persons"], 36)
        self.assertEqual(r.context["summary"]["tumors"], 73)
        r = self.client.get("/consulta/", {"metric": "rate", "dimension": "sex"})
        self.assertEqual(sum(row["population"] for row in r.context["table"]), 720000)
        r = self.client.get(
            "/consulta/",
            {
                "year": "2024",
                "site": "Colon y recto",
                "dimension": "sex",
                "metric": "rate",
            },
        )
        self.assertEqual(sum(row["population"] for row in r.context["table"]), 360000)

    def test_multiple_filter_values_aggregate_tumors_and_explain_person_limit(self):
        self.delivery(publish=True)
        from django.http import QueryDict

        query = QueryDict("", mutable=True)
        query.setlist("year", ["2023", "2024"])
        query.setlist("age", ["0-4", "5-9"])
        query.setlist("site", ["Mama", "Colon y recto"])
        response = self.client.get("/consulta/", query)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].errors)
        self.assertEqual(response.context["summary"]["tumors"], 8)
        self.assertIsNone(response.context["summary"]["persons"])
        self.assertEqual(
            {row["label"] for row in response.context["table"]},
            {"Mama", "Colon y recto"},
        )
        self.assertTrue(response.context["multi_value_filters"])
        self.assertContains(response, "Personas distintas")
        self.assertContains(response, "Las personas distintas no se calculan cuando se combinan varios valores")
        self.assertContains(response, "2023, 2024")

        query["metric"] = "rate"
        response = self.client.get("/consulta/", query)
        self.assertEqual(response.context["summary"]["tumors"], 8)
        self.assertTrue(all(row["population"] == 80000 for row in response.context["table"]))
        self.assertTrue(all(row["value"] == 5 for row in response.context["table"]))
        query["metric"] = "count"

        export_query = query.copy()
        export_query["format"] = "csv"
        exported = self.client.get("/consulta/", export_query)
        csv_text = exported.content.decode("utf-8-sig")
        self.assertEqual(exported.status_code, 200)
        self.assertIn('Año de incidencia,"2023, 2024"', csv_text)
        self.assertIn("Provincia de residencia,Provincias disponibles; cobertura nacional incompleta", csv_text)
        self.assertIn("Municipio de residencia,No disponible en este corte", csv_text)
        self.assertIn("grupos de localización pueden solaparse en personas distintas", csv_text)

        query["unit"] = "persons"
        response = self.client.get("/consulta/", query)
        self.assertIn("unit", response.context["form"].errors)
        self.assertFalse(response.context["table"])

    def test_unknown_filter_and_incompatible_graphs_have_field_errors(self):
        self.delivery(publish=True)
        for data, field in [
            ({"year": "bad"}, "year"),
            ({"chart": "line", "dimension": "site"}, "dimension"),
            ({"metric": "asr", "age": "0-4"}, "metric"),
            ({"chart": "stacked", "metric": "rate"}, "metric"),
            ({"chart": "pie", "unit": "persons"}, "unit"),
            ({"chart": "grouped", "sex": "Mujeres"}, "chart"),
            ({"chart": "scatter", "dimension": "site"}, "dimension"),
            ({"chart": "scatter", "unit": "persons"}, "unit"),
            ({"chart": "pie", "metric": "rate"}, "metric"),
            ({"chart": "strip", "dimension": "sex"}, "dimension"),
        ]:
            r = self.client.get("/consulta/", data)
            self.assertIn(field, r.context["form"].errors)
            self.assertFalse(r.context["table"])

    @tag("long_running")
    def test_exhaustive_selector_and_single_value_filter_matrix(self):
        """Exercise every selector tuple against every single-value filter tuple in the demo."""
        from itertools import product

        from .aggregate_release import current_public_release
        from .aggregate_statistics import results
        from .chart_context import describe_query
        from .public_forms import ExplorerForm
        from .public_portal import CHARTS, METRICS
        from .aggregate_statistics import DIMENSIONS

        self.delivery(publish=True)
        release = current_public_release()
        options = {
            "year": release["options"]["period"],
            "territory": release["options"]["territory"],
            "sex": release["options"]["sex"],
            "age": release["options"]["age_group"],
            "site": release["options"]["site"],
        }
        filters = [dict.fromkeys(options)]
        filters.extend(
            dict(zip(options, values))
            for values in product(*(options[key] for key in options))
        )
        selector_tuples = product(
            DIMENSIONS,
            METRICS,
            ("tumors", "persons"),
            CHARTS,
        )

        checked = valid = 0
        for dimension, metric, unit, chart in selector_tuples:
            for filter_values in filters:
                data = {
                    "dimension": dimension,
                    "metric": metric,
                    "unit": unit,
                    "chart": chart,
                }
                data.update(
                    {
                        key: [filter_values[key]] if filter_values.get(key) else []
                        for key in options
                    }
                )
                form = ExplorerForm(
                    data,
                    options=options,
                    dimensions=DIMENSIONS,
                    charts=CHARTS,
                    metrics=METRICS,
                )
                checked += 1
                if form.is_valid():
                    valid += 1
                    params = dict(form.cleaned_data)
                    table, total = results(params, release)
                    self.assertGreaterEqual(total["tumors"], 0)
                    self.assertGreaterEqual(total["population"], 0)
                    self.assertTrue(all(row["value"] is None or row["value"] >= 0 for row in table))
                    self.assertEqual(
                        sum(row["tumors"] for row in table), total["tumors"]
                    )

        self.assertEqual(
            checked,
            len(DIMENSIONS) * len(METRICS) * 2 * len(CHARTS) * len(filters),
        )
        self.assertGreater(valid, 0)

    @tag("long_running")
    def test_every_subset_of_each_individual_filter(self):
        """Enumerate all multiselect states for each field independently."""
        from itertools import combinations

        from .aggregate_release import current_public_release
        from .aggregate_statistics import results

        self.delivery(publish=True)
        release = current_public_release()
        options = {
            "year": release["options"]["period"],
            "territory": release["options"]["territory"],
            "sex": release["options"]["sex"],
            "age": release["options"]["age_group"],
            "site": release["options"]["site"],
        }
        checked = 0
        for field, values in options.items():
            for size in range(len(values) + 1):
                for selection in combinations(values, size):
                    params = {
                        "year": [],
                        "territory": [],
                        "sex": [],
                        "age": [],
                        "site": [],
                        "dimension": "site",
                        "metric": "count",
                        "unit": "tumors",
                    }
                    params[field] = list(selection)
                    table, total = results(params, release)
                    self.assertEqual(sum(row["tumors"] for row in table), total["tumors"])
                    self.assertTrue(all(row["tumors"] >= 0 for row in table))
                    checked += 1
        self.assertEqual(checked, sum(2 ** len(values) for values in options.values()))

    @tag("long_running")
    def test_all_compatible_selector_combinations_export_every_format(self):
        """Cross valid selector combinations with all five supported exports."""
        from itertools import product

        from .aggregate_statistics import DIMENSIONS
        from .public_forms import ExplorerForm
        from .public_portal import CHARTS, METRICS

        self.delivery(publish=True)
        options = {
            "year": ["2023", "2024"],
            "territory": ["La Habana"],
            "sex": ["Mujeres", "Hombres"],
            "age": [f"{n}-{n + 4}" for n in range(0, 85, 5)] + ["85+"],
            "site": ["Mama", "Colon y recto"],
        }
        signatures = {
            "csv": b"\xef\xbb\xbf",
            "xlsx": b"PK",
            "png": b"\x89PNG",
            "svg": b"<?xml",
            "pdf": b"%PDF",
        }
        formats = tuple(signatures)
        combinations_checked = exports_checked = 0
        for dimension, metric, unit, chart in product(
            DIMENSIONS, METRICS, ("tumors", "persons"), CHARTS
        ):
            params = {
                "dimension": dimension,
                "metric": metric,
                "unit": unit,
                "chart": chart,
            }
            form = ExplorerForm(
                params,
                options=options,
                dimensions=DIMENSIONS,
                charts=CHARTS,
                metrics=METRICS,
            )
            if not form.is_valid():
                continue
            combinations_checked += 1
            response = self.client.get("/consulta/", params)
            if response.context["errors"] or not response.context["table"]:
                continue
            for fmt, signature in signatures.items():
                with self.subTest(dimension=dimension, metric=metric, unit=unit, chart=chart, format=fmt):
                    # Exercise export behavior independently of the separate
                    # per-minute rendering throttle and export response cache.
                    cache.clear()
                    exported = self.client.get("/consulta/", {**params, "format": fmt})
                    self.assertEqual(exported.status_code, 200)
                    self.assertTrue(exported.content.startswith(signature))
                    self.assertEqual(exported["Cache-Control"], "no-store")
                    exports_checked += 1
        self.assertGreater(combinations_checked, 0)
        self.assertGreater(exports_checked, 0)

    @patch("public_site.public_portal.export_result")
    def test_rendered_export_limit_allows_twenty_and_blocks_the_next(self, exporter):
        from itertools import product
        from django.http import HttpResponse

        from .aggregate_statistics import DIMENSIONS
        from .public_forms import ExplorerForm
        from .public_portal import CHARTS, METRICS

        self.delivery(publish=True)
        exporter.return_value = HttpResponse(
            b"image", content_type="image/png", headers={"Content-Disposition": "attachment; filename=chart.png"}
        )
        options = {
            "year": ["2023", "2024"],
            "territory": ["La Habana"],
            "sex": ["Mujeres", "Hombres"],
            "age": [f"{n}-{n + 4}" for n in range(0, 85, 5)] + ["85+"],
            "site": ["Mama", "Colon y recto"],
        }
        successful = 0
        for dimension, metric, unit, chart in product(
            DIMENSIONS, METRICS, ("tumors", "persons"), CHARTS
        ):
            params = {
                "dimension": dimension,
                "metric": metric,
                "unit": unit,
                "chart": chart,
                "format": "png",
            }
            form = ExplorerForm(
                params,
                options=options,
                dimensions=DIMENSIONS,
                charts=CHARTS,
                metrics=METRICS,
            )
            if not form.is_valid():
                continue
            page = self.client.get(
                "/consulta/", {key: value for key, value in params.items() if key != "format"}
            )
            if page.context["errors"] or not page.context["table"]:
                continue
            response = self.client.get("/consulta/", params)
            successful += 1
            if successful == 21:
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response["Retry-After"], "60")
                break
            self.assertEqual(response.status_code, 200)
        self.assertEqual(successful, 21)

    def test_all_twelve_graph_types_render_compatible_data(self):
        self.delivery(publish=True)
        for kind in [
            "bar",
            "column",
            "ranking",
            "line",
            "grouped",
            "stacked",
            "percent",
            "pie",
            "doughnut",
            "scatter",
            "strip",
            "swarm",
        ]:
            data = {
                "chart": kind,
                "dimension": (
                    "period"
                    if kind == "line"
                    else "sex" if kind in {"pie", "doughnut"}
                    else "age_group" if kind in {"scatter", "strip", "swarm"}
                    else "site"
                ),
            }
            r = self.client.get("/consulta/", data)
            with self.subTest(kind=kind):
                self.assertFalse(r.context["form"].errors)
                self.assertTrue(r.context["table"])
                self.assertEqual(r.context["chart_payload"]["type"], kind)

    def test_all_export_formats_signatures_metadata_and_no_private_values(self):
        self.delivery(publish=True)
        for fmt, signature in [
            ("csv", b"\xef\xbb\xbf"),
            ("xlsx", b"PK"),
            ("png", b"\x89PNG"),
            ("svg", b"<?xml"),
            ("pdf", b"%PDF"),
        ]:
            with self.subTest(fmt=fmt):
                r = self.client.get("/consulta/", {"year": "2024", "format": fmt})
                self.assertEqual(r.status_code, 200)
                self.assertTrue(r.content.startswith(signature))
                self.assertIn(fmt, r["Content-Disposition"])
                self.assertEqual(r["Cache-Control"], "no-store")
        r = self.client.get("/consulta/", {"year": "2024", "format": "csv"})
        self.assertIn("2024", r.content.decode("utf-8-sig"))
        self.assertIn("Datos sintéticos", r.content.decode("utf-8-sig"))

    def test_every_graph_and_export_format_preserves_selection_and_values(self):
        import csv
        import xml.etree.ElementTree as ET
        from openpyxl import load_workbook
        from PIL import Image

        self.delivery(publish=True)
        charts = [
            ("bar", "site"),
            ("column", "site"),
            ("ranking", "site"),
            ("line", "period"),
            ("grouped", "site"),
            ("stacked", "site"),
            ("percent", "site"),
            ("pie", "sex"),
            ("doughnut", "sex"),
            ("scatter", "age_group"),
            ("strip", "age_group"),
            ("swarm", "age_group"),
        ]
        signatures = {
            "csv": b"\xef\xbb\xbf",
            "xlsx": b"PK",
            "png": b"\x89PNG",
            "svg": b"<?xml",
            "pdf": b"%PDF",
        }
        for chart, dimension in charts:
            query = {"chart": chart, "dimension": dimension}
            if chart != "line":
                query["year"] = "2024"
            page = self.client.get("/consulta/", query)
            payload = page.context["chart_payload"]
            self.assertIn("Año de incidencia:", payload["filter_summary"])
            self.assertIn("Provincia de residencia:", payload["filter_summary"])
            self.assertTrue(payload["axis_unit"])
            if chart == "scatter":
                self.assertEqual(
                    payload["datasets"][0]["data"],
                    [
                        {"x": row["tumors"], "y": row["persons"], "category": row["label"]}
                        for row in page.context["table"]
                    ],
                )
            elif chart in {"strip", "swarm"}:
                self.assertEqual(
                    [point["x"] for point in payload["datasets"][0]["data"]],
                    [row["value"] for row in page.context["table"]],
                )
                self.assertEqual(
                    [point["category"] for point in payload["datasets"][0]["data"]],
                    [row["label"] for row in page.context["table"]],
                )
            elif len(payload["datasets"]) == 1:
                self.assertEqual(
                    payload["datasets"][0]["data"],
                    [row["value"] for row in page.context["table"]],
                )
            else:
                for index, row in enumerate(page.context["table"]):
                    self.assertEqual(
                        [dataset["data"][index] for dataset in payload["datasets"]],
                        [series["value"] for series in row["series"]],
                    )

            def assert_exported_rows(actual_rows):
                expected_rows = []
                for row in page.context["table"]:
                    expected = [
                        row[key]
                        for key in (
                            "label", "tumors", "persons", "population",
                            "relative_frequency", "crude_rate", "adjusted_rate",
                        )
                    ]
                    if chart == "ranking":
                        expected.insert(0, row["rank"])
                    if len(payload["datasets"]) > 1:
                        expected.extend(series["value"] for series in row["series"])
                    expected_rows.append(expected)
                self.assertEqual(len(actual_rows), len(expected_rows))
                for actual, expected in zip(actual_rows, expected_rows):
                    if chart == "ranking":
                        self.assertEqual(int(actual[0]), expected[0])
                        self.assertEqual(actual[1], expected[1])
                        actual_values, expected_values = actual[2:], expected[2:]
                    else:
                        self.assertEqual(actual[0], expected[0])
                        actual_values, expected_values = actual[1:], expected[1:]
                    for actual_value, expected_value in zip(actual_values, expected_values):
                        if expected_value is None:
                            self.assertIn(actual_value, (None, ""))
                        else:
                            self.assertAlmostEqual(float(actual_value), float(expected_value))

            for fmt, signature in signatures.items():
                with self.subTest(chart=chart, fmt=fmt):
                    cache.clear()
                    response = self.client.get("/consulta/", {**query, "format": fmt})
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.content.startswith(signature))
                    if fmt == "csv":
                        text = response.content.decode("utf-8-sig")
                        self.assertIn("Contexto de la consulta", text)
                        self.assertIn("Año de incidencia", text)
                        self.assertIn("2024", text)
                        self.assertIn("Categoría", text)
                        rows = list(csv.reader(io.StringIO(text)))
                        header_index = next(i for i, row in enumerate(rows) if "Categoría" in row)
                        assert_exported_rows(rows[header_index + 1 :])
                    elif fmt == "xlsx":
                        sheet = load_workbook(io.BytesIO(response.content), data_only=True).active
                        self.assertEqual(sheet.cell(1, 1).value, "Contexto de la consulta")
                        self.assertIn("Año de incidencia", [sheet.cell(row, 1).value for row in range(2, 13)])
                        header_row = next(
                            row_index
                            for row_index, row in enumerate(
                                sheet.iter_rows(values_only=True), start=1
                            )
                            if "Categoría" in row
                        )
                        assert_exported_rows(
                            [
                                list(row)
                                for row in sheet.iter_rows(
                                    min_row=header_row + 1, values_only=True
                                )
                            ]
                        )
                    elif fmt == "png":
                        image = Image.open(io.BytesIO(response.content))
                        self.assertGreater(image.width, 1000)
                        self.assertGreater(image.height, 600)
                    elif fmt == "svg":
                        root = ET.fromstring(response.content)
                        self.assertTrue(root.tag.endswith("svg"))
                        if chart == "scatter":
                            self.assertIn("×", " ".join(root.itertext()))
                        expected_period = "Todos (2023–2024)" if chart == "line" else "2024"
                        self.assertIn(expected_period, " ".join(root.itertext()))

        for chart in ("pie", "doughnut"):
            with self.subTest(chart=chart, metric="share"):
                cache.clear()
                response = self.client.get(
                    "/consulta/", {"chart": chart, "dimension": "site", "metric": "share", "format": "svg"}
                )
                self.assertEqual(response.status_code, 200)
                text = " ".join(ET.fromstring(response.content).itertext())
                self.assertIn("Frecuencia relativa (%)", text)
                page = self.client.get("/consulta/", {"chart": chart, "dimension": "site", "metric": "share"})
                for row in page.context["table"]:
                    expected = f"{row['value']:.2f}".replace(".", ",") + "%"
                    self.assertIn(expected, text)

    def test_revocation_does_not_serve_cached_export(self):
        d = self.delivery(publish=True)
        self.assertEqual(
            self.client.get("/consulta/?format=csv")["Content-Type"],
            "text/csv; charset=utf-8",
        )
        self.apply_transition(d.pk, "revoke", self.root, "Retirar corte sintético de prueba.")
        r = self.client.get("/consulta/?format=csv")
        self.assertNotIn("attachment", r.get("Content-Disposition", ""))

    def test_downloaded_update_is_valid_and_adds_one_tumor(self):
        d = self.delivery(publish=True)
        self.client.force_login(self.root)
        r = self.client.get("/administracion/cortes/ejemplo/")
        updated = ingest(
            SimpleUploadedFile("update.csv", r.content),
            "Actualización sintética",
            self.root,
        )
        self.assertEqual(updated.row_count, d.row_count + 1)
        self.assertEqual(updated.person_count, d.person_count)

    def test_html_is_escaped_and_does_not_create_account(self):
        self.client.force_login(self.root)
        payload = "<script>alert('probe')</script>"
        r = self.client.post(
            "/administracion/usuarios/nuevo/", self.account_data(first_name=payload)
        )
        self.assertContains(r, "&lt;script&gt;")
        self.assertNotContains(r, payload)
        self.assertFalse(self.User.objects.filter(username="cuenta_nueva").exists())
        self.assertIn("script-src 'self'", r["Content-Security-Policy"])
        self.assertIn("object-src 'none'", r["Content-Security-Policy"])

    def test_login_throttle_cannot_be_bypassed_with_correct_credentials_after_limit(
        self,
    ):
        for _ in range(11):
            self.client.post(
                "/acceso/", {"username": self.reader.username, "password": "wrong"}
            )
        r = self.client.post(
            "/acceso/", {"username": self.reader.username, "password": PASSWORD}
        )
        self.assertTrue(r.context["form"].non_field_errors())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_control_characters_and_injected_identifiers_are_not_stored_as_valid_records(
        self,
    ):
        for field, value in [
            ("person_id", "SYN-P-<script>"),
            ("tumor_id", "SYN-T-../evil"),
            ("site_id", "<script>"),
        ]:
            rows = synthetic_rows()
            rows[0][field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    ingest(uploaded(rows=rows), "Revisión sintética", self.root)
                self.assertFalse(Delivery.objects.filter(status="validated").exists())

    def test_csrf_error_is_themed_and_does_not_echo_internal_reason(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/administracion/usuarios/nuevo/", {})
        self.assertEqual(r.status_code, 403)
        self.assertContains(r, "No se pudo enviar el formulario", status_code=403)
        self.assertNotContains(r, "CSRF cookie not set", status_code=403)

    def test_search_rejects_overlength_and_tags_without_widening_results(self):
        self.client.force_login(self.root)
        for query in ["a" * 101, "<script>alert(1)</script>"]:
            r = self.client.get("/administracion/usuarios/", {"q": query})
            self.assertIn("q", r.context["search_form"].errors)
            self.assertEqual(r.context["page"].paginator.count, 0)

    def test_password_change_invalidates_another_session(self):
        first = Client()
        second = Client()
        first.login(username=self.reader.username, password=PASSWORD)
        second.login(username=self.reader.username, password=PASSWORD)
        first.post(
            "/cuenta/contrasena/",
            {
                "old_password": PASSWORD,
                "new_password1": "Another-private-2026!",
                "new_password2": "Another-private-2026!",
            },
        )
        self.assertNotIn("_auth_user_id", second.get("/").wsgi_request.session)

    def test_privileged_actions_get_do_not_mutate(self):
        d = self.delivery()
        self.client.force_login(self.root)
        self.assertEqual(
            self.client.get(f"/administracion/cortes/{d.pk}/estado/").status_code, 405
        )
        d.refresh_from_db()
        self.assertEqual(d.status, "validated")
        self.assertFalse(Publication.objects.exists())

    def test_revoked_cut_with_saved_filters_shows_empty_state_not_field_errors(self):
        d = self.delivery(publish=True)
        self.client.get(
            "/consulta/?year=2024&dimension=age_group&metric=rate&format=csv"
        )
        self.apply_transition(d.pk, "revoke", self.root, "Retiro de revisión sintética.")
        r = self.client.get(
            "/consulta/?year=2024&dimension=age_group&metric=rate&format=csv"
        )
        self.assertContains(r, "No hay resultados")
        self.assertFalse(r.context["form"].errors)
        self.assertNotIn("attachment", r.get("Content-Disposition", ""))
