"use strict";
(() => {
  function initialize(root = document) {
  const form = root.querySelector("#query-form[data-query-form]");
  if (!form) return;
  const t = text => window.gettext ? window.gettext(text) : text;
  const workspace = form.closest(".query-workspace");
  const sidebar = form.closest(".query-filter-sidebar");
  const originalPanel = form.closest(".query-filter-panel");
  const select = form.elements.namedItem("chart");
  if (!workspace || !sidebar || !select) return;
  const kind = select.value;
  const circular = ["pie", "doughnut"].includes(kind);
  const points = ["scatter", "strip", "swarm"].includes(kind);
  const paths = {
    bar: "M4 4v16h16M7 6h11v3H7zM7 12h7v3H7z",
    ranking: "M4 4v16h16M7 5h12v3H7zM7 10h8v3H7zM7 15h4v3H7z",
    column: "M4 4v16h16M7 11h3v6H7zM13 6h3v11h-3z",
    line: "M4 4v16h16M6 16l4-7 4 3 5-7",
    trend: "M4 4v16h16M6 17l4-5 4 2 6-9M16 5h4v4",
    curve: "M4 4v16h16M6 17C13 17 17 13 19 5",
    map: "M3 10l4-3 4 1 3 4 5 1 2 3-5 1-4-2-3-3-5 1z",
    table: "M3 4h18v16H3zM3 9h18M3 14h18M9 4v16M15 4v16",
    grouped: "M3 20h18M5 10h3v7H5zM9 6h3v11H9zM15 12h3v5h-3zM19 8h2v9h-2z",
    stacked: "M4 20h16M6 5h4v12H6zM6 10h4M14 8h4v9h-4zM14 13h4",
    percent: "M4 20h16M6 4h4v13H6zM6 9h4M14 4h4v13h-4zM14 12h4",
    scatter: "M4 4v16h16M8 15h.1M10 9h.1M14 12h.1M18 6h.1",
    strip: "M4 4v16h16M7 9h.1M10 9h.1M15 9h.1M9 15h.1M17 15h.1",
    swarm: "M4 4v16h16M9 10h.1M12 7h.1M12 13h.1M15 10h.1M18 13h.1",
    pie: "M12 3v9h9A9 9 0 0 0 12 3zM8 4a9 9 0 1 0 12 12H8z",
    doughnut: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
  };
  const rail = document.createElement("nav");
  rail.className = "query-chart-rail";
  rail.setAttribute("aria-label", select.dataset.label || t("Tipo de gráfico"));
  for (const option of select.options) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "query-chart-button";
    button.setAttribute("aria-label", option.textContent);
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", paths[option.value] || paths.bar);
    svg.append(path);
    const label = document.createElement("span");
    label.textContent = option.textContent;
    button.append(svg, label);
    const positionLabel = () => {
      const rect = button.getBoundingClientRect();
      label.style.left = `${rect.right + 10}px`;
      label.style.top = `${rect.top + rect.height / 2}px`;
    };
    button.addEventListener("pointerenter", positionLabel);
    button.addEventListener("focus", positionLabel);
    button.setAttribute("aria-pressed", String(option.selected));
    button.title = option.textContent;
    const years = form.querySelectorAll('input[name="year"]').length;
    button.disabled = ["line", "trend"].includes(option.value) && years < 2;
    if (button.disabled) button.title = t("La serie temporal requiere al menos dos años disponibles.");
    button.addEventListener("click", () => {
      if (select.value === option.value) return;
      select.value = option.value;
      select.dispatchEvent(new Event("change", {bubbles: true}));
    });
    rail.append(button);
  }
  workspace.insertBefore(rail, sidebar);
  select.closest(".form-field").hidden = true;
  // Move the existing controls, preserving widgets, names and event listeners.
  const grid = form.querySelector(".form-grid");
  const tablist = document.createElement("div");
  tablist.className = "query-control-tabs";
  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-label", t("Opciones del gráfico"));
  form.insertBefore(tablist, grid);
  const tabs = [];
  function addTab(id, label) {
    const button = document.createElement("button");
    button.type = "button";
    button.id = `query-tab-${id}`;
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", `query-panel-${id}`);
    button.textContent = t(label);
    const panel = document.createElement("section");
    panel.id = `query-panel-${id}`;
    panel.className = "form-grid";
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", button.id);
    form.insertBefore(panel, grid);
    tablist.append(button);
    tabs.push({id, button, panel});
    button.addEventListener("click", () => activate(id));
    button.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const index = tabs.findIndex(tab => tab.id === id);
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
      activate(tabs[next].id);
      tabs[next].button.focus();
    });
    return panel;
  }
  function activate(id) {
    tabs.forEach(tab => {
      const active = tab.id === id;
      tab.button.setAttribute("aria-selected", String(active));
      tab.button.tabIndex = active ? 0 : -1;
      tab.panel.hidden = !active;
    });
  }
  const filters = addTab("filters", "Filtros");
  const comparison = addTab("comparison", "Comparación");
  [...grid.children].forEach(field => {
    if (field.dataset.field === "chart") return;
    (["unit", "metric", "dimension"].includes(field.dataset.field) ? comparison : filters).append(field);
  });
  grid.hidden = true;
  originalPanel.querySelector(":scope > summary").hidden = true;
  originalPanel.open = true;
  if (["map", "table"].includes(kind)) {
    activate("filters");
    workspace.classList.add("query-workspace-with-rail");
    return;
  }
  const view = addTab("view", circular ? "Composición" : points ? "Puntos" : ["line", "trend", "curve"].includes(kind) ? "Líneas" : "Barras");
  const canvas = document.getElementById("result-chart");
  const chart = window.Chart && canvas ? Chart.getChart(canvas) : null;
  function setting(label, type, initial, apply, bounds = {}, target = view) {
    const wrapper = document.createElement("label");
    wrapper.className = "query-view-setting";
    const title = document.createElement("span");
    title.textContent = t(label);
    const input = document.createElement("input");
    input.type = type;
    if (type === "checkbox") input.checked = initial;
    else input.value = initial;
    Object.assign(input, bounds);
    input.disabled = !chart;
    wrapper.append(title, input);
    target.append(wrapper);
    wrapper.addEventListener("change", event => {
      event.stopPropagation();
      if (!chart) return;
      apply(type === "checkbox" ? input.checked : Number(input.value));
      chart.update();
    });
  }
  if (points) {
    setting("Tamaño de los puntos", "range", 6, value => {
      chart.data.datasets.forEach(dataset => { dataset.pointRadius = value; dataset.pointHoverRadius = value + 3; });
    }, {min: 3, max: 12, step: 1});
  } else if (["line", "trend", "curve"].includes(kind)) {
    setting("Grosor de la línea", "range", 2, value => {
      chart.data.datasets.forEach(dataset => { dataset.borderWidth = value; });
    }, {min: 1, max: 6, step: 1});
    setting("Mostrar puntos", "checkbox", true, value => {
      chart.data.datasets.forEach(dataset => { dataset.pointRadius = value ? 3 : 0; });
    });
  } else if (!circular) {
    setting("Grosor de las barras", "range", 90, value => {
      chart.data.datasets.forEach(dataset => { dataset.barPercentage = value / 100; });
    }, {min: 20, max: 100, step: 5});
  }
  if (kind === "doughnut") setting("Tamaño del centro", "range", 50, value => { chart.options.cutout = `${value}%`; }, {min: 20, max: 80, step: 5});
  if (!points) setting("Mostrar valores", "checkbox", true, value => {
    chart.options.plugins.rncValueLabels = {display: value};
  });
  setting("Mostrar leyenda", "checkbox", Boolean(chart?.options.plugins.legend.display), value => { chart.options.plugins.legend.display = value; });
  if (!circular && kind !== "percent") {
    const axes = addTab("axes", "Escala");
    setting("Iniciar escala en cero", "checkbox", true, value => {
      const names = kind === "scatter" ? ["x", "y"] : points || chart.options.indexAxis === "y" ? ["x"] : ["y"];
      names.forEach(name => { chart.options.scales[name].beginAtZero = value; });
    }, {}, axes);
  }
  activate("filters");
  workspace.classList.add("query-workspace-with-rail");
  }
  window.RncExplorer = {initialize};
  initialize();
})();
