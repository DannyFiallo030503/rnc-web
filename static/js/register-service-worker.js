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
      const postLanguage = language => new Promise(resolve => {
        const supported = new Set([...document.querySelectorAll("#site-language option")].map(option => option.value));
        const worker = navigator.serviceWorker.controller || registration.active;
        if (!worker || !supported.has(language)) {
          resolve(false);
          return;
        }
        const message = {
          type: "rnc-language",
          language,
          offlineUnavailable: document.documentElement.dataset.offlineUnavailable || "",
        };
        if (typeof MessageChannel === "undefined") {
          worker.postMessage(message);
          resolve(true);
          return;
        }
        const channel = new MessageChannel();
        const timeout = setTimeout(() => resolve(false), 1500);
        channel.port1.onmessage = () => {
          clearTimeout(timeout);
          channel.port1.close();
          resolve(true);
        };
        worker.postMessage(message, [channel.port2]);
      });
      const syncLanguage = () => languageChangePending
        ? Promise.resolve(false)
        : postLanguage(document.documentElement.lang);
      document.querySelector(".language-picker")?.addEventListener("submit", async event => {
        const form = event.currentTarget;
        if (form.dataset.languageReady === "true") return;
        const selected = form.querySelector("select[name=language]")?.value;
        if (!selected) return;
        event.preventDefault();
        languageChangePending = true;
        await postLanguage(selected);
        form.dataset.languageReady = "true";
        form.requestSubmit(event.submitter);
      });
      navigator.serviceWorker.addEventListener("controllerchange", syncLanguage);
      navigator.serviceWorker.ready.then(syncLanguage);
    } catch {
      // PWA support is optional; the online public site remains usable.
    }
  });
}
