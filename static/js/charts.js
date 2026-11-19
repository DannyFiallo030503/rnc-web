"use strict";
(() => {
  function render(payload, canvas) {
  if (!canvas || typeof Chart === "undefined") return null;
  Chart.getChart(canvas)?.destroy();
const t = message => window.gettext ? window.gettext(message) : message;
const plural = (singular, many, count) => window.ngettext ? window.ngettext(singular, many, count) : (count === 1 ? singular : many);
  const colors = ["#177c70", "#df785d", "#778fb5", "#b89b52", "#8c78ad", "#65a3a5", "#bd7795", "#809763"];
  const kind = payload.type;
  const line = ["line", "trend", "curve"].includes(kind);
  const circular = ["pie", "doughnut"].includes(kind);
  const layout = window.RncChartLayout.prepare(canvas, kind, payload.labels);
  const horizontal = layout.horizontal;
  const scatter = kind === "scatter";
  const points = scatter || ["strip", "swarm"].includes(kind);
  const strip = kind === "strip";
  const stacked = ["stacked", "percent"].includes(kind);
const metricLabel = payload.metric || payload.title || t("Consulta estadística");
  const unitLabel = payload.unit || "";
const dimensionLabel = payload.dimension_label || payload.title || t("Categoría");
  const axisUnit = payload.axis_unit || unitLabel;
const numberFormat = new Intl.NumberFormat(document.documentElement.lang || "es", {maximumFractionDigits: 2});
  const collapseCoincidentScatterPoints = data => {
    const grouped = new Map();
    data.forEach(point => {
      const key = `${point.x}:${point.y}`;
      if (!grouped.has(key)) grouped.set(key, {x: point.x, y: point.y, categories: []});
      grouped.get(key).categories.push(point.category);
    });
    return [...grouped.values()].map(point => ({
      ...point,
      overlap: point.categories.length,
      category: point.categories.length === 1 ? point.categories[0] : `${point.categories.length} ${plural("categoría", "categorías", point.categories.length)}`,
    }));
  };
  const valueLabels = {
    id: "rncValueLabels",
    afterDatasetsDraw(renderedChart) {
      if (renderedChart.options.plugins.rncValueLabels?.display === false) return;
      if (points) return;
      const {ctx, chartArea} = renderedChart;
      const occupied = [];
      ctx.save();
      ctx.font = "600 11px system-ui, sans-serif";
      ctx.fillStyle = "#183f39";
      ctx.textBaseline = "middle";
      renderedChart.data.datasets.forEach((dataset, datasetIndex) => {
        const meta = renderedChart.getDatasetMeta(datasetIndex);
        meta.data.forEach((element, dataIndex) => {
          const value = dataset.data[dataIndex];
          if (value === null || value === undefined || Number(value) === 0) return;
          const label = `${numberFormat.format(Number(value))}${kind === "percent" || (circular && metricLabel.includes("%")) ? "%" : ""}`;
          if (line && dataIndex % Math.max(1, Math.ceil(payload.labels.length / 16))) return;
          if (circular) {
            if (element.circumference < 0.28) return;
            const point = element.tooltipPosition();
            ctx.fillStyle = dataIndex === 0 ? "#ffffff" : "#183f39";
            ctx.textAlign = "center";
            ctx.fillText(label, point.x, point.y);
            return;
          }
          const props = element.getProps(["x", "y", "base", "width", "height"], true);
          if ((kind === "stacked" || kind === "percent") && (props.height < 18 || props.width < 22)) return;
          if (horizontal && !stacked) {
            const atEdge = props.x > chartArea.right - 38;
            ctx.textAlign = atEdge ? "right" : "left";
            ctx.fillStyle = atEdge ? "#ffffff" : "#183f39";
            ctx.fillText(label, props.x + (atEdge ? -5 : 6), props.y);
          } else if (kind === "stacked" || kind === "percent") {
            ctx.textAlign = "center";
            ctx.fillStyle = datasetIndex === 0 ? "#ffffff" : "#183f39";
            ctx.fillText(label, horizontal ? (props.x + props.base) / 2 : props.x, horizontal ? props.y : props.y + props.height / 2);
          } else {
            ctx.textAlign = "center";
            const x = props.x, y = Math.max(chartArea.top + 10, props.y - 9), width = ctx.measureText(label).width;
            const box = {left:x-width/2-3, right:x+width/2+3, top:y-9, bottom:y+9};
            if (occupied.some(other => box.left<other.right && box.right>other.left && box.top<other.bottom && box.bottom>other.top)) return;
            occupied.push(box);
            ctx.fillText(label, x, y);
          }
        });
      });
      ctx.restore();
    },
  };
  const chart = new Chart(canvas, {
    type: circular ? kind : line ? "line" : points ? "scatter" : "bar",
    data: {
      labels: payload.labels,
      datasets: payload.datasets.map((dataset, index) => ({
        ...dataset,
        data: scatter ? collapseCoincidentScatterPoints(dataset.data) : dataset.data,
        backgroundColor: circular ? colors : colors[index % colors.length],
        borderColor: colors[index % colors.length],
        borderWidth: line ? 2 : 0,
        borderRadius: circular || stacked || points ? 0 : 4,
        pointRadius: scatter ? context => Math.min(16, 6 + 2 * Math.sqrt((context.raw?.overlap || 1) - 1)) : points ? Math.max(2, Math.min(6, 90 / Math.sqrt(payload.labels.length || 1))) : line ? (payload.labels.length > 30 ? 2 : 3) : undefined,
        pointHoverRadius: points ? 9 : undefined,
        pointBorderColor: scatter ? "#ffffff" : undefined,
        pointBorderWidth: scatter ? 1.5 : undefined,
        tension: kind === "curve" ? 0.35 : 0,
        cubicInterpolationMode: kind === "curve" ? "monotone" : "default",
      })),
    },
    plugins: [valueLabels],
    options: {
      responsive: true, maintainAspectRatio: false, devicePixelRatio:layout.pixelRatio,
      locale: document.documentElement.lang || "es",
      indexAxis: horizontal ? "y" : "x",
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : {duration: 250},
      plugins: {
        legend: {display: circular || payload.datasets.length > 1, position: "bottom", labels: {generateLabels: chart => (circular ? Chart.overrides[kind].plugins.legend.labels.generateLabels : Chart.defaults.plugins.legend.labels.generateLabels)(chart).map(item => ({...item, text: item.text.length > 36 ? item.text.slice(0,33) + "…" : item.text}))}, onHover: (_event,item) => {canvas.title = circular ? payload.labels[item.index] : item.text;}, onLeave: () => {canvas.title = "";}},
        title: {display: true, text: [metricLabel, unitLabel].filter(Boolean).join(" · "), color: "#183f39", font: {size: 17}},
        subtitle: {display: true, text: [dimensionLabel, ...window.RncChartLayout.wrap(payload.filter_summary || payload.note || "", 90)].filter(Boolean), color: "#526963", font: {size: 12}},
        tooltip: scatter ? {callbacks: {
          title: items => {
            const categories=items[0]?.raw?.categories || [];
            return categories.length>1 ? `${categories.length} ${plural("categoría con el mismo valor", "categorías con los mismos valores", categories.length)}` : (categories[0] || t("Categoría"));
          },
          label: context => `${numberFormat.format(context.raw.x)} ${t("tumores")} · ${numberFormat.format(context.raw.y)} ${t("personas distintas")}`,
          afterBody: items => (items[0]?.raw?.categories || []).length>1 ? [t("Categorías"), ...items[0].raw.categories] : [],
        }} : points ? {callbacks: {label: context => `${context.raw.category}: ${numberFormat.format(context.raw.x)} ${axisUnit}`}} : {},
      },
      scales: circular ? {} : scatter ? {
        x: {type: "linear", beginAtZero: true, suggestedMax: Math.max(1, ...payload.datasets.flatMap(dataset => dataset.data.map(point => point.x))) * 1.12, title: {display: true, text: axisUnit, color: "#526963"}, ticks: {color: "#526963"}},
        y: {type: "linear", beginAtZero: true, suggestedMax: Math.max(1, ...payload.datasets.flatMap(dataset => dataset.data.map(point => point.y))) * 1.18, title: {display: true, text: payload.y_axis_unit, color: "#526963"}, ticks: {color: "#526963"}},
      } : points ? {
        x: {type: "linear", beginAtZero: true, title: {display: true, text: axisUnit, color: "#526963"}, ticks: {color: "#526963"}},
        y: {
          type: "linear",
          min: -0.5,
          max: Math.max(0.5, payload.labels.length - 0.5),
          reverse: true,
          title: {display: true, text: dimensionLabel, color: "#526963"},
          ticks: {autoSkip:false, stepSize: 1, color: "#526963", callback: value => layout.wrapped[Math.round(value)] || ""},
          grid: {display: false},
        },
      } : {
        x: {
          stacked, beginAtZero: true, max: horizontal && kind === "percent" ? 100 : undefined, grid: {display: horizontal},
          title: {display: true, text: horizontal ? axisUnit : dimensionLabel, color: "#526963"},
          ticks: {color: "#526963", maxRotation: 0, autoSkip: horizontal, callback: horizontal ? undefined : value => window.RncChartLayout.wrap(payload.labels[value] || "", 16)},
        },
        y: {
          stacked, beginAtZero: true, max: !horizontal && kind === "percent" ? 100 : undefined,
          title: {display: true, text: horizontal ? dimensionLabel : (kind === "percent" ? t("Porcentaje de cada categoría (%)") : axisUnit), color: "#526963"},
          ticks: {color: "#526963", autoSkip: !horizontal, callback: horizontal ? value => layout.wrapped[value] || "" : undefined},
        },
      },
    },
  });
  // Recompute when an initially off-screen canvas first becomes visible.
  if ("IntersectionObserver" in window) {
    const observer=new IntersectionObserver(entries=>{
      if(entries.some(entry=>entry.isIntersecting)) { chart.resize();chart.update("none");observer.disconnect(); }
    },{threshold:0.05});
    observer.observe(canvas);
  }
  return chart;
  }
  window.RncCharts = {render};
  const element = document.getElementById("chart-payload"), canvas = document.getElementById("result-chart");
  if (element && canvas) render(JSON.parse(element.textContent),canvas);
})();
