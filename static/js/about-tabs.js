(() => {
  const tablist = document.querySelector(".about-index");
  const panels = document.querySelector(".about-sections");
  if (!tablist || !panels) return;

  const tabs = [...tablist.querySelectorAll('a[href^="#"]')]
    .map((tab) => ({ tab, panel: document.getElementById(tab.hash.slice(1)) }))
    .filter(({ panel }) => panel && panels.contains(panel));
  if (!tabs.length) return;

  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-orientation", "horizontal");

  tabs.forEach(({ tab, panel }) => {
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-controls", panel.id);
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);
    panel.setAttribute("tabindex", "0");
  });

  const activate = (selected, { focus = false, updateHash = true } = {}) => {
    tabs.forEach(({ tab, panel }) => {
      const active = tab === selected;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
      panel.hidden = !active;
    });

    if (updateHash && window.location.hash !== selected.hash) {
      window.history.replaceState(null, "", selected.hash);
    }
    if (focus) selected.focus();
  };

  const initial = tabs.find(({ tab }) => tab.hash === window.location.hash)?.tab || tabs[0].tab;
  activate(initial, { updateHash: false });

  tablist.addEventListener("click", (event) => {
    const tab = event.target.closest('a[role="tab"]');
    if (!tab || !tablist.contains(tab)) return;
    event.preventDefault();
    activate(tab);
  });

  tablist.addEventListener("keydown", (event) => {
    const currentIndex = tabs.findIndex(({ tab }) => tab === document.activeElement);
    if (currentIndex < 0) return;

    let nextIndex;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
    else if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") nextIndex = 0;
    else if (event.key === "End") nextIndex = tabs.length - 1;
    else return;

    event.preventDefault();
    activate(tabs[nextIndex].tab, { focus: true });
  });

  window.addEventListener("hashchange", () => {
    const match = tabs.find(({ tab }) => tab.hash === window.location.hash);
    if (match) activate(match.tab, { updateHash: false });
  });
})();
