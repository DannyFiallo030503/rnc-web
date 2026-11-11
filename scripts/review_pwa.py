"""Isolated PWA browser review with synthetic aggregates only.

Exercises the public-only URLconf, browser worker, IndexedDB, Cache API,
offline navigation, chart matrix, local exports, and query parity. The public
server is threaded and binds only to a loopback ephemeral port.
"""

import json
import csv
import io
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import unicodedata
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server
from socketserver import ThreadingMixIn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *_args):
        pass


def numeric(value):
    value = value.strip().replace("\u00a0", "").replace(" ", "")
    if value in {"", "—", "-"}:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    elif value.count(".") == 1 and len(value.rsplit(".", 1)[1]) == 3:
        # Spanish/French-style grouping (e.g. 720.000); localized decimals
        # in the tested UI always show two fraction digits.
        value = value.replace(".", "")
    return float(value)


def pdf_contains_glyphs(expected, extracted):
    """Check PDF text coverage without assuming extraction preserves shaping/order.

    Matplotlib's PDF text layer can expose shaped script glyphs in visual order
    or repeat Unicode sequences for a ligature. SVG is checked separately for
    the exact localized label; here require every letter and combining mark
    from that label to exist in the extractable PDF text layer.
    """
    expected_glyphs = {
        character
        for character in expected
        if unicodedata.category(character)[0] in {"L", "M"}
    }
    return expected_glyphs.issubset(set(extracted))


def compile_isolated_draft_catalogs(locale_root):
    """Compile the same validated, hash-pinned bundle used by opt-in preview."""
    from scripts.compile_translation_preview import compile_translation_preview

    manifest = compile_translation_preview(locale_root)
    return [Path(locale_root) / record["mo"] for record in manifest["catalogs"].values()]


def run():
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application
    from django.urls import clear_url_caches
    from playwright.sync_api import sync_playwright
    from config import settings_public
    from config.languages import PRIORITY_LANGUAGES
    from public_site.aggregate_release import _read_artifact, publish_release
    from public_site.testing import synthetic_rows
    from analytics.catalogs import resolve
    from django.utils.translation.trans_real import to_locale
    from gettext import translation as gettext_translation
    from pypdf import PdfReader

    results = []
    screenshots = []
    failures = []
    browser_version = None
    js_errors = []
    failed_responses = []
    worker_requests = []
    with tempfile.TemporaryDirectory(prefix="rnc-pwa-review-") as temporary:
        draft_locale_root = Path(temporary) / "draft-locales"
        compiled_drafts = compile_isolated_draft_catalogs(draft_locale_root)
        settings.LOCALE_PATHS = [draft_locale_root, ROOT / "locale"]
        settings.LANGUAGES = tuple((code, native) for code, _english, native, _active in PRIORITY_LANGUAGES)
        settings.TRANSLATION_PREVIEW_ENABLED = True
        settings.DRAFT_TRANSLATION_LOCALES = tuple(
            code for code, _english, _native, active in PRIORITY_LANGUAGES if not active
        )
        from django.utils.translation import trans_real
        trans_real.reset_cache(setting="LANGUAGES")
        settings.DEBUG = True
        settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
        settings.ROOT_URLCONF = "config.urls_public"
        settings.DEPLOYMENT_ROLE = "public"
        settings.TEMPLATES = settings_public.TEMPLATES
        settings.MIDDLEWARE = settings_public.MIDDLEWARE
        settings.PUBLIC_RELEASE_ROOT = Path(temporary) / "public-releases"
        settings.PRIVATE_STORAGE_ROOT = None
        settings.EMAIL_FILE_PATH = None
        _read_artifact.cache_clear()
        release = SimpleNamespace(
            pk=uuid4(),
            title="Corte sintético para revisión PWA",
            published_at=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
            report={"source": "fixture sintética de pruebas"},
        )
        rows = []
        for row in synthetic_rows(extra=2):
            rows.append({
                **row,
                "territory": resolve("territory_id", row["territory_id"])["name"],
                "sex": resolve("sex_id", row["sex_id"])["name"],
                "age_group": resolve("age_group_id", row["age_group_id"])["name"],
                "site": resolve("site_id", row["site_id"])["name"],
            })
        publish_release(release, rows)
        _read_artifact.cache_clear()
        clear_url_caches()

        application = StaticFilesHandler(get_wsgi_application())
        server = make_server(
            "127.0.0.1", 0, application,
            server_class=ThreadedServer,
            handler_class=QuietHandler,
        )
        base = f"http://127.0.0.1:{server.server_port}"
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def record(ok, label, evidence=None):
            item = {"ok": bool(ok), "check": label}
            if evidence is not None:
                item["evidence"] = evidence
            results.append(item)
            if not ok:
                failures.append(label)

        browser = None
        context = None
        page = None
        try:
            with sync_playwright() as playwright:
                launch = {"headless": True}
                if os.environ.get("RNC_REVIEW_BROWSER"):
                    launch["executable_path"] = os.environ["RNC_REVIEW_BROWSER"]
                browser = playwright.chromium.launch(**launch)
                browser_version = browser.version
                context = browser.new_context(
                    viewport={"width": 1365, "height": 900},
                    locale="es-CU",
                    reduced_motion="reduce",
                    service_workers="allow",
                    accept_downloads=True,
                )
                page = context.new_page()
                page.on("pageerror", lambda error: js_errors.append(str(error)))
                page.on("request", lambda request: worker_requests.append(request.url))
                page.on("response", lambda response: failed_responses.append({"status": response.status, "url": response.url}) if response.status >= 500 and not response.from_service_worker else None)

                response = page.goto(base + "/", wait_until="networkidle")
                record(response.status == 200, "PWA: inicio público responde 200")
                sidebar_toggle = page.locator(".sidebar-toggle")
                page.wait_for_function("!document.querySelector('.sidebar-toggle').hidden")
                record(sidebar_toggle.get_attribute("aria-label") == "Plegar barra lateral", "ARIA de barra lateral inicia traducida al español")
                sidebar_toggle.click()
                record(sidebar_toggle.get_attribute("aria-label") == "Ampliar barra lateral" and sidebar_toggle.get_attribute("title") == "Ampliar barra lateral", "ARIA y title anuncian expandir barra en español")
                sidebar_toggle.click()
                manifest_url = page.locator('link[rel="manifest"]').get_attribute("href")
                record(manifest_url == "/static/pwa/manifest.webmanifest", "PWA: manifiesto enlazado desde perfil público", manifest_url)
                manifest_response = page.request.get(base + manifest_url)
                manifest = manifest_response.json()
                record(manifest_response.status == 200 and manifest["scope"] == "/" and manifest["start_url"] == "/", "PWA: manifiesto público cubre la experiencia pública")
                worker_response = page.request.get(base + "/service-worker.js")
                record(worker_response.status == 200 and worker_response.headers.get("service-worker-allowed") == "/", "PWA: worker disponible solo en URLconf pública y con scope permitido")
                page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller", timeout=10000)
                scope = page.evaluate("navigator.serviceWorker.controller.scriptURL")
                record(scope.endswith("/service-worker.js"), "PWA: página pública queda controlada por el worker")
                page.wait_for_function("async () => { for (const name of await caches.keys()) { const value=await (await (await caches.open(name)).match('/__rnc-language__'))?.text(); if(value==='es') return true; } return false; }")

                page.goto(base + "/consulta-offline/", wait_until="networkidle")
                page.wait_for_function("navigator.serviceWorker.controller !== null")
                page.locator("#save-package").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('guardada en este dispositivo')")
                saved_text = page.locator("#offline-release").inner_text()
                record("versión" in saved_text and "sintético" in page.locator("#offline-context").inner_text(), "Paquete sintético guardado en IndexedDB con corte y método visibles")

                query_request_start = len(worker_requests)
                page.locator("#run-local").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('calculada localmente')")
                default_summary = page.locator("#offline-summary").inner_text()
                default_local = page.locator("#offline-results tbody tr").evaluate_all("rows => rows.map(row => Array.from(row.cells, cell => cell.innerText.trim()))")
                requests_during_local_query = [url for url in worker_requests[query_request_start:] if "/consulta/" in url or "/paquete-offline.json" in url]
                record(not requests_during_local_query, "Consulta local no envía filtros ni solicita datos al servidor")
                record(len(default_local) == 2 and "cálculo local:" in default_summary, "Frecuencias, personas, denominador e indicador se presentan en tabla local", {"rows": default_local, "summary": default_summary})

                server_page = context.new_page()
                server_page.on("pageerror", lambda error: js_errors.append(str(error)))
                server_page.goto(base + "/consulta/?dimension=site&chart=bar&metric=count&unit=tumors", wait_until="networkidle")
                server_chart_locale = server_page.evaluate("""() => ({
                  language:document.documentElement.lang,
                  chart:Chart.getChart(document.querySelector('#result-chart'))?.options.locale
                })""")
                record(server_chart_locale["chart"] == server_chart_locale["language"], "Gráfico de servidor usa locale español", server_chart_locale)
                server_rows = server_page.locator(".result-table tbody tr").evaluate_all("rows => rows.map(row => Array.from(row.cells, cell => cell.innerText.trim()))")
                local_parity = []
                for local, remote in zip(default_local, server_rows):
                    # Local: category, tumors, persons, population, relative, crude, adjusted.
                    # Server: category, tumors, persons, population, relative, crude, adjusted.
                    local_parity.append(
                        local[0] == remote[0]
                        and all(
                            (numeric(local[i]) is None and numeric(remote[i]) is None)
                            or (numeric(local[i]) is not None and numeric(remote[i]) is not None and abs(numeric(local[i]) - numeric(remote[i])) < 0.011)
                            for i in range(1, 7)
                        )
                    )
                record(len(local_parity) == len(server_rows) and all(local_parity), "Paridad local/servidor: 7 columnas tabulares para consulta sintética", {"rows": len(local_parity)})
                multi_group = server_page.locator(".query-multi-field").first
                multi_group.locator("summary").click()
                multi_options = multi_group.locator(".query-multi-option input")
                multi_options.nth(0).locator("xpath=..").click()
                spanish_one = multi_group.locator("summary small").inner_text()
                multi_options.nth(1).locator("xpath=..").click()
                spanish_many = multi_group.locator("summary small").inner_text()
                record(spanish_one == "1 opción seleccionada" and spanish_many == "2 opciones seleccionadas", "Resumen de multiselección usa singular/plural español", {"one": spanish_one, "many": spanish_many})
                server_page.close()
                page.goto(base + "/consulta-offline/", wait_until="networkidle")

                for metric, unit in [("count", "tumors"), ("count", "persons"), ("share", "tumors"), ("rate", "tumors"), ("rate", "persons"), ("asr", "tumors"), ("asr", "persons")]:
                    page.locator("#chart-kind").select_option("bar")
                    page.locator("#dimension").select_option("site")
                    page.locator("#metric").select_option(metric)
                    page.locator("#unit").select_option(unit)
                    page.locator("#run-local").click()
                    page.wait_for_function("document.querySelector('#offline-status').textContent.includes('calculada localmente')")
                    local_rows = page.locator("#offline-results tbody tr").evaluate_all("rows => rows.map(row => Array.from(row.cells, cell => cell.innerText.trim()))")
                    comparison = context.new_page()
                    comparison.goto(base + f"/consulta/?dimension=site&chart=bar&metric={metric}&unit={unit}", wait_until="networkidle")
                    remote_rows = comparison.locator(".result-table tbody tr").evaluate_all("rows => rows.map(row => Array.from(row.cells, cell => cell.innerText.trim()))")
                    remote_by_category = {row[0]: row for row in remote_rows}
                    matches = []
                    for local in local_rows:
                        remote = remote_by_category.get(local[0])
                        matches.append(remote is not None and all(
                            (numeric(local[i]) is None and numeric(remote[i]) is None)
                            or (numeric(local[i]) is not None and numeric(remote[i]) is not None and abs(numeric(local[i]) - numeric(remote[i])) < 0.011)
                            for i in range(1, 7)
                        ))
                    record(len(local_rows) == len(remote_rows) and len(matches) > 0 and all(matches), f"Paridad local/servidor: {metric}/{unit}", {"rows": len(matches), "local": local_rows, "server": remote_rows})
                    comparison.close()
                page.goto(base + "/consulta-offline/", wait_until="networkidle")

                chart_cases = [
                    ("bar", "site", "count", "tumors"),
                    ("ranking", "site", "share", "tumors"),
                    ("scatter", "age_group", "count", "tumors"),
                    ("strip", "age_group", "rate", "tumors"),
                    ("swarm", "age_group", "rate", "tumors"),
                    ("column", "site", "count", "tumors"),
                    ("line", "period", "count", "tumors"),
                    ("grouped", "site", "count", "tumors"),
                    ("stacked", "site", "count", "tumors"),
                    ("percent", "site", "count", "tumors"),
                    ("pie", "sex", "share", "tumors"),
                    ("doughnut", "sex", "count", "tumors"),
                ]
                for chart, dimension, metric, unit in chart_cases:
                    page.locator("#chart-kind").select_option(chart)
                    page.locator("#dimension").select_option(dimension)
                    page.locator("#metric").select_option(metric)
                    page.locator("#unit").select_option(unit)
                    page.locator("#run-local").click()
                    page.wait_for_function("!document.querySelector('#offline-status').textContent.startsWith('Calculando')")
                    status_text = page.locator("#offline-status").inner_text()
                    chart_state = page.evaluate("""() => {
                      const chart=Chart.getChart(document.getElementById('offline-chart'));
                      return chart ? {type:chart.config.type,rows:document.querySelectorAll('#offline-results tbody tr').length,datasets:chart.data.datasets.length} : null;
                    }""")
                    selected_state = page.evaluate("""() => ({chart:document.querySelector('#chart-kind').value,dimension:document.querySelector('#dimension').value,metric:document.querySelector('#metric').value,unit:document.querySelector('#unit').value})""")
                    record("calculada localmente" in status_text and chart_state is not None and chart_state["rows"] > 0 and chart_state["datasets"] > 0 and selected_state == {"chart": chart, "dimension": dimension, "metric": metric, "unit": unit}, f"Gráfico local {chart}: tabla y serie para la selección solicitada", {"selection": selected_state, "chart": chart_state})
                    screenshots.append({"chart": chart, "data": chart_state})

                page.locator("#chart-kind").select_option("bar")
                page.locator("#dimension").select_option("age_group")
                page.locator("#metric").select_option("count")
                page.locator("#run-local").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('calculada localmente')")
                record(page.locator("#offline-results tbody tr").count() == 10 and page.locator("#table-pagination").is_visible(), "Tabla local pagina a 10 filas por defecto")
                page.locator("#next-page").click()
                record(page.locator("#offline-results tbody tr").count() == 8 and "Página 2 de 2" in page.locator("#page-indicator").inner_text(), "Paginación local conserva las 18 categorías")
                page.locator("#previous-page").click()
                page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
                record(page.locator("#offline-results tbody tr").count() == 18, "Impresión local prepara todas las categorías para PDF")
                page.evaluate("window.dispatchEvent(new Event('afterprint'))")
                pdf_bytes = page.pdf(print_background=True)
                record(pdf_bytes.startswith(b"%PDF-"), "Impresión del navegador genera un PDF válido")

                with page.expect_download() as csv_download:
                    page.locator("#export-csv").click()
                csv_path = Path(csv_download.value.path())
                csv_bytes = csv_path.read_bytes()
                record(csv_bytes.startswith(b"\xef\xbb\xbf") and b"Datos sint\xc3\xa9ticos" in csv_bytes and b"SYN-P-" not in csv_bytes, "Exportación CSV local contiene procedencia y no incluye identificadores")
                with page.expect_download() as png_download:
                    page.locator("#export-png").click()
                png_bytes = Path(png_download.value.path()).read_bytes()
                record(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"), "Exportación PNG local tiene firma válida")

                page.locator("#year").select_option(["2023", "2024"])
                page.locator("#chart-kind").select_option("bar")
                page.locator("#dimension").select_option("site")
                page.locator("#unit").select_option("persons")
                unit_state = page.evaluate("""() => ({
                  selectedYears:Array.from(document.querySelector('#year').selectedOptions, option=>option.value),
                  personsDisabled:document.querySelector('#unit option[value=persons]').disabled,
                  unitValue:document.querySelector('#unit').value,
                  hint:document.querySelector('#filter-help').textContent
                })""")
                record(unit_state["personsDisabled"], "Unidad personas se bloquea para filtros con varios valores", unit_state)
                page.locator("#unit").select_option("tumors")
                page.locator("#run-local").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('calculada localmente')")
                record("no disponible" in page.locator("#offline-summary").inner_text(), "Selección múltiple calcula tumores e informa que no deduplica personas")

                cache_contents = page.evaluate("""async () => {
                  const entries=[];
                  for (const name of await caches.keys()) {
                    const cache=await caches.open(name);
                    for (const request of await cache.keys()) { const url=new URL(request.url); entries.push(url.pathname+url.search); }
                  }
                  return entries;
                }""")
                record("/paquete-offline.json" not in cache_contents and not any(path.startswith("/consulta/") for path in cache_contents), "Cache API excluye paquete y consultas del servidor", {"cached_assets": len(cache_contents)})
                record("/jsi18n/?lang=es" in cache_contents, "PWA: catálogo JavaScript español queda persistido para uso offline")
                record("/__rnc-language__" in cache_contents, "PWA: idioma activo queda persistido para el fallback offline")
                record(not any(path.startswith(("/admin/", "/acceso/", "/administracion/", "/cuenta/")) for path in cache_contents), "Cache API no contiene rutas administrativas")

                context.set_offline(True)
                page.goto(base + "/consulta/", wait_until="domcontentloaded")
                record(page.get_by_role("heading", name="Consulta sin conexión").is_visible(), "Navegación pública cae al shell local cuando el servidor no responde")
                page.locator("#run-local").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('calculada localmente')")
                offline_local_rows = page.locator("#offline-results tbody tr").count()
                record(offline_local_rows > 0, "Filtro y gráfico siguen funcionando sin conexión")
                page.goto(base + "/", wait_until="domcontentloaded")
                record(page.get_by_role("heading", name="Consulta sin conexión").is_visible(), "Inicio público usa la experiencia local al fallar el servidor")
                admin_failed = False
                try:
                    page.goto(base + "/administracion/cortes/", wait_until="domcontentloaded", timeout=2500)
                except Exception:
                    admin_failed = True
                record(admin_failed, "Ruta administrativa no se sirve desde shell/cache offline")
                context.set_offline(False)
                page.goto(base + "/consulta-offline/", wait_until="networkidle")
                page.locator("#clear-package").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('eliminó el paquete local')")
                package_removed = page.evaluate("""async () => {
                  const db=await new Promise((resolve,reject)=>{const request=indexedDB.open('rnc-public-offline',2);request.onsuccess=()=>resolve(request.result);request.onerror=()=>reject(request.error);});
                  return await new Promise((resolve,reject)=>{const request=db.transaction('package').objectStore('package').get('active');request.onsuccess=()=>resolve(request.result === undefined);request.onerror=()=>reject(request.error);});
                }""")
                record(package_removed and "No hay paquete guardado." in page.locator("#offline-release").inner_text(), "La persona puede borrar el paquete local")
                page.goto(base + "/")
                page.locator("#site-language").select_option("en")
                page.locator(".language-picker button").click()
                page.wait_for_function("document.documentElement.lang === 'en'")
                page.wait_for_function("async () => { for (const name of await caches.keys()) { const value=await (await (await caches.open(name)).match('/__rnc-language__'))?.text(); if(value==='en') return true; } return false; }")
                sidebar_toggle = page.locator(".sidebar-toggle")
                record(sidebar_toggle.get_attribute("aria-label") == "Collapse sidebar", "ARIA de barra lateral inicia traducida al inglés")
                sidebar_toggle.click()
                record(sidebar_toggle.get_attribute("aria-label") == "Expand sidebar" and sidebar_toggle.get_attribute("title") == "Expand sidebar", "ARIA y title anuncian expandir barra en inglés")
                page.goto(base + "/consulta/", wait_until="networkidle")
                english_chart_locale = page.evaluate("""() => ({
                  language:document.documentElement.lang,
                  chart:Chart.getChart(document.querySelector('#result-chart'))?.options.locale
                })""")
                record(english_chart_locale == {"language": "en", "chart": "en"}, "Gráfico de servidor usa locale inglés", english_chart_locale)
                multi_group = page.locator(".query-multi-field").first
                multi_group.locator("summary").click()
                multi_options = multi_group.locator(".query-multi-option input")
                multi_options.nth(0).locator("xpath=..").click()
                english_one = multi_group.locator("summary small").inner_text()
                multi_options.nth(1).locator("xpath=..").click()
                english_many = multi_group.locator("summary small").inner_text()
                record(english_one == "1 option selected" and english_many == "2 options selected", "Multiselection count uses English singular/plural", {"one": english_one, "many": english_many})
                page.goto(base + "/consulta-offline/", wait_until="networkidle")
                record(page.get_by_role("heading", name="Offline consultation").is_visible(), "PWA: interfaz offline estática en inglés")
                record(page.locator("#offline-release").inner_text() == "No package saved.", "PWA: estado inicial del paquete en inglés")
                page.locator("#run-local").click()
                record("First save the synthetic release" in page.locator("#offline-status").inner_text(), "PWA: estado dinámico sin paquete usa el catálogo inglés")
                page.locator("#save-package").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('saved on this device')")
                page.select_option("#dimension", "site")
                page.select_option("#chart-kind", "bar")
                page.select_option("#metric", "count")
                page.select_option("#unit", "tumors")
                page.locator("#site").select_option("Mama")
                page.locator("#run-local").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.includes('calculated on this device')")
                category_state = page.evaluate("""() => ({
                  option:document.querySelector('#site option[value="Mama"]').textContent,
                  row:document.querySelector('#offline-results tbody th[scope="row"]')?.textContent,
                  chart:Chart.getChart(document.querySelector('#offline-chart'))?.data.labels[0]
                })""")
                record(category_state == {"option": "Breast", "row": "Breast", "chart": "Breast"}, "PWA: filtros, tabla y gráfico traducen categorías dinámicas y conservan claves estables", category_state)
                page.evaluate("""() => {
                  const years=document.querySelector('#year');
                  [...years.options].forEach(option=>option.selected=['2023','2024'].includes(option.value));
                  document.querySelector('#unit').value='persons';
                }""")
                page.locator("#run-local").click()
                page.wait_for_function("document.querySelector('#offline-status').textContent.startsWith('Incompatible selection:')")
                record("multiple selections" in page.locator("#offline-status").inner_text(), "PWA: mensaje de validación del trabajador local en inglés")

                # Exercise the inactive draft catalogs through disposable MO files.
                # Source catalogs remain fuzzy and are never added to the app build.
                draft_results = []
                for locale, _english_name, _native_name, active in PRIORITY_LANGUAGES:
                    if active:
                        continue
                    context.set_offline(False)
                    page.goto(base + "/", wait_until="networkidle")
                    page.locator("#site-language").select_option(locale)
                    page.locator(".language-picker button").click()
                    page.wait_for_function("expected => document.documentElement.lang === expected", arg=locale)
                    page.wait_for_function(
                        """async expected => {
                          for (const name of await caches.keys()) {
                            const value = await (await (await caches.open(name))
                              .match('/__rnc-language__'))?.text();
                            if (value === expected) return true;
                          }
                          return false;
                        }""",
                        arg=locale,
                    )
                    from django.utils import translation
                    from django.utils.translation import gettext as _
                    with translation.override(locale):
                        preview_title = str(_("Vista previa de traducción automática"))
                        preview_warning = str(_(
                            "Este idioma usa un borrador no revisado ni aprobado. "
                            "No lo use para interpretar estadísticas de cáncer."
                        ))
                        preview_suffix = str(_("borrador de vista previa"))
                    preview_banner = page.locator(".translation-preview-banner").inner_text()
                    preview_option = page.locator(
                        f"#site-language option[value='{locale}']"
                    ).inner_text()
                    record(
                        preview_title in preview_banner
                        and preview_warning in preview_banner
                        and preview_suffix in preview_option,
                        f"Borrador {locale}: aviso y etiqueta de vista previa localizados",
                        {"heading_present": preview_title in preview_banner,
                         "warning_present": preview_warning in preview_banner,
                         "selector_suffix_present": preview_suffix in preview_option},
                    )
                    language_sync = page.evaluate("""async () => {
                      const cacheLanguages={};
                      const cacheRevisions={};
                      for(const name of await caches.keys()) {
                        const cache=await caches.open(name);
                        cacheLanguages[name]=await (await cache.match('/__rnc-language__'))?.text() || null;
                        cacheRevisions[name]=await (await cache.match('/__rnc-language-revision__'))?.text() || null;
                      }
                      return {page:document.documentElement.lang,caches:cacheLanguages,revisions:cacheRevisions,preference:localStorage.getItem('rnc-language-preference')};
                    }""")
                    language_cookies = [
                        cookie["value"] for cookie in context.cookies(base)
                        if cookie["name"] == "rnc_language"
                    ]
                    record(
                        language_sync["page"] == locale
                        and language_sync["caches"].get("rnc-public-shell-v8") == locale
                        and language_cookies == [locale],
                        f"Borrador {locale}: selector sincroniza cookie y worker offline",
                        {**language_sync, "language_cookie": language_cookies},
                    )
                    from django.utils import translation
                    from django.utils.translation import gettext as _
                    from django.utils.formats import number_format
                    from django.core.cache import cache
                    from openpyxl import load_workbook

                    with translation.override(locale):
                        expected_context = str(_("Contexto de la consulta"))
                        expected_tumors = str(_("Tumores (frecuencia absoluta)"))
                        expected_sheet = str(_("Consulta"))
                    server_csv = page.evaluate("""async () => {
                      const response = await fetch('/consulta/?format=csv', {credentials:'same-origin'});
                      return {status:response.status, language:response.headers.get('Content-Language'), text:await response.text()};
                    }""")
                    server_rows_from_csv = list(csv.reader(io.StringIO(server_csv["text"].lstrip("\ufeff"))))
                    first_data_row = next(
                        row for row in server_rows_from_csv
                        if len(row) >= 7 and row[1].isdigit()
                    )
                    with translation.override(locale):
                        expected_server_population = number_format(
                            float(first_data_row[3]), decimal_pos=0,
                            use_l10n=True, force_grouping=True,
                        )
                    record(
                        server_csv["status"] == 200
                        and expected_context in server_csv["text"]
                        and expected_tumors in server_csv["text"],
                        f"Borrador {locale}: CSV del servidor traduce contexto y cabeceras",
                        {"status": server_csv["status"], "content_language": server_csv["language"],
                         "expected_context": expected_context, "expected_header": expected_tumors,
                         "csv_preview": server_csv["text"][:240],
                         "context_present": expected_context in server_csv["text"],
                         "header_present": expected_tumors in server_csv["text"]},
                    )
                    server_table = page.evaluate("""async () => {
                      const response = await fetch('/consulta/', {credentials:'same-origin'});
                      const html = await response.text();
                      const documentCopy = new DOMParser().parseFromString(html, 'text/html');
                      return {
                        status:response.status,
                        language:response.headers.get('Content-Language'),
                        population:documentCopy.querySelector('.result-table tbody tr')?.cells[3]?.textContent.trim()
                      };
                    }""")
                    record(
                        server_table["status"] == 200
                        and server_table["language"] == locale
                        and server_table["population"] == expected_server_population,
                        f"Borrador {locale}: tabla del servidor agrupa millares según el locale",
                        {**server_table, "expected_population": expected_server_population},
                    )
                    xlsx_b64 = page.evaluate("""async () => {
                      const response = await fetch('/consulta/?format=xlsx', {credentials:'same-origin'});
                      const bytes = new Uint8Array(await response.arrayBuffer());
                      let binary='';
                      for(let offset=0;offset<bytes.length;offset+=0x8000)
                        binary+=String.fromCharCode(...bytes.subarray(offset,offset+0x8000));
                      return {status:response.status,content:btoa(binary)};
                    }""")
                    import base64
                    from io import BytesIO

                    workbook = load_workbook(BytesIO(base64.b64decode(xlsx_b64["content"])), read_only=True)
                    cells = [cell for row in workbook.active.iter_rows(values_only=True) for cell in row]
                    xlsx_ok = (
                        xlsx_b64["status"] == 200
                        and workbook.active.title == expected_sheet
                        and expected_context in cells
                        and expected_tumors in cells
                    )
                    workbook.close()
                    record(
                        xlsx_ok,
                        f"Borrador {locale}: XLSX del servidor traduce hoja, contexto y cabeceras",
                        {"status": xlsx_b64["status"], "sheet": workbook.active.title,
                         "expected_sheet": expected_sheet,
                         "context_present": expected_context in cells,
                         "header_present": expected_tumors in cells},
                    )
                    # Image and PDF renderers also carry locale-sensitive text.
                    # Validate these on the same disposable draft catalogs as CSV/XLSX.
                    with translation.override(locale):
                        expected_dimension = str(_("Grupo de localización"))
                    # The browser sweep exercises independent locale scenarios;
                    # reset this disposable review server's per-IP render throttle
                    # so each locale can validate its three export formats.
                    cache.clear()
                    svg_export = page.evaluate("""async () => {
                      const response = await fetch('/consulta/?format=svg', {credentials:'same-origin'});
                      return {status:response.status,type:response.headers.get('Content-Type'),text:await response.text()};
                    }""")
                    record(
                        svg_export["status"] == 200
                        and "<svg" in svg_export["text"]
                        and expected_dimension in svg_export["text"],
                        f"Borrador {locale}: SVG contiene etiquetas del gráfico localizadas",
                        {"status": svg_export["status"], "type": svg_export["type"],
                         "dimension_present": expected_dimension in svg_export["text"]},
                    )
                    raster_exports = page.evaluate("""async () => {
                      const result={};
                      for(const format of ['png','pdf']) {
                        const response=await fetch(`/consulta/?format=${format}`, {credentials:'same-origin'});
                        const bytes=new Uint8Array(await response.arrayBuffer());
                        let binary='';
                        for(let offset=0;offset<bytes.length;offset+=0x8000)
                          binary+=String.fromCharCode(...bytes.subarray(offset,offset+0x8000));
                        result[format]={status:response.status,type:response.headers.get('Content-Type'),content:btoa(binary)};
                      }
                      return result;
                    }""")
                    png_bytes = base64.b64decode(raster_exports["png"]["content"])
                    pdf_bytes = base64.b64decode(raster_exports["pdf"]["content"])
                    pdf_text = "\n".join(
                        page.extract_text() or ""
                        for page in PdfReader(io.BytesIO(pdf_bytes)).pages
                    )
                    record(
                        raster_exports["png"]["status"] == 200
                        and raster_exports["png"]["type"].startswith("image/png")
                        and png_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
                        f"Borrador {locale}: PNG del servidor válido",
                        {"status": raster_exports["png"]["status"], "bytes": len(png_bytes)},
                    )
                    record(
                        raster_exports["pdf"]["status"] == 200
                        and raster_exports["pdf"]["type"] == "application/pdf"
                        and pdf_bytes.startswith(b"%PDF-")
                        and pdf_contains_glyphs(expected_dimension, pdf_text),
                        f"Borrador {locale}: PDF válido con glifos de etiquetas localizadas",
                        {"status": raster_exports["pdf"]["status"], "bytes": len(pdf_bytes),
                         "glyphs_present": pdf_contains_glyphs(expected_dimension, pdf_text)},
                    )
                    expected_dir = "rtl" if locale in {"ar", "ur"} else "ltr"
                    direction = page.locator("html").get_attribute("dir")
                    js_strings = page.evaluate("""() => ({
                      women:gettext('Mujeres'),
                      frequency:gettext('Frecuencia absoluta'),
                      category:gettext('Mama')
                    })""")
                    nonempty_js = all(value.strip() for value in js_strings.values())
                    record(direction == expected_dir, f"Borrador {locale}: dirección {expected_dir}", direction)
                    record(nonempty_js, f"Borrador {locale}: catálogo JavaScript cargado", js_strings)
                    plural_catalog = gettext_translation(
                        "djangojs", localedir=str(draft_locale_root),
                        languages=[to_locale(locale)], fallback=True,
                    )
                    plural_counts = [0, 1, 2, 3, 5, 11, 21, 101]
                    expected_plural_forms = [
                        plural_catalog.ngettext(
                            "categoría con el mismo valor",
                            "categorías con los mismos valores",
                            count,
                        )
                        for count in plural_counts
                    ]
                    browser_plural_forms = page.evaluate("""counts => counts.map(count =>
                      ngettext('categoría con el mismo valor', 'categorías con los mismos valores', count))""", plural_counts)
                    record(
                        browser_plural_forms == expected_plural_forms,
                        f"Borrador {locale}: selección plural JavaScript coincide con GNU gettext",
                        {"counts": plural_counts, "browser": browser_plural_forms},
                    )
                    if expected_dir == "rtl":
                        page.set_viewport_size({"width": 390, "height": 844})
                        page.wait_for_function("() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))")
                        rtl_layout = page.evaluate("""() => ({
                          viewport:innerWidth,
                          document:document.documentElement.scrollWidth,
                          body:document.body.scrollWidth,
                          direction:document.documentElement.dir,
                          offenders:Array.from(document.body.querySelectorAll('*')).map(element=>({
                            node:element.tagName.toLowerCase(),
                            className:typeof element.className==='string'?element.className:'',
                            left:Math.round(element.getBoundingClientRect().left),
                            right:Math.round(element.getBoundingClientRect().right)
                          })).filter(item=>item.right>innerWidth+1||item.left < -1).slice(0,12)
                        })""")
                        rtl_layout["fits"] = rtl_layout["document"] <= rtl_layout["viewport"] and rtl_layout["body"] <= rtl_layout["viewport"]
                        record(rtl_layout["fits"], f"Borrador {locale}: PWA RTL cabe en viewport móvil de 390 px", rtl_layout)
                        page.screenshot(path=str(ROOT / "docs" / f"pwa-review-{locale}-390.png"), full_page=True)
                        page.set_viewport_size({"width": 1365, "height": 900})

                    page.goto(base + "/consulta-offline/", wait_until="networkidle")
                    page.wait_for_function("expected => document.documentElement.lang === expected", arg=locale)
                    page.wait_for_function("""async expected => {
                      for(const name of await caches.keys()) {
                        const value=await (await (await caches.open(name)).match('/__rnc-language__'))?.text();
                        if(value===expected) return true;
                      }
                      return false;
                    }""", arg=locale)
                    shell_cache_state = page.evaluate("""async () => {
                      const requests=[];
                      let saved=null, localized=null;
                      for(const name of await caches.keys()) {
                        const cache=await caches.open(name);
                        saved ||= await (await cache.match('/__rnc-language__'))?.text() || null;
                        localized ||= await (await cache.match('/consulta-offline/?__rnc_locale='+document.documentElement.lang))?.text().then(html=>html.match(/<html\\b[^>]*\\blang=["']([^"']+)/i)?.[1]) || null;
                        for(const request of await cache.keys()) if(new URL(request.url).pathname==='/consulta-offline/') requests.push(new URL(request.url).search);
                      }
                      return {lang:document.documentElement.lang,dir:document.documentElement.dir,saved,localized,requests};
                    }""")
                    page.locator("#save-package").click()
                    page.wait_for_function("!document.querySelector('#save-package').disabled && document.querySelector('#offline-status').textContent.length > 0")
                    package_date = page.evaluate("""() => ({
                      displayed:document.querySelector('#offline-release').textContent,
                      expected:new Intl.DateTimeFormat(document.documentElement.lang, {dateStyle:'medium',timeStyle:'short'}).format(new Date('2026-11-10T12:00:00+00:00'))
                    })""")
                    record(
                        package_date["expected"] in package_date["displayed"],
                        f"Borrador {locale}: fecha de publicación de PWA localizada",
                        package_date,
                    )
                    page.select_option("#dimension", "site")
                    page.select_option("#chart-kind", "bar")
                    page.select_option("#metric", "count")
                    page.select_option("#unit", "tumors")
                    page.locator("#site").select_option("Mama")
                    page.locator("#run-local").click()
                    page.wait_for_function("document.querySelectorAll('#offline-results tbody tr').length > 0 && Chart.getChart(document.querySelector('#offline-chart'))")
                    category_state = page.evaluate("""() => ({
                      key:document.querySelector('#site option:checked').value,
                      option:document.querySelector('#site option:checked').textContent,
                      row:document.querySelector('#offline-results tbody th[scope=row]')?.textContent,
                      chart:Chart.getChart(document.querySelector('#offline-chart'))?.data.labels[0],
                      expected:gettext('Mama')
                    })""")
                    translated_category = category_state["option"] == category_state["expected"] and category_state["row"] == category_state["expected"] and category_state["chart"] == category_state["expected"]
                    record(category_state["key"] == "Mama" and translated_category, f"Borrador {locale}: consulta local traduce filtros, tabla y gráfico conservando la clave", category_state)

                    with page.expect_download() as draft_csv_download:
                        page.locator("#export-csv").click()
                    draft_csv = Path(draft_csv_download.value.path()).read_bytes()
                    export_rows = list(csv.reader(io.StringIO(draft_csv.decode("utf-8-sig"))))
                    category_row = next(
                        row for row in export_rows
                        if len(row) >= 7 and row[0] == category_state["expected"]
                    )
                    record(
                        category_row[0] == category_state["expected"],
                        f"Borrador {locale}: CSV offline traduce categorías visibles",
                        {"category": category_row[0]},
                    )
                    number_state = page.evaluate("""values => {
                      const locale = document.documentElement.lang;
                      const integer = new Intl.NumberFormat(locale, {maximumFractionDigits:0});
                      const decimal = new Intl.NumberFormat(locale, {minimumFractionDigits:2,maximumFractionDigits:2});
                      const cells = document.querySelector('#offline-results tbody tr')?.children || [];
                      const chart = Chart.getChart(document.querySelector('#offline-chart'));
                      return {
                        locale,
                        population:cells[3]?.textContent,
                        expectedPopulation:integer.format(Number(values.population)),
                        frequency:cells[4]?.textContent,
                        expectedFrequency:decimal.format(Number(values.frequency)),
                        chartLocale:chart?.options.locale,
                      };
                    }""", {"population": category_row[3], "frequency": category_row[4]})
                    record(
                        number_state["population"] == number_state["expectedPopulation"]
                        and number_state["frequency"] == number_state["expectedFrequency"]
                        and number_state["chartLocale"] == locale,
                        f"Borrador {locale}: tabla y ejes usan agrupación/decimales del locale",
                        number_state,
                    )
                    csv_metadata_label = page.evaluate("gettext('Datos sintéticos')")
                    record(
                        bool(csv_metadata_label.strip())
                        and csv_metadata_label != "Datos sintéticos"
                        and csv_metadata_label.encode("utf-8") in draft_csv
                        and draft_csv.startswith(bytes.fromhex("efbbbf")),
                        f"Borrador {locale}: CSV local usa metadatos traducidos y UTF-8 BOM",
                        {"metadata_label_present": csv_metadata_label.encode("utf-8") in draft_csv,
                         "utf8_bom": draft_csv.startswith(bytes.fromhex("efbbbf"))},
                    )

                    context.set_offline(True)
                    page.goto(base + "/consulta/", wait_until="domcontentloaded")
                    shell_state = page.evaluate("""() => ({lang:document.documentElement.lang,dir:document.documentElement.dir})""")
                    record(shell_state == {"lang": locale, "dir": expected_dir}, f"Borrador {locale}: shell PWA sin conexión conserva idioma y dirección", {"offline": shell_state, "cache": shell_cache_state})
                    context.set_offline(False)
                    fallback_message = page.locator("html").get_attribute("data-offline-unavailable")
                    page.evaluate("""async locale => {
                      const key = new URL('/consulta-offline/?__rnc_locale=' + locale, location.origin).href;
                      for (const name of await caches.keys())
                        await (await caches.open(name)).delete(key);
                    }""", locale)
                    context.set_offline(True)
                    fallback_response = page.goto(base + "/consulta/", wait_until="domcontentloaded")
                    fallback_text = page.locator("body").inner_text()
                    record(
                        fallback_response.status == 503
                        and bool(fallback_message)
                        and fallback_text == fallback_message,
                        f"Borrador {locale}: fallback sin shell conserva el mensaje localizado",
                        {"status": fallback_response.status,
                         "message_matches": fallback_text == fallback_message},
                    )
                    context.set_offline(False)
                    page.goto(base + "/consulta-offline/", wait_until="networkidle")
                    draft_results.append({"locale": locale, "strings": js_strings, "category": category_state, "shell": shell_state})

                record(len(compiled_drafts) == 18 and all(path.is_relative_to(Path(temporary)) for path in compiled_drafts), "Catálogos de prueba compilados fuera del árbol del proyecto", len(compiled_drafts))
                record(not js_errors, "Sin excepciones JavaScript durante recorrido PWA", js_errors)
                record(not failed_responses, "Sin respuestas HTTP 5xx durante recorrido PWA", failed_responses)

                removed_shells = page.evaluate("""async () => {
                  let removed=0;
                  for(const name of await caches.keys()) {
                    const cache=await caches.open(name);
                    for(const request of await cache.keys()) {
                      if(new URL(request.url).pathname === '/consulta-offline/' && await cache.delete(request)) removed++;
                    }
                  }
                  return removed;
                }""")
                record(removed_shells > 0, "Preparación del caso: shell retirado de Cache API", {"removed": removed_shells})
                for locale, expected in [("en", "The offline query is not available on this device yet."), ("es", "La consulta local aún no está disponible en este dispositivo.")]:
                    context.set_offline(False)
                    page.goto(base + "/", wait_until="networkidle")
                    page.locator("#site-language").select_option(locale)
                    page.locator(".language-picker button").click()
                    page.wait_for_function("expected => document.documentElement.lang === expected", arg=locale)
                    page.wait_for_function("async expected => { for (const name of await caches.keys()) { const value=await (await (await caches.open(name)).match('/__rnc-language__'))?.text(); if(value===expected) return true; } return false; }", arg=locale)
                    page.wait_for_function("""async wanted => {
                      for(const name of await caches.keys()) {
                        const value=await (await (await caches.open(name)).match('/__rnc-offline-message__/?lang='+wanted.locale))?.text();
                        if(value===wanted.message) return true;
                      }
                      return false;
                    }""", arg={"locale": locale, "message": expected})
                    fallback_cache_state = page.evaluate("""async () => {
                      const state=[];
                      for(const name of await caches.keys()) {
                        const cache=await caches.open(name);
                        state.push({name,language:await (await cache.match('/__rnc-language__'))?.text(),message:await (await cache.match('/__rnc-offline-message__/?lang='+document.documentElement.lang))?.text()});
                      }
                      return state;
                    }""")
                    context.set_offline(True)
                    fallback = page.goto(base + "/consulta/", wait_until="domcontentloaded")
                    fallback_text = page.locator("body").inner_text()
                    record(fallback.status == 503 and expected in fallback_text, f"Fallback sin shell respeta el idioma activo ({locale})", {"status": fallback.status, "text": fallback_text, "cache": fallback_cache_state})
        except Exception as error:
            diagnostic = None
            if page:
                try:
                    diagnostic = page.evaluate("""async () => ({
                      controller:navigator.serviceWorker?.controller?.scriptURL || null,
                      registrations:await navigator.serviceWorker?.getRegistrations().then(items=>items.map(item=>({scope:item.scope,active:item.active?.state,waiting:item.waiting?.state,installing:item.installing?.state}))),
                      caches:await caches.keys()
                    })""")
                except Exception:
                    pass
            failures.append(f"{error}; estado PWA={diagnostic}")
            if page:
                try:
                    page.screenshot(path=str(ROOT / "docs" / "pwa-review-failure.png"), full_page=True)
                except Exception:
                    pass
        finally:
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    report = {
        "success": not failures and all(item["ok"] for item in results),
        "browser": browser_version,
        "profile": "config.settings_public URLconf with synthetic fixture and temporary release directory",
        "checks": results,
        "chart_cases": screenshots,
        "javascript_errors": js_errors,
        "http_5xx": failed_responses,
        "failures": failures,
    }
    output = ROOT / "docs" / "pwa-review.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"success": report["success"], "browser": browser_version, "checks": len(results), "failures": failures, "output": str(output)}, ensure_ascii=False))
    if not report["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
