if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      const registrations = await navigator.serviceWorker.getRegistrations();
      for (const registration of registrations) {
        const script = registration.active?.scriptURL || registration.waiting?.scriptURL || registration.installing?.scriptURL;
        if (registration.scope === `${location.origin}/consulta-offline/` && script === `${location.origin}/consulta-offline/service-worker.js`) {
          await registration.unregister();
          if ("caches" in window) {
            const keys = await caches.keys();
            await Promise.all(keys.filter(key => key.startsWith("rnc-public-shell-")).map(key => caches.delete(key)));
          }
        }
      }
      const registration = await navigator.serviceWorker.register("/service-worker.js", { scope: "/" });
      let languageChangePending = false;
      const supported = new Set([...document.querySelectorAll("#site-language option")].map(option => option.value));
      const preferenceKey = "rnc-language-preference";
      let fallbackPreference = null;
      const parsePreference = value => {
        try {
          const preference = JSON.parse(value);
          return supported.has(preference?.language)
            && Number.isSafeInteger(preference?.revision)
            && preference.revision >= 0
            ? preference
            : null;
        } catch {
          return null;
        }
      };
      const currentPreference = () => {
        let preference = null;
        try {
          preference = parsePreference(localStorage.getItem(preferenceKey));
        } catch {
          // Storage is optional; a page-local revision still protects this client.
        }
        if (!preference && fallbackPreference) preference = fallbackPreference;
        if (!preference) {
          const cookie = document.cookie.match(/(?:^|;\s*)rnc_language=([^;]+)/i);
          let language = "";
          try {
            language = cookie ? decodeURIComponent(cookie[1]) : "";
          } catch {
            language = "";
          }
          language = supported.has(language) ? language : document.documentElement.lang;
          if (!supported.has(language)) language = "es";
          preference = { language, revision: Date.now() };
          fallbackPreference = preference;
          try {
            localStorage.setItem(preferenceKey, JSON.stringify(preference));
          } catch {
            // Keep the preference for this page when persistent storage is unavailable.
          }
        }
        fallbackPreference = preference;
        return preference;
      };
      const selectPreference = language => {
        const previous = currentPreference();
        const preference = {
          language,
          revision: Math.max(Date.now(), previous.revision + 1),
        };
        fallbackPreference = preference;
        try {
          localStorage.setItem(preferenceKey, JSON.stringify(preference));
        } catch {
          // The worker still receives the monotonic revision from this page.
        }
        return preference;
      };
      const postLanguage = (language, revision) => new Promise(resolve => {
        const worker = navigator.serviceWorker.controller || registration.active;
        if (!worker || !supported.has(language) || !Number.isSafeInteger(revision)) {
          resolve(false);
          return;
        }
        const message = {
          type: "rnc-language",
          language,
          revision,
          offlineUnavailable: document.documentElement.dataset.offlineUnavailable || "",
        };
        if (typeof MessageChannel === "undefined") {
          worker.postMessage(message);
          resolve(true);
          return;
        }
        const channel = new MessageChannel();
        const timeout = setTimeout(() => resolve(false), 1500);
        channel.port1.onmessage = event => {
          clearTimeout(timeout);
          channel.port1.close();
          resolve(event.data?.saved === language && event.data?.revision === revision);
        };
        worker.postMessage(message, [channel.port2]);
      });
      const syncLanguage = () => {
        if (languageChangePending) return Promise.resolve(false);
        const preference = currentPreference();
        return postLanguage(preference.language, preference.revision);
      };
      document.querySelector(".language-picker")?.addEventListener("submit", async event => {
        const form = event.currentTarget;
        if (form.dataset.languageReady === "true") return;
        const selected = form.querySelector("select[name=language]")?.value;
        if (!selected) return;
        event.preventDefault();
        languageChangePending = true;
        const preference = selectPreference(selected);
        await postLanguage(preference.language, preference.revision);
        form.dataset.languageReady = "true";
        form.requestSubmit(event.submitter);
      });
      window.addEventListener("storage", event => {
        if (event.key !== preferenceKey) return;
        const preference = parsePreference(event.newValue);
        if (preference) {
          fallbackPreference = preference;
          postLanguage(preference.language, preference.revision);
        }
      });
      navigator.serviceWorker.addEventListener("controllerchange", syncLanguage);
      navigator.serviceWorker.ready.then(syncLanguage);
    } catch {
      // PWA support is optional; the online public site remains usable.
    }
  });
}
