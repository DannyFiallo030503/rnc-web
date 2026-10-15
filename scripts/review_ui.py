"""Browser review with disposable accounts/database and an OS-assigned port.

Run with the project's Python after installing the optional playwright package.
Set RNC_REVIEW_BROWSER to a Chromium executable if Playwright's is unavailable.
"""

import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def run():
    from django.conf import settings

    with tempfile.TemporaryDirectory(prefix="rnc-ui-review-") as temporary:
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3",
                                         "NAME": str(Path(temporary) / "review.sqlite3")}}
        settings.DEBUG = True
        settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
        import django
        django.setup()
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application
        from django.contrib.staticfiles.handlers import StaticFilesHandler
        from django.db import connections
        from playwright.sync_api import sync_playwright

        call_command("migrate", interactive=False, stdout=io.StringIO(), verbosity=0)
        password = secrets.token_urlsafe(24)
        users = get_user_model().objects
        users.create_user("revision_lector", password=password)
        users.create_superuser("revision_superadmin", password=password)

        class QuietHandler(WSGIRequestHandler):
            def log_message(self, *args):
                pass

        server = make_server("127.0.0.1", 0, StaticFilesHandler(get_wsgi_application()),
                             handler_class=QuietHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        output = ROOT / "docs" / "revision-ui-2026-10-15"
        output.mkdir(parents=True, exist_ok=True)
        checks = []
        errors = []
        resource_failures = []
        captures = []
        success = False
        browser_version = None

        def check(condition, label):
            if not condition:
                raise AssertionError(label)
            checks.append(label)

        try:
            with sync_playwright() as playwright:
                launch = {"headless": True, "args": ["--no-sandbox"]}
                if os.environ.get("RNC_REVIEW_BROWSER"):
                    launch["executable_path"] = os.environ["RNC_REVIEW_BROWSER"]
                browser = playwright.chromium.launch(**launch)
                browser_version = browser.version
                context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                              reduced_motion="reduce")
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", lambda response: resource_failures.append(response.url)
                        if "/static/" in response.url and response.status >= 400 else None)
                page.on("requestfailed", lambda request: resource_failures.append(request.url)
                        if "/static/" in request.url else None)

                def capture(name):
                    page.screenshot(path=str(output / f"{name}.png"), full_page=True)
                    captures.append(f"{name}.png")

                def fits(label):
                    check(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"),
                          f"Sin desbordamiento horizontal: {label}")
                    rectangles = page.locator(".brand, .header-nav, .account-nav, .mobile-menu").evaluate_all(
                        "elements => elements.filter(e => e.getClientRects().length).map(e => {const r=e.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}})"
                    )
                    for index, a in enumerate(rectangles):
                        for b in rectangles[index + 1:]:
                            overlap = min(a["right"], b["right"]) - max(a["left"], b["left"])
                            vertical = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
                            check(overlap <= 1 or vertical <= 1, f"Cabecera sin solapamientos: {label}")

                def login(username):
                    page.goto(base + "/acceso/")
                    page.locator("#id_username").fill(username)
                    page.locator("#id_password").fill(password)
                    page.locator(".login-form button").click()
                    page.wait_for_load_state("networkidle")

                def active_button_is_clear(selector):
                    import re
                    colors = page.locator(selector).evaluate(
                        "e => {const s=getComputedStyle(e); return {fg:s.color,bg:s.backgroundColor,cursor:s.cursor}}"
                    )
                    def luminance(color):
                        rgb = [int(value) / 255 for value in re.findall(r"\d+", color)[:3]]
                        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
                        return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))
                    levels = sorted([luminance(colors["fg"]), luminance(colors["bg"])])
                    check((levels[1] + .05) / (levels[0] + .05) >= 4.5,
                          f"Contraste de texto del botón >= 4.5: {selector}")
                    check(colors["cursor"] == "pointer", f"Botón activo comunica interacción: {selector}")

                page.goto(base)
                fits("Inicio 1440")
                capture("inicio-escritorio")
                check(page.locator('a[href="/administracion/cortes/"]').count() == 0,
                      "Visitante no ve enlaces administrativos")
                page.locator(".brand").click()
                check(page.url.endswith("/acceso/"), "Marca pública abre login")
                active_button_is_clear(".login-form button")
                capture("login-escritorio")
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(base + "/acceso/")
                capture("login-movil")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/acceso/")
                page.locator("#id_username").fill("revision_lector")
                page.locator("#id_password").fill("incorrecta")
                page.locator(".login-form button").click()
                check(page.locator("#login-error").is_visible(), "Error de login visible")
                check(page.locator("#id_username").input_value() == "revision_lector",
                      "Login fallido conserva usuario")
                login("revision_lector")
                check(page.url == base + "/", "Cuenta normal vuelve al Inicio")
                response = page.goto(base + "/administracion/cortes/")
                check(response.status == 403, "Cuenta normal recibe 403 al abrir panel")
                check(page.get_by_role("heading", name="Acceso restringido").is_visible(),
                      "403 usa interfaz del portal")
                capture("acceso-restringido")
                login("revision_superadmin")
                check(page.url.endswith("/administracion/cortes/"), "Superadmin entra al panel")
                fits("Administración 1440")
                capture("administracion-escritorio")
                page.locator(".brand").click()
                check(page.url.endswith("/administracion/cortes/"), "Marca autenticada abre panel")
                page.locator(".sidebar-toggle").click()
                check(page.locator(".sidebar-toggle").get_attribute("aria-expanded") == "false",
                      "Sidebar comunica estado plegado")
                width = page.locator(".site-sidebar").bounding_box()["width"]
                check(width == 76, "Sidebar plegado mide 76 px")
                page.reload()
                check(page.locator(".workspace-shell.sidebar-collapsed").count() == 1,
                      "Sidebar conserva preferencia tras recarga")
                page.locator('.sidebar-pages a[href="/consulta-sintetica/"]').click()
                check(page.url.endswith("/consulta-sintetica/"), "Icono plegado permite navegar")
                capture("consulta-sidebar-plegado")
                active_button_is_clear(".synthetic-filters .apply-filters")
                initial_total = page.locator(".synthetic-summary article strong").first.inner_text()
                selected = page.locator("#filter-year").select_option(index=1)[0]
                page.locator("#filter-unit").select_option("persons")
                page.locator(".synthetic-filters .apply-filters").click()
                check(f"year={selected}" in page.url and "unit=persons" in page.url,
                      "Filtros se envían y conservan en URL")
                check(page.locator(".synthetic-summary article strong").first.inner_text() != initial_total,
                      "Filtros modifican resultados del backend")
                with page.expect_download() as download_event:
                    page.locator(".synthetic-export").click()
                download = download_event.value
                exported = Path(download.path()).read_text(encoding="utf-8-sig")
                check(download.suggested_filename.endswith(".csv") and "sintéticos" in exported,
                      "Descarga CSV funciona y conserva aviso de datos sintéticos")
                page.locator(".sidebar-toggle").focus()
                page.keyboard.press("Enter")
                check(page.locator(".sidebar-toggle").get_attribute("aria-expanded") == "true",
                      "Sidebar se puede ampliar con teclado")
                for width in (1440, 1024, 768, 760, 390, 320):
                    page.set_viewport_size({"width": width, "height": 900})
                    for route, name in (("/", "inicio"), ("/acceso/", "login"),
                                        ("/consulta-sintetica/", "consulta"),
                                        ("/administracion/cortes/", "administracion")):
                        page.goto(base + route)
                        fits(f"{name} {width}")
                        if width == 390 and name != "login":
                            capture(f"{name}-movil")
                page.set_viewport_size({"width": 390, "height": 844})
                page.goto(base + "/")
                page.locator(".mobile-menu summary").click()
                check(page.locator(".mobile-menu").get_attribute("open") is not None,
                      "Menú móvil abre")
                page.locator('.mobile-menu a[href="/administracion/cortes/"]').click()
                check(page.url.endswith("/administracion/cortes/"), "Menú móvil navega al panel")
                check(page.locator(".mobile-menu").get_attribute("open") is None,
                      "Menú móvil cierra al navegar")
                page.locator(".mobile-menu summary").click()
                page.keyboard.press("Escape")
                check(page.locator(".mobile-menu").get_attribute("open") is None,
                      "Escape cierra menú móvil")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/admin/auth/user/")
                check(page.get_by_role("heading", name="Seleccione usuario a modificar").count() > 0,
                      "Superadmin abre gestión de usuarios")
                capture("usuarios-escritorio")
                page.set_viewport_size({"width": 390, "height": 844})
                check(page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"),
                      "Gestión de usuarios sin desbordamiento en móvil")
                capture("usuarios-movil")
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.goto(base + "/administracion/cortes/")
                page.locator(".account-nav form button").click()
                response = page.goto(base + "/administracion/cortes/")
                check(page.url.startswith(base + "/acceso/"), "Cerrar sesión retira acceso")
                check(not errors, "Sin excepciones JavaScript")
                check(not resource_failures, "Recursos estáticos sin fallos de carga")
                success = True
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            connections.close_all()
            result = {"success": success, "browser": browser_version,
                      "checks": checks, "javascript_errors": errors,
                      "resource_failures": resource_failures, "screenshots": captures}
            (output / "resultados.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
        print(json.dumps({"passed": len(checks), "screenshots": len(captures), "output": str(output)},
                         ensure_ascii=False))


if __name__ == "__main__":
    run()
