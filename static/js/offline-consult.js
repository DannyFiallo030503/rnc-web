"use strict";
(() => {
  const t = message => window.gettext ? window.gettext(message) : message;
  const displayCategory = value => t(String(value));
  const fmt = (message, values) => window.interpolate ? window.interpolate(t(message), values, true) : message.replace(/%\((\w+)\)s/g, (_, key) => values[key]);
  const plural = (singular, many, count) => window.ngettext ? window.ngettext(singular, many, count) : (count === 1 ? singular : many);
  const WORKER_MESSAGES = [
    ["Frecuencia absoluta", t("Frecuencia absoluta")],
    ["Frecuencia relativa (%)", t("Frecuencia relativa (%)")],
    ["Tasa cruda / específica por 100 000", t("Tasa cruda / específica por 100 000")],
    ["Tasa ajustada Segi–Doll por 100 000", t("Tasa ajustada Segi–Doll por 100 000")],
    ["Mujeres", t("Mujeres")],
    ["Hombres", t("Hombres")],
    ["dimensión", t("dimensión")],
    ["indicador", t("indicador")],
    ["unidad", t("unidad")],
    ["personas distintas con selección múltiple", t("personas distintas con selección múltiple")],
    ["ajuste por edad incompatible con la selección", t("ajuste por edad incompatible con la selección")],
    ["composición de personas solo por sexo", t("composición de personas solo por sexo")],
    ["comparación por sexo necesita ambos sexos", t("comparación por sexo necesita ambos sexos")],
    ["dispersión requiere filtros simples", t("dispersión requiere filtros simples")],
    ["valor de %(key)s fuera del paquete", t("valor de %(key)s fuera del paquete")],
    ["la publicación no contiene ambos sexos", t("la publicación no contiene ambos sexos")],
    ["Selección no compatible: %(errors)s.", t("Selección no compatible: %(errors)s.")],
    ["Este gráfico necesita al menos dos categorías con datos.", t("Este gráfico necesita al menos dos categorías con datos.")],
    ["El gráfico circular necesita hasta ocho categorías.", t("El gráfico circular necesita hasta ocho categorías.")],
    ["No hay valores positivos para representar una composición.", t("No hay valores positivos para representar una composición.")],
    ["Falta población en algún grupo de edad para calcular la tasa ajustada.", t("Falta población en algún grupo de edad para calcular la tasa ajustada.")],
    ["Tumores y personas distintas", t("Tumores y personas distintas")],
    ["No se cargó una publicación local.", t("No se cargó una publicación local.")],
    ["Paquete local: %(title)s · versión %(release)s · publicado %(published)s · %(size)s KB", t("Paquete local: %(title)s · versión %(release)s · publicado %(published)s · %(size)s KB")],
    ["Publicación %(release)s · %(date)s", t("Publicación %(release)s · %(date)s")],
    ["Página %(page)s de %(pages)s · %(count)s %(categories)s", t("Página %(page)s de %(pages)s · %(count)s %(categories)s")],
    ["Tumores: %(tumors)s · Personas distintas: %(persons)s · Población: %(population)s · cálculo local: %(elapsed)s ms", t("Tumores: %(tumors)s · Personas distintas: %(persons)s · Población: %(population)s · cálculo local: %(elapsed)s ms")],
    ["No disponible", t("No disponible")], ["Todos", t("Todos")],
  ];
  const DIMENSION_LABELS = {
    site: t("Grupo de localización"), territory: t("Provincia de residencia"),
    sex: t("Sexo"), age_group: t("Edad"), period: t("Año de incidencia"),
  };
  const CHART_LABELS = {
    bar: t("Barras horizontales"), ranking: t("Ranking por indicador"),
    scatter: t("Dispersión: tumores y personas por provincia/edad"),
    strip: t("Puntos por provincia o grupo de edad"),
    swarm: t("Distribución territorial (swarm)"), column: t("Columnas"),
    line: t("Líneas"), grouped: t("Barras agrupadas por sexo"),
    stacked: t("Barras apiladas por sexo"), percent: t("Barras porcentuales por sexo"),
    pie: t("Circular"), doughnut: t("Anillo"),
  };
  const METRIC_LABELS = {
    count: t("Frecuencia absoluta"), share: t("Frecuencia relativa (%)"),
    rate: t("Tasa cruda / específica por 100 000"),
    asr: t("Tasa ajustada Segi–Doll por 100 000"),
  };
  const $ = selector => document.querySelector(selector);
  const FILTERS = ["year", "territory", "municipality", "sex", "age", "site"];
  const FILTER_LABELS = {
    year: "Año de incidencia", territory: "Provincia de residencia", municipality: "Municipio de residencia",
    sex: "Sexo", age: "Edad", site: "Grupo de localización",
  };
  const numberFormat = new Intl.NumberFormat(document.documentElement.lang || "es", { maximumFractionDigits: 2 });
  const decimalFormat = new Intl.NumberFormat(document.documentElement.lang || "es", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const integerFormat = new Intl.NumberFormat(document.documentElement.lang || "es", { maximumFractionDigits: 0 });
  const dateTimeFormat = new Intl.DateTimeFormat(document.documentElement.lang || "es", { dateStyle: "medium", timeStyle: "short" });
  const displayDateTime = value => {
    const date = value ? new Date(value) : null;
    return date && !Number.isNaN(date.getTime()) ? dateTimeFormat.format(date) : (value || t("fecha no disponible"));
  };
  const PAGE_SIZE = 10;
  let db;
  let pkg;
  let installPrompt;
  let worker;
  let workerReleaseId;
  let workerReady;
  let pendingQuery;
  let pageIndex = 0;
  let printAll = false;
  let lastResult;
  let lastParams;

  const dbOpen = () => new Promise((resolve, reject) => {
    const request = indexedDB.open("rnc-public-offline", 2);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains("package")) request.result.createObjectStore("package");
    };
    request.onsuccess = () => { db = request.result; resolve(db); };
    request.onerror = () => reject(request.error);
  });
  const transaction = (mode, action) => new Promise((resolve, reject) => {
    const tx = db.transaction("package", mode);
    const result = action(tx.objectStore("package"));
    tx.oncomplete = () => resolve(result?.result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error || new Error(t("No se pudo guardar el paquete local.")));
  });
  const loadPackage = () => transaction("readonly", store => store.get("active"));
  const savePackage = value => transaction("readwrite", store => store.put(value, "active"));
  const deletePackage = () => transaction("readwrite", store => store.delete("active"));

  const status = (message, bad = false) => {
    const node = $("#offline-status");
    node.textContent = message;
    node.classList.toggle("error", bad);
  };
  const selected = id => [...$(`#${id}`).selectedOptions].map(option => option.value).filter(Boolean);
  const setOptions = (element, values, { multiple = false, placeholder = "" } = {}) => {
    element.multiple = multiple;
    element.replaceChildren();
    if (!multiple) element.add(new Option(placeholder, ""));
    for (const value of values) {
      const option = Array.isArray(value)
        ? new Option(t(String(value[1])), String(value[0]))
        : new Option(displayCategory(value), String(value));
      element.add(option);
    }
  };
  const queryParams = () => Object.fromEntries([
    ...FILTERS.map(key => [key, selected(key)]),
    ["dimension", $("#dimension").value],
    ["chart", $("#chart-kind").value],
    ["unit", $("#unit").value],
    ["metric", $("#metric").value],
  ]);

  async function storageInfo() {
    const node = $("#offline-storage");
    if (!navigator.storage?.estimate) {
      node.textContent = t("El navegador no ofrece una estimación de almacenamiento.");
      return;
    }
    try {
      const estimate = await navigator.storage.estimate();
      const used = numberFormat.format((estimate.usage || 0) / 1024 / 1024);
      const quotaValue = numberFormat.format((estimate.quota || 0) / 1024 / 1024);
      node.textContent = fmt("Almacenamiento del sitio usado: %(used)s MB%(quota)s. Estimación del navegador.", {used, quota: estimate.quota ? fmt(" de %(quota)s MB estimados", {quota: quotaValue}) : ""});
    } catch {
      node.textContent = t("No se pudo estimar el almacenamiento disponible.");
    }
  }

  function renderPackage() {
    if (!pkg) {
      $("#offline-release").textContent = t("No hay paquete guardado.");
      $("#offline-context").textContent = t("Guarda una publicación mientras tienes conexión para consultar desde este dispositivo.");
      return;
    }
    const size = pkg.bytes || new Blob([JSON.stringify(pkg)]).size;
    $("#offline-release").textContent = fmt("Paquete local: %(title)s · versión %(release)s · publicado %(published)s · %(size)s KB", {title: pkg.title, release: pkg.release_id, published: displayDateTime(pkg.published_at), size: (size / 1024).toFixed(1)});
    $("#offline-context").textContent = fmt("Datos sintéticos · método %(method)s · guardado en este navegador. La fecha de publicación identifica el corte; no indica cuándo se conectó el dispositivo.", {method: pkg.standard_id});
    fill(pkg);
  }

  function fill(release) {
    const options = release.options || {};
    const optionKeys = { year: "period", territory: "territory", municipality: "municipality", sex: "sex", age: "age_group", site: "site" };
    for (const [id, key] of Object.entries(optionKeys)) {
      setOptions($(`#${id}`), options[key] || [], { multiple: true });
    }
    const municipalityAvailable = (release.fields || []).includes("municipality") && (options.municipality || []).length > 0;
    $("#municipality").disabled = !municipalityAvailable;
    if (!municipalityAvailable) $("#municipality").replaceChildren(new Option(t("No disponible en esta publicación"), ""));

    const contract = release.query_contract || {};
    setOptions($("#dimension"), (contract.dimensions || []).map(key => [key, DIMENSION_LABELS[key] || key]), { placeholder: t("Seleccione una dimensión") });
    setOptions($("#chart-kind"), (contract.charts || []).map(key => [key, CHART_LABELS[key] || key]), { placeholder: t("Seleccione un gráfico") });
    setOptions($("#metric"), (contract.metrics || []).map(key => [key, METRIC_LABELS[key] || key]), { placeholder: t("Seleccione un indicador") });
    $("#dimension").value = "site";
    $("#chart-kind").value = "bar";
    $("#metric").value = "count";
    syncCompatibility();
  }

  function syncCompatibility() {
    if (!pkg?.query_contract) return;
    const contract = pkg.query_contract;
    const chart = $("#chart-kind").value;
    const dimension = $("#dimension").value;
    const metric = $("#metric").value;
    let unit = $("#unit").value;
    const multi = FILTERS.some(key => selected(key).length > 1);
    const dimensions = contract.chart_dimensions?.[chart];
    const metrics = contract.chart_metrics?.[chart];
    const units = contract.chart_units?.[chart];
    [...$("#chart-kind").options].forEach(option => {
      const allowedDimensions = contract.chart_dimensions?.[option.value];
      const allowedMetrics = contract.chart_metrics?.[option.value];
      const allowedUnits = contract.chart_units?.[option.value];
      const sexChart = ["grouped", "stacked", "percent"].includes(option.value);
      option.disabled = Boolean(
        (allowedDimensions && !allowedDimensions.includes(dimension))
        || (allowedMetrics && !allowedMetrics.includes(metric))
        || (allowedUnits && !allowedUnits.includes(unit))
        || (["pie", "doughnut"].includes(option.value) && unit === "persons" && dimension !== "sex")
        || (sexChart && (selected("sex").length || dimension === "sex"))
        || (option.value === "scatter" && multi)
      );
    });
    [...$("#dimension").options].forEach(option => { option.disabled = Boolean(dimensions && !dimensions.includes(option.value)); });
    [...$("#metric").options].forEach(option => { option.disabled = Boolean(metrics && !metrics.includes(option.value)); });
    [...$("#unit").options].forEach(option => { option.disabled = (Boolean(units && !units.includes(option.value)) || (option.value === "persons" && multi)); });
    const bothSexes = ["grouped", "stacked", "percent"].includes(chart);
    $("#sex").disabled = bothSexes;
    if (bothSexes) [...$("#sex").options].forEach(option => { option.selected = false; });
    $("#filter-help").textContent = multi
      ? t("Puedes combinar varios valores. Para personas distintas, selecciona como máximo un valor en cada filtro.")
      : t("Deja un filtro sin selección para incluir todos sus valores; puedes elegir varios.");
    if (dimensions && !dimensions.includes(dimension)) $("#dimension").value = dimensions[0];
    if (metrics && !metrics.includes(metric)) $("#metric").value = metrics[0];
    if (units && !units.includes(unit)) $("#unit").value = units[0];
    if (multi && $("#unit").value === "persons") $("#unit").value = "tumors";
  }

  function terminateWorker() {
    worker?.terminate();
    worker = null;
    workerReleaseId = null;
    workerReady = null;
    if (pendingQuery) {
      pendingQuery.reject(new Error(t("El cálculo local se interrumpió.")));
      pendingQuery = null;
    }
  }

  function ensureWorker() {
    if (worker && workerReleaseId === pkg.release_id && workerReady) return workerReady;
    terminateWorker();
    worker = new Worker("/static/js/offline-worker.js");
    workerReleaseId = pkg.release_id;
    workerReady = new Promise((resolve, reject) => {
      worker.onmessage = ({ data }) => {
        if (data.ready) { resolve(); return; }
        if (pendingQuery) {
          const pending = pendingQuery;
          pendingQuery = null;
          pending.resolve(data);
        }
      };
      worker.onerror = () => {
        const error = new Error(t("El cálculo local encontró un error."));
        workerReady = null;
        if (pendingQuery) { pendingQuery.reject(error); pendingQuery = null; }
        reject(error);
        worker?.terminate();
        worker = null;
        workerReleaseId = null;
      };
    });
    worker.postMessage({
      type: "initialize",
      release: pkg,
      translations: Object.fromEntries(WORKER_MESSAGES),
    });
    return workerReady;
  }

  async function queryLocally(params) {
    if (!pkg) return status(t("Guarda primero la publicación sintética en este dispositivo."), true);
    if (!pkg.query_contract || !pkg.standard_weights) return status(t("Este paquete no incluye el contrato estadístico requerido. Conéctate y actualízalo."), true);
    $("#run-local").disabled = true;
    $("#clear-package").disabled = true;
    status(t("Calculando en este dispositivo…"));
    try {
      await ensureWorker();
      const data = await new Promise((resolve, reject) => {
        pendingQuery = { resolve, reject };
        worker.postMessage({ type: "query", params });
      });
      if (!data.ok) return status(data.error, true);
      lastResult = data;
      lastParams = params;
      pageIndex = 0;
      renderResult(data, params);
      status(fmt("Consulta calculada localmente · publicación %(release)s · método %(method)s.", {release: pkg.release_id, method: pkg.standard_id}));
    } catch (error) {
      status(error.message || t("No se pudo completar el cálculo local."), true);
    } finally {
      $("#run-local").disabled = false;
      $("#clear-package").disabled = false;
    }
  }

  function chartConfig(result, params) {
    const kind = params.chart;
    const circular = ["pie", "doughnut"].includes(kind);
    const horizontal = ["bar", "ranking"].includes(kind);
    const points = ["scatter", "strip", "swarm"].includes(kind);
    const colors = ["#177c70", "#df785d", "#778fb5", "#b89b52", "#8c78ad", "#65a3a5", "#bd7795", "#809763"];
    const datasets = result.datasets.map((dataset, index) => ({
      ...dataset,
      data: points ? dataset.data.map(point => ({
        ...point,
        category: point.category ? displayCategory(point.category) : point.category,
        categories: point.categories?.map(displayCategory),
      })) : dataset.data,
      backgroundColor: circular ? colors : colors[index % colors.length],
      borderColor: colors[index % colors.length],
      borderWidth: kind === "line" ? 2 : 0,
      borderRadius: circular || ["stacked", "percent"].includes(kind) || points ? 0 : 4,
      pointRadius: points ? 6 : undefined,
      tension: 0,
    }));
    if (points && kind === "scatter") {
      datasets[0].data = datasets[0].data.map(point => ({ ...point, y: point.y ?? 0 }));
    }
    return {
      type: circular ? kind : kind === "line" ? "line" : points ? "scatter" : "bar",
      data: { labels: result.rows.map(row => displayCategory(row.label)), datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        locale: document.documentElement.lang || "es",
        animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 250 },
        indexAxis: horizontal ? "y" : "x",
        plugins: {
          legend: { display: circular || datasets.length > 1, position: "bottom" },
          title: { display: true, text: [METRIC_LABELS[params.metric], DIMENSION_LABELS[params.dimension]].join(" · ") },
          subtitle: { display: true, text: fmt("Publicación %(release)s · %(date)s", {release: pkg.release_id, date: displayDateTime(pkg.published_at)}) },
        },
        scales: circular ? {} : points && kind === "scatter" ? {
          x: { type: "linear", beginAtZero: true, title: { display: true, text: t("Tumores") } },
          y: { type: "linear", beginAtZero: true, title: { display: true, text: t("Personas distintas") } },
        } : points ? {
          x: { type: "linear", beginAtZero: true, title: { display: true, text: METRIC_LABELS[params.metric] } },
          y: { type: "linear", min: -0.5, max: Math.max(0.5, result.rows.length - 0.5), reverse: true, ticks: { stepSize: 1, callback: value => displayCategory(result.rows[Math.round(value)]?.label || "") } },
        } : {
          x: { stacked: ["stacked", "percent"].includes(kind), beginAtZero: true },
          y: { stacked: ["stacked", "percent"].includes(kind), beginAtZero: true, max: kind === "percent" ? 100 : undefined },
        },
      },
    };
  }

  function renderTable(result, params) {
    const body = $("#offline-results tbody");
    body.replaceChildren();
    const headers = params.chart === "ranking" ? [t("Posición")] : [];
    headers.push(t("Categoría"), t("Tumores"), t("Personas distintas"), t("Población denominadora"), t("Frecuencia relativa (%)"), t("Tasa cruda/específica por 100 000"), t("Tasa ajustada por 100 000"));
    if (result.rows[0]?.series) headers.push(...result.rows[0].series.map(item => `${item.label}${params.chart === "percent" ? " (%)" : ""}`));
    const head = $("#offline-results thead");
    head.replaceChildren();
    const headerRow = document.createElement("tr");
    for (const heading of headers) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = heading;
      headerRow.append(th);
    }
    head.append(headerRow);
    const start = printAll ? 0 : pageIndex * PAGE_SIZE;
    const pageRows = printAll ? result.rows : result.rows.slice(start, start + PAGE_SIZE);
    for (const [offset, row] of pageRows.entries()) {
      const tr = document.createElement("tr");
      if (params.chart === "ranking") {
        const rank = document.createElement("td");
        rank.textContent = integerFormat.format(row.rank || start + offset + 1);
        tr.append(rank);
      }
      const label = document.createElement("th");
      label.scope = "row";
      label.textContent = displayCategory(row.label);
      tr.append(label);
      const cells = [
        [row.tumors, true], [row.persons ?? t("No disponible"), true], [row.population, true],
        [row.relative_frequency, false], [row.crude_rate, false], [row.adjusted_rate, false],
      ];
      cells.forEach(([value, integer]) => {
        const td = document.createElement("td");
        td.textContent = value === null || value === undefined ? "—"
          : typeof value === "number" ? (integer ? integerFormat : decimalFormat).format(value)
          : String(value);
        tr.append(td);
      });
      if (row.series) row.series.forEach(item => {
        const td = document.createElement("td");
        td.textContent = (params.metric === "count" ? integerFormat : decimalFormat).format(item.value);
        tr.append(td);
      });
      body.append(tr);
    }
    const pageCount = Math.max(1, Math.ceil(result.rows.length / PAGE_SIZE));
    const countLabel = plural("categoría", "categorías", result.rows.length);
    $("#page-indicator").textContent = printAll ? `${numberFormat.format(result.rows.length)} ${countLabel}` : fmt("Página %(page)s de %(pages)s · %(count)s %(categories)s", {page: numberFormat.format(pageIndex + 1), pages: numberFormat.format(pageCount), count: numberFormat.format(result.rows.length), categories: countLabel});
    $("#previous-page").disabled = pageIndex === 0 || printAll;
    $("#next-page").disabled = pageIndex + 1 >= pageCount || printAll;
    $("#table-pagination").hidden = result.rows.length <= PAGE_SIZE;
  }

  function renderResult(result, params) {
    const chart = window.Chart;
    if (!chart) return status(t("No se pudo cargar la biblioteca local de gráficos."), true);
    const previous = chart.getChart($("#offline-chart"));
    previous?.destroy();
    window.offlineChart = new chart($("#offline-chart"), chartConfig(result, params));
    if (["grouped", "stacked", "percent"].includes(params.chart)) {
      result.rows.forEach((row, index) => {
        row.series = result.datasets.map(dataset => ({ label: dataset.label, value: dataset.data[index] }));
      });
    }
    const persons = result.summary.persons === null ? t("no disponible para filtros múltiples") : result.summary.persons;
    $("#offline-summary").textContent = fmt("Tumores: %(tumors)s · Personas distintas: %(persons)s · Población: %(population)s · cálculo local: %(elapsed)s ms", {tumors: numberFormat.format(result.summary.tumors), persons: typeof persons === "number" ? numberFormat.format(persons) : persons, population: numberFormat.format(result.summary.population), elapsed: numberFormat.format(result.elapsed)});
    $("#offline-filter-summary").textContent = FILTERS.map(key => {
      const labels = selected(key);
      return `${$("label[for='${key}']")?.textContent || key}: ${labels.length ? labels.join(", ") : t("Todos")}`;
    }).join(" · ");
    renderTable(result, params);
    $("#offline-results").dataset.chart = params.chart;
    $("#offline-results").dataset.metric = params.metric;
    $("#export-csv").disabled = result.rows.length === 0;
    $("#export-png").disabled = result.rows.length === 0;
    $("#print-results").disabled = result.rows.length === 0;
  }

  function csvCell(value) {
    const text = value === null || value === undefined ? "" : String(value);
    return `"${text.replaceAll('"', '""')}"`;
  }
  function download(filename, content, type) {
    const url = URL.createObjectURL(new Blob([content], { type }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportCsv() {
    if (!lastResult || !lastParams) return;
    const params = lastParams;
    const queryLabels = FILTERS.map(key => `${t(FILTER_LABELS[key])}=${params[key].map(displayCategory).join("|") || t("todos")}`);
    const headers = params.chart === "ranking" ? [t("Posición")] : [];
    headers.push(t("Categoría"), t("Tumores"), t("Personas distintas"), t("Población denominadora"), t("Frecuencia relativa (%)"), t("Tasa cruda/específica por 100 000"), t("Tasa ajustada por 100 000"));
    if (lastResult.rows[0]?.series) headers.push(...lastResult.rows[0].series.map(item => displayCategory(item.label)));
    const records = lastResult.rows.map(row => {
      const values = params.chart === "ranking" ? [row.rank] : [];
      values.push(displayCategory(row.label), row.tumors, row.persons, row.population, row.relative_frequency, row.crude_rate, row.adjusted_rate);
      if (row.series) values.push(...row.series.map(item => item.value));
      return values.map(csvCell).join(",");
    });
    const metadata = [
      [t("Datos sintéticos"), t("Sí")],
      [t("Publicación"), pkg.release_id],
      [t("Título"), pkg.title],
      [t("Fecha de publicación"), pkg.published_at || t("No disponible")],
      [t("Método"), pkg.standard_id],
      [t("Dimensión"), pkg.query_contract.dimensions[params.dimension]],
      [t("Indicador"), pkg.query_contract.metrics[params.metric]],
      [t("Unidad"), t(params.unit === "persons" ? "Personas distintas" : "Tumores")],
      [t("Filtros"), queryLabels.join("; ")],
    ];
    const text = `\ufeff${metadata.map(row => row.map(csvCell).join(",")).join("\r\n")}\r\n\r\n${headers.map(csvCell).join(",")}\r\n${records.join("\r\n")}`;
    download(`${t("consulta-local")}-${pkg.release_id}.csv`, text, "text/csv;charset=utf-8");
  }

  async function saveCurrentPackage() {
    const button = $("#save-package");
    button.disabled = true;
    try {
      const response = await fetch("/paquete-offline.json", { cache: "no-store", credentials: "omit" });
      if (!response.ok) throw new Error(t("No hay publicación disponible para guardar."));
      const next = await response.json();
      if (next.synthetic !== true) throw new Error(t("Este prototipo solo admite el paquete sintético autorizado para pruebas."));
      if (!next.query_contract || !next.standard_weights || !next.release_id || !next.published_at) throw new Error(t("El paquete está incompleto y no se guardó."));
      next.bytes = new Blob([JSON.stringify(next)]).size;
      await savePackage(next);
      terminateWorker();
      pkg = next;
      try { await navigator.storage?.persist?.(); } catch { /* Browser policy may decline persistent storage. */ }
      renderPackage();
      await storageInfo();
      status(t("Publicación sintética guardada en este dispositivo. El navegador puede retirar datos locales por cuota o configuración."));
    } catch (error) {
      status(error.message || t("No se pudo guardar la publicación."), true);
    } finally {
      button.disabled = false;
    }
  }

  async function compareWithServer() {
    const params = queryParams();
    const query = new URLSearchParams();
    for (const key of FILTERS) params[key].forEach(value => query.append(key, value));
    for (const key of ["dimension", "chart", "unit", "metric"]) query.set(key, params[key]);
    const start = performance.now();
    try {
      const response = await fetch(`/consulta/?${query}`, { cache: "no-store", credentials: "omit" });
      const html = await response.text();
      if (!response.ok) throw new Error(fmt("El servidor respondió HTTP %(status)s.", {status: response.status}));
      status(fmt("Servidor: %(elapsed)s ms de ida y vuelta · %(bytes)s bytes de HTML. No mide CPU del servidor.", {elapsed: (performance.now() - start).toFixed(1), bytes: new Blob([html]).size}));
    } catch {
      status(t("El servidor no respondió; la consulta local sigue disponible si ya guardaste el paquete."), true);
    }
  }

  async function init() {
    window.addEventListener("beforeinstallprompt", event => {
      event.preventDefault();
      installPrompt = event;
      $("#install-pwa").hidden = false;
    });
    $("#install-pwa").addEventListener("click", async () => {
      if (!installPrompt) return;
      installPrompt.prompt();
      await installPrompt.userChoice;
      installPrompt = null;
      $("#install-pwa").hidden = true;
    });
    try {
      await dbOpen();
      pkg = await loadPackage();
      renderPackage();
    } catch {
      status(t("Este navegador no permite el almacenamiento local requerido por la consulta offline."), true);
    }
    await storageInfo();
    $("#save-package").addEventListener("click", saveCurrentPackage);
    $("#run-local").addEventListener("click", () => queryLocally(queryParams()));
    $("#compare-online").addEventListener("click", compareWithServer);
    $("#clear-package").addEventListener("click", async () => {
      try {
        terminateWorker();
        await deletePackage();
        pkg = null;
        lastResult = null;
        renderPackage();
        $("#offline-results tbody").replaceChildren();
        window.Chart?.getChart($("#offline-chart"))?.destroy();
        $("#offline-summary").textContent = "";
        status(t("Se eliminó el paquete local de este navegador."));
        await storageInfo();
      } catch {
        status(t("No se pudo eliminar el paquete local."), true);
      }
    });
    $("#export-csv").addEventListener("click", exportCsv);
    $("#export-png").addEventListener("click", () => {
      const chart = window.Chart?.getChart($("#offline-chart"));
      if (chart) {
        const base64 = chart.toBase64Image().split(",")[1];
        if (base64) download(`${t("grafico-local")}-${pkg.release_id}.png`, Uint8Array.from(atob(base64), character => character.charCodeAt(0)), "image/png");
      }
    });
    $("#print-results").addEventListener("click", () => window.print());
    $("#previous-page").addEventListener("click", () => { pageIndex = Math.max(0, pageIndex - 1); renderTable(lastResult, lastParams); });
    $("#next-page").addEventListener("click", () => { pageIndex += 1; renderTable(lastResult, lastParams); });
    window.addEventListener("beforeprint", () => { printAll = true; if (lastResult) renderTable(lastResult, lastParams); });
    window.addEventListener("afterprint", () => { printAll = false; if (lastResult) renderTable(lastResult, lastParams); });
    [...document.querySelectorAll("#filters select, #dimension, #chart-kind, #metric, #unit")]
      .forEach(element => element.addEventListener("change", syncCompatibility));
  }

  document.addEventListener("DOMContentLoaded", init);
})();
