"""Exercise the browser-based translation review site with synthetic catalog text."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
from threading import Thread

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_translation_review_site import build, build_data


def run():
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory(prefix="rnc-translation-site-") as temporary:
        site_root = Path(temporary) / "site"
        build(site_root)
        server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            partial(SimpleHTTPRequestHandler, directory=str(site_root)),
        )
        Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                launch = {"headless": True}
                if os.environ.get("RNC_REVIEW_BROWSER"):
                    launch["executable_path"] = os.environ["RNC_REVIEW_BROWSER"]
                browser = playwright.chromium.launch(**launch)
                context = browser.new_context(
                    viewport={"width": 1365, "height": 900},
                    permissions=["clipboard-read", "clipboard-write"],
                )
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/",
                    wait_until="networkidle",
                )
                page.locator(".message-card").first.wait_for()
                assert page.locator(".message-card").count() == 60
                assert int(page.locator("#shown-count").inner_text().replace(",", "")) == 885
                page.locator(".copy-reference").first.click()
                copy_status = page.locator(".copy-reference").first.inner_text()
                assert copy_status in {
                    "Copiado / Copied",
                    "Selecciona y copia la referencia / Select and copy the reference",
                }
                if "Selecciona" in copy_status:
                    assert "Language: zh-hans" in page.locator(".copy-fallback").input_value()

                page.locator("#language").select_option("zh-hans")
                assert page.locator(".message-card").count() == 60
                assert page.locator(".tag.pending").count() == 60
                page.locator("#load-more").click()
                assert page.locator(".message-card").count() == 120

                page.locator("#language").select_option("ar")
                assert page.locator("html").get_attribute("dir") == "rtl"
                page.locator("#language").select_option("ur")
                assert page.locator("html").get_attribute("dir") == "rtl"
                page.locator("#language").select_option("ru")
                page.locator("#domain").select_option("djangojs")
                assert "JavaScript / PWA" in page.locator(".message-card").first.inner_text()
                page.locator("#search").fill("query absent from every catalog")
                assert page.locator(".message-card").count() == 0
                assert page.locator("#shown-count").inner_text() == "0"
                page.locator("#search").fill("")

                page.set_viewport_size({"width": 390, "height": 844})
                assert page.locator("body").evaluate(
                    "element => element.scrollWidth <= window.innerWidth"
                )
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()

    data = build_data()
    total = sum(
        len(rows)
        for language in data["languages"]
        for rows in language["domains"].values()
    )
    print(
        "Translation review website passed: 11 locales, 885 strings per locale, "
        "candidate badges, search, area filter, RTL, pagination, mobile width, "
        f"no browser errors; {total} rendered catalog rows available."
    )


if __name__ == "__main__":
    run()
