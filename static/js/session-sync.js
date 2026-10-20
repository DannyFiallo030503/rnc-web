"use strict";
(() => {
  const identity = document.body.dataset.sessionIdentity;
  if (!identity) return;
  const storageKey = "rnc.session.identity";
  window.addEventListener("storage", (event) => {
    if (event.key === storageKey && event.newValue && event.newValue !== identity)
      window.location.reload();
  });
  try {
    window.localStorage.setItem(storageKey, identity);
  } catch {
    // BroadcastChannel below still synchronizes private browsing contexts.
  }
  if (!("BroadcastChannel" in window)) return;
  const channel = new BroadcastChannel("rnc-session-state");
  channel.addEventListener("message", ({ data }) => {
    if (data?.type === "identity" && data.identity !== identity) window.location.reload();
  });
  channel.postMessage({ type: "identity", identity });
})();
