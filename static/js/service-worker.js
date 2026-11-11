const CACHE = "rnc-public-shell-v8";
const SHELL = "/consulta-offline/";
const LANGUAGE_KEY = "/__rnc-language__";
const FALLBACK_KEY = "/__rnc-offline-message__/";
const FALLBACK_MESSAGES = {
  en: "The offline query is not available on this device yet.",
  es: "La consulta local aún no está disponible en este dispositivo.",
};
const ASSETS = [
  SHELL,
  "/static/css/site.css",
  "/static/css/components.css",
  "/static/css/offline.css",
  "/static/js/navigation.js",
  "/static/js/session-sync.js",
  "/static/js/forms.js",
  "/static/js/register-service-worker.js",
  "/static/js/offline-consult.js",
  "/static/js/offline-worker.js",
  "/static/js/charts.js",
  "/static/vendor/chart.umd.min.js",
  "/static/images/favicon.svg",
  "/static/pwa/manifest.webmanifest",
  "/static/pwa/icon.svg",
  "/jsi18n/?lang=es",
];
let languageMessageQueue = Promise.resolve();
const languagePattern = /^[a-z]{2,3}(?:-[a-z0-9]{2,8})?$/iu;
const absolutePath = path => new URL(path, self.location.origin);
const languageKey = () => absolutePath(LANGUAGE_KEY);
const fallbackMessageKey = language => {
  const key = absolutePath(FALLBACK_KEY);
  key.searchParams.set("lang", language);
  return key;
};
const localizedShellKey = language => {
  const key = absolutePath(SHELL);
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
  await cache.put(localizedShellKey(language), new Response(html, { headers: response.headers }));
}

self.addEventListener("install", event => event.waitUntil((async () => {
  const cache = await caches.open(CACHE);
  await cache.addAll(ASSETS);
  const shell = await cache.match(SHELL);
  if (shell) await cacheLocalizedShell(cache, shell);
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
  const saveLanguage = languageMessageQueue.then(() => caches.open(CACHE).then(async cache => {
    await cache.put(languageKey(), new Response(language, {
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    }));
    if (typeof data.offlineUnavailable === "string" && data.offlineUnavailable.length <= 300) {
      await cache.put(fallbackMessageKey(language), new Response(data.offlineUnavailable, {
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      }));
    }
    event.ports?.[0]?.postMessage({ saved: language });
  }));
  languageMessageQueue = saveLanguage.catch(() => {});
  event.waitUntil(saveLanguage);
});

async function offlineNavigation(request, url) {
  try {
    const response = await fetch(request);
    if (response.ok && url.pathname === SHELL) {
      const cache = await caches.open(CACHE);
      await cacheLocalizedShell(cache, response.clone());
    }
    return response;
  } catch {
    const cache = await caches.open(CACHE);
    const requested = url.searchParams.get("lang")?.toLowerCase() || "";
    const cookie = cookieLanguage(request);
    const saved = await storedLanguage(cache);
    const browser = request.headers.get("accept-language")?.split(/[,;]/)[0]?.toLowerCase() || "";
    // The locally confirmed selection must win over a potentially stale
    // server cookie when the network is unavailable.
    const language = validLanguage(requested) ? requested
      : saved || cookie || (validLanguage(browser) ? browser : "es");
    const localeShell = validLanguage(language) ? await cache.match(localizedShellKey(language)) : null;
    if (localeShell) return localeShell;
    const message = await cache.match(fallbackMessageKey(language));
    const fallback = message
      ? await message.text()
      : FALLBACK_MESSAGES[language]
        || FALLBACK_MESSAGES[language.split("-")[0]]
        || FALLBACK_MESSAGES.es;
    return new Response(fallback, {
      status: 503,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    });
  }
}

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  // Never cache packages, server query responses, or private service paths.
  if (["/paquete-offline.json", "/service-worker.js"].includes(url.pathname)
    || ["/admin/", "/acceso/", "/administracion/", "/cuenta/"].some(prefix => url.pathname.startsWith(prefix))) return;
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(caches.match(request).then(hit => hit || fetch(request).then(response => {
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
  const publicNavigation = ["/", "/el-rnc/", "/consulta/", "/consulta-sintetica/", SHELL, "/nomencladores/"];
  if (request.mode === "navigate" && publicNavigation.includes(url.pathname)) {
    event.respondWith(offlineNavigation(request, url));
  }
});
