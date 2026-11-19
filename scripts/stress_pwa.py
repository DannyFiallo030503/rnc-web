"""Bounded synthetic load and browser-worker stress profile for the PWA."""

import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import urlopen
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


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * fraction + 0.999999)))
    return round(ordered[index], 2)


def resident_kb():
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def make_stress_rows():
    from analytics.catalogs import SITES, TERRITORIES
    from analytics.standard import AGE_STANDARD_WEIGHTS

    years = [str(year) for year in range(2015, 2025)]
    territories = [entry["name"] for entry in list(TERRITORIES.values())[:8]]
    sexes = ["Mujeres", "Hombres"]
    ages = list(AGE_STANDARD_WEIGHTS)
    sites = [entry["name"] for entry in list(SITES.values())[:10]]
    rows = []
    for year_index, year in enumerate(years):
        for territory_index, territory in enumerate(territories):
            for sex_index, sex in enumerate(sexes):
                for age_index, (age, weight) in enumerate(AGE_STANDARD_WEIGHTS.items()):
                    for site_index, site in enumerate(sites):
                        identity = f"{year_index}-{territory_index}-{sex_index}-{age_index}-{site_index}"
                        rows.append({
                            "synthetic": "TRUE",
                            "person_id": f"SYN-P-{identity}",
                            "tumor_id": f"SYN-T-{identity}",
                            "period": year,
                            "territory": territory,
                            "sex": sex,
                            "age_group": age,
                            "site": site,
                            "population": 15000 + age_index * 7,
                            "standard_weight": weight,
                        })
    return rows


def run():
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.staticfiles.handlers import StaticFilesHandler
    from django.core.wsgi import get_wsgi_application
    from django.urls import clear_url_caches
    from playwright.sync_api import sync_playwright
    from config import settings_public
    from public_site.aggregate_release import _read_artifact, build_release, publish_release
    from public_site.public_forms import CHART_DIMENSION_LIMITS, CHART_METRIC_LIMITS, CHART_UNIT_LIMITS
    from public_site.aggregate_statistics import DIMENSIONS
    from public_site.public_portal import CHARTS, METRICS
    from analytics.standard import AGE_STANDARD_ID, AGE_STANDARD_WEIGHTS

    with tempfile.TemporaryDirectory(prefix="rnc-pwa-stress-") as temporary:
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
        rows = make_stress_rows()
        release = SimpleNamespace(
            pk=uuid4(),
            title="Paquete sintético de carga PWA",
            published_at=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc),
            report={"source": "generador sintético determinista de estrés", "row_count": len(rows)},
        )
        package = build_release(release, rows)
        package["query_contract"] = {
            "dimensions": list(DIMENSIONS),
            "charts": list(CHARTS),
            "metrics": list(METRICS),
            "chart_dimensions": {key: list(value) for key, value in CHART_DIMENSION_LIMITS.items()},
            "chart_metrics": {key: list(value) for key, value in CHART_METRIC_LIMITS.items()},
            "chart_units": {key: list(value) for key, value in CHART_UNIT_LIMITS.items()},
        }
        publish_release(release, rows)
        _read_artifact.cache_clear()
        payload_bytes = json.dumps(package, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        clear_url_caches()

        class StressRoute:
            def __init__(self, wrapped):
                self.wrapped = wrapped

            def __call__(self, environ, start_response):
                if environ.get("PATH_INFO") == "/__stress-package.json":
                    start_response("200 OK", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(payload_bytes))), ("Cache-Control", "no-store")])
                    return [payload_bytes]
                return self.wrapped(environ, start_response)

        application = StressRoute(StaticFilesHandler(get_wsgi_application()))
        server = make_server("127.0.0.1", 0, application, server_class=ThreadedServer, handler_class=QuietHandler)
        base = f"http://127.0.0.1:{server.server_port}"
        serving = threading.Thread(target=server.serve_forever, daemon=True)
        serving.start()
        cpu_start = time.process_time()
        wall_start = time.perf_counter()

        def request_once(sequence):
            started = time.perf_counter()
            try:
                with urlopen(base + "/consulta/?dimension=site&chart=bar&metric=rate&unit=tumors", timeout=30) as response:
                    body = response.read()
                    return {"ok": response.status == 200 and b"result-chart" in body, "ms": (time.perf_counter() - started) * 1000, "bytes": len(body), "sequence": sequence}
            except (URLError, TimeoutError) as error:
                return {"ok": False, "ms": (time.perf_counter() - started) * 1000, "error": type(error).__name__, "sequence": sequence}

        server_load = []
        rss_before_kb = resident_kb()
        try:
            for concurrency, requests_per_worker in [(1, 10), (4, 10), (8, 10), (16, 10)]:
                batch = []
                with ThreadPoolExecutor(max_workers=concurrency) as pool:
                    futures = [pool.submit(request_once, index) for index in range(concurrency * requests_per_worker)]
                    for future in as_completed(futures):
                        batch.append(future.result())
                latencies = [result["ms"] for result in batch]
                server_load.append({
                    "concurrency": concurrency,
                    "requests": len(batch),
                    "successes": sum(result["ok"] for result in batch),
                    "errors": sum(not result["ok"] for result in batch),
                    "p50_ms": percentile(latencies, 0.50),
                    "p95_ms": percentile(latencies, 0.95),
                    "p99_ms": percentile(latencies, 0.99),
                    "max_response_bytes": max((result.get("bytes", 0) for result in batch), default=0),
                })
            recovery = request_once("recovery")
            cpu_seconds = time.process_time() - cpu_start
            wall_seconds = time.perf_counter() - wall_start
            rss_after_load_kb = resident_kb()
            max_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

            with sync_playwright() as playwright:
                launch = {"headless": True}
                if os.environ.get("RNC_REVIEW_BROWSER"):
                    launch["executable_path"] = os.environ["RNC_REVIEW_BROWSER"]
                browser = playwright.chromium.launch(**launch)
                browser_version = browser.version
                context = browser.new_context(service_workers="allow", viewport={"width": 1280, "height": 850})
                page = context.new_page()
                page.goto(base + "/consulta-offline/", wait_until="networkidle")
                worker_bench = page.evaluate("""async () => {
                  const packageStart=performance.now();
                  const response=await fetch('/__stress-package.json',{cache:'no-store'});
                  const release=await response.json();
                  const packageMs=performance.now()-packageStart;
                  const packageBytes=new Blob([JSON.stringify(release)]).size;
                  const worker=new Worker('/static/js/offline-worker.js');
                  const ready=await new Promise((resolve,reject)=>{
                    worker.onmessage=event=>{if(event.data.ready)resolve(event.data);};
                    worker.onerror=reject;
                    worker.postMessage({type:'initialize',release});
                  });
                  const initializeMs=performance.now()-packageStart-packageMs;
                  const params={year:[],territory:[],municipality:[],sex:[],age:[],site:[],dimension:'site',chart:'bar',unit:'tumors',metric:'asr'};
                  const roundTrips=[],workerTimes=[];
                  let last;
                  for(let index=0;index<30;index++){
                    const start=performance.now();
                    last=await new Promise((resolve,reject)=>{
                      worker.onmessage=event=>{if(!event.data.ready)resolve(event.data);};
                      worker.onerror=reject;
                      worker.postMessage({type:'query',params});
                    });
                    roundTrips.push(performance.now()-start);
                    workerTimes.push(last.elapsed);
                    if(!last.ok)throw new Error(last.error);
                  }
                  worker.terminate();
                  const sorted=x=>[...x].sort((a,b)=>a-b);
                  const at=(x,p)=>sorted(x)[Math.min(x.length-1,Math.floor((x.length-1)*p))];
                  return {
                    release:ready.release_id,
                    package_bytes:packageBytes,
                    records:release.report?.row_count || null,
                    aggregate_cells:Object.values(release.cube).reduce((sum,cells)=>sum+cells.length,0),
                    options:Object.fromEntries(Object.entries(release.options).map(([key,values])=>[key,values.length])),
                    package_parse_ms:+packageMs.toFixed(2),
                    worker_initialize_ms:+initializeMs.toFixed(2),
                    worker_rounds:workerTimes.length,
                    worker_p50_ms:+at(workerTimes,.50).toFixed(2),
                    worker_p95_ms:+at(workerTimes,.95).toFixed(2),
                    worker_max_ms:+Math.max(...workerTimes).toFixed(2),
                    roundtrip_p50_ms:+at(roundTrips,.50).toFixed(2),
                    roundtrip_p95_ms:+at(roundTrips,.95).toFixed(2),
                    heap_bytes:performance.memory?.usedJSHeapSize || null,
                    output_categories:last.rows.length,
                    summary:last.summary
                  };
                }""")
                page.goto(base + "/consulta/?dimension=site&chart=bar&metric=asr&unit=tumors", wait_until="networkidle")
                online_rows = page.locator(".result-table tbody tr").evaluate_all("rows=>rows.map(row=>Array.from(row.cells,cell=>cell.innerText.trim()))")
                browser.close()

            report = {
                "success": all(row["errors"] == 0 and row["successes"] == row["requests"] for row in server_load) and recovery["ok"] and len(online_rows) == worker_bench["output_categories"],
                "environment": {"browser": browser_version, "profile": "loopback public-only Django WSGI; temporary release directory; synthetic aggregates only", "python_cpu_seconds": round(cpu_seconds, 3), "wall_seconds": round(wall_seconds, 3), "python_rss_before_load_kb": rss_before_kb, "python_rss_after_load_kb": rss_after_load_kb, "python_max_rss_kb": max_rss_kb},
                "workload": {"input_records": len(rows), "aggregate_cells": worker_bench["aggregate_cells"], "package_bytes": worker_bench["package_bytes"], "periods": 10, "territories": 8, "sexes": 2, "age_groups": 18, "sites": 10, "worker_queries": worker_bench["worker_rounds"]},
                "server_load": server_load,
                "server_recovery": recovery,
                "browser_worker": worker_bench,
                "online_table_rows": len(online_rows),
                "http_requests_are_read_only": True,
                "limitations": ["Mediciones de este equipo y esta versión local; no son umbrales de producción.", "No representa dispositivos móviles de gama baja ni redes cubanas.", "El proceso WSGI de pruebas es threaded en un único proceso y no modela balanceador, CDN ni infraestructura institucional."],
            }
        finally:
            server.shutdown()
            server.server_close()
            serving.join(timeout=5)

    output = ROOT / "docs" / "pwa-stress.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"success": report["success"], "records": report["workload"]["input_records"], "package_bytes": report["workload"]["package_bytes"], "server_load": report["server_load"], "browser_worker": {key: report["browser_worker"][key] for key in ("worker_p50_ms", "worker_p95_ms", "worker_max_ms", "roundtrip_p50_ms", "roundtrip_p95_ms")}, "output": str(output)}, ensure_ascii=False))
    if not report["success"]:
        raise SystemExit(1)


if __name__ == "__main__":
    run()
