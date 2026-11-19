const CACHE = "rnc-public-shell-navigation-20261113-v7";
const SHELL = "/consulta/";
const PUBLIC_PAGES = ["/", "/el-rnc/", SHELL, "/nomencladores/"];
const QUERY_ALIASES = ["/consulta-sintetica/", "/consulta-offline/"];
const pagePath = path => QUERY_ALIASES.includes(path) ? SHELL : path;
const LANGUAGE_KEY = "/__rnc-language__";
const LANGUAGE_REVISION_KEY = "/__rnc-language-revision__";
const FALLBACK_KEY = "/__rnc-offline-message__/";
const FALLBACK_MESSAGES = {
  en: "The offline query is not available on this device yet.",
  es: "La consulta local aún no está disponible en este dispositivo.",
};
const PAGE_UNAVAILABLE_MESSAGES = {
  en: "This page is not saved for offline use.",
  es: "Esta página no está guardada para usarla sin conexión.",
};
const ASSETS = [
  ...PUBLIC_PAGES,
  "/static/js/about-tabs.js",
  "/static/js/language.js",
  "/static/css/site.css",
  "/static/css/components.css",
  "/static/css/offline.css",
  "/static/js/navigation.js",
  "/static/js/session-sync.js",
  "/static/js/forms.js",
  "/static/js/register-service-worker.js",
  "/static/js/unified-consult.js",
  "/static/js/explorer-layout.js",
  "/static/geo/cuba-provinces.geojson",
  "/static/js/offline-worker.js",
  "/static/js/charts.js",
  "/static/js/chart-layout.js",
  "/static/vendor/chart.umd.min.js",
  "/static/images/favicon.svg",
  "/static/pwa/manifest.webmanifest",
  "/static/pwa/icon.svg",
  "/jsi18n/?lang=es",
  "/jsi18n/?lang=en",
];
let languageMessageQueue = Promise.resolve();
const languagePattern = /^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$/iu;
const absolutePath = path => new URL(path, self.location.origin);
const languageKey = () => absolutePath(LANGUAGE_KEY);
const languageRevisionKey = () => absolutePath(LANGUAGE_REVISION_KEY);
const fallbackMessageKey = language => {
  const key = absolutePath(FALLBACK_KEY);
  key.searchParams.set("lang", language);
  return key;
};
const localizedShellKey = (language, path = SHELL) => {
  const key = absolutePath(path);
  key.searchParams.set("__rnc_locale", language);
  return key;
};
const validLanguage = value => typeof value === "string" && languagePattern.test(value);

async function storedLanguage(cache) {
  const response = await cache.match(languageKey());
  const language = response ? (await response.text()).toLowerCase() : "";
  return validLanguage(language) ? language : "";
}

function cookieLanguage(request) {
  const cookie = request.headers.get("cookie") || "";
  const match = cookie.match(/(?:^|;\s*)rnc_language=([^;]+)/i);
  if (!match) return "";
  try {
    const language = decodeURIComponent(match[1]).toLowerCase();
    return validLanguage(language) ? language : "";
  } catch {
    return "";
  }
}

async function cacheLocalizedShell(cache, response) {
  const html = await response.text();
  const language = html.match(/<html\b[^>]*\blang=["']([^"']+)["']/i)?.[1]?.toLowerCase();
  if (!validLanguage(language)) return;
  const path = response.url ? new URL(response.url).pathname : SHELL;
  await cache.put(localizedShellKey(language, path), new Response(html, { headers: response.headers }));
  return language;
}

self.addEventListener("install", event => event.waitUntil((async () => {
  const cache = await caches.open(CACHE);
  await cache.addAll(ASSETS.map(path => new Request(absolutePath(path), {credentials: "omit"})));
  const shell = await cache.match(SHELL);
  if (shell) await cacheLocalizedShell(cache, shell);
  for (const language of ["es", "en"]) for (const path of PUBLIC_PAGES) {
    const url=new URL(path,self.location.origin);url.searchParams.set("__rnc_locale",language);
    const response=await fetch(url,{cache:"reload",credentials:"omit"});
    if(!response.ok || await cacheLocalizedShell(cache,response)!==language)throw new Error("Public page preparation failed");
  }
  await self.skipWaiting();
})()));
self.addEventListener("activate", event => event.waitUntil(
  caches.keys()
    .then(keys => Promise.all(keys.filter(key => key.startsWith("rnc-public-shell-") && key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()),
));
self.addEventListener("message", event => {
  const data = event.data;
  const language = typeof data?.language === "string" ? data.language.toLowerCase() : "";
  if (data?.type !== "rnc-language" || !validLanguage(language)) return;
  const revision = Number.isSafeInteger(data.revision) && data.revision >= 0 ? data.revision : 0;
  const saveLanguage = languageMessageQueue.then(() => caches.open(CACHE).then(async cache => {
    const savedRevisionResponse = await cache.match(languageRevisionKey());
    const savedRevision = Number.parseInt(await savedRevisionResponse?.text(), 10) || 0;
    if (revision < savedRevision) {
      event.ports?.[0]?.postMessage({
        saved: await storedLanguage(cache),
        revision: savedRevision,
        ignored: true,
      });
      return;
    }
    await cache.put(languageKey(), new Response(language, {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    }));
    await cache.put(languageRevisionKey(), new Response(String(revision), {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    }));
    if (typeof data.offlineUnavailable === "string" && data.offlineUnavailable.length <= 300) {
      await cache.put(fallbackMessageKey(language), new Response(data.offlineUnavailable, {
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      }));
    }
    event.ports?.[0]?.postMessage({ saved: language, revision });
  }));
  languageMessageQueue = saveLanguage.catch(() => {});
  event.waitUntil(saveLanguage);
});

async function cachedNavigation(request, url) {
  const cache = await caches.open(CACHE);
  const requested = (url.searchParams.get("__rnc_locale") || url.searchParams.get("lang"))?.toLowerCase() || "";
  const saved = await storedLanguage(cache);
  const cookie = cookieLanguage(request);
  const browser = request.headers.get("accept-language")?.split(/[,;]/)[0]?.toLowerCase() || "";
  const language = validLanguage(requested) ? requested
    : saved || cookie || (validLanguage(browser) ? browser : "es");
  // Only query aliases may share the query shell. Other pages keep their identity.
  const path = pagePath(url.pathname);
  for (const locale of new Set([language, language.split("-")[0]])) {
    const hit = await cache.match(localizedShellKey(locale, path));
    if (!hit) continue;
    let html = await hit.text();
    html = html.replace(/<html\b([^>]*)>/i, (_, attributes) =>
      `<html${attributes.replace(/\sdata-server-connection=["'][^"']*["']/i, "")} data-server-connection="offline">`);
    html = html.replace('data-state="checking"', 'data-state="offline"')
      .replace(/(<span class="connection-label">)[^<]*(<\/span>)/, "$1Offline$2");
    // The page is already marked offline before its first paint or deferred JS.
    return new Response(html, {headers: hit.headers});
  }
  const message = await cache.match(fallbackMessageKey(language));
  const fallback = path!==SHELL
    ? PAGE_UNAVAILABLE_MESSAGES[language] || PAGE_UNAVAILABLE_MESSAGES[language.split("-")[0]] || PAGE_UNAVAILABLE_MESSAGES.es
    : message ? await message.text()
    : FALLBACK_MESSAGES[language] || FALLBACK_MESSAGES[language.split("-")[0]] || FALLBACK_MESSAGES.es;
  return new Response(fallback, {status: 503, headers: {"Content-Type": "text/plain; charset=utf-8"}});
}

async function offlineNavigation(request, url) {
  if (self.navigator?.onLine === false) return cachedNavigation(request, url);
  try {
    const response = await fetch(request, {credentials: "omit", signal: AbortSignal.timeout(5000)});
    if (response.status >= 500) return cachedNavigation(request, url);
    const path = pagePath(url.pathname);
    const plainPage = [...url.searchParams.keys()].every(key => ["__rnc_locale", "lang"].includes(key));
    if (response.ok && PUBLIC_PAGES.includes(path) && plainPage) {
      const cache = await caches.open(CACHE);
      await cacheLocalizedShell(cache, response.clone());
    }
    return response;
  } catch {
    return cachedNavigation(request, url);
  }
}

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  // Never cache packages, server query responses, or private service paths.
  if (["/paquete-offline.json", "/conexion.json", "/service-worker.js"].includes(url.pathname)
    || ["/admin/", "/acceso/", "/administracion/", "/cuenta/"].some(prefix => url.pathname.startsWith(prefix))) return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.open(CACHE).then(cache => cache.match(request, {ignoreSearch:true})).then(hit => hit || fetch(request).then(response => {
      if (response.ok) caches.open(CACHE).then(cache => cache.put(request, response.clone()));
      return response;
    })));
    return;
  }
  if (url.pathname === "/jsi18n/") {
    event.respondWith(fetch(request).then(response => {
      if (response.ok) event.waitUntil(caches.open(CACHE).then(cache => cache.put(request, response.clone())));
      return response;
    }).catch(async () => (await caches.match(request, { ignoreVary: true })) || new Response("", { status: 503 })));
    return;
  }
  const publicNavigation = [...PUBLIC_PAGES, ...QUERY_ALIASES];
  if (request.mode === "navigate" && publicNavigation.includes(url.pathname)) {
    event.respondWith(offlineNavigation(request, url));
  }
});
