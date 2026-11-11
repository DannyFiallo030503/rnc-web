"use strict";
(() => {
  const element = document.getElementById("chart-payload");
  const canvas = document.getElementById("result-chart");
  if (!element || !canvas || typeof Chart === "undefined") return;
const t = message => window.gettext ? window.gettext(message) : message;
const plural = (singular, many, count) => window.ngettext ? window.ngettext(singular, many, count) : (count === 1 ? singular : many);
  const payload = JSON.parse(element.textContent);
  const colors = ["#177c70", "#df785d", "#778fb5", "#b89b52", "#8c78ad", "#65a3a5", "#bd7795", "#809763"];
  const kind = payload.type;
  const circular = ["pie", "doughnut"].includes(kind);
  const horizontal = ["bar", "ranking"].includes(kind);
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
      if (points) return;
      const {ctx, chartArea} = renderedChart;
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
          if (circular) {
            const point = element.tooltipPosition();
            ctx.fillStyle = dataIndex === 0 ? "#ffffff" : "#183f39";
            ctx.textAlign = "center";
            ctx.fillText(label, point.x, point.y);
            return;
          }
          const props = element.getProps(["x", "y", "base", "width", "height"], true);
          if ((kind === "stacked" || kind === "percent") && (props.height < 18 || props.width < 22)) return;
          if (horizontal) {
            const atEdge = props.x > chartArea.right - 38;
            ctx.textAlign = atEdge ? "right" : "left";
            ctx.fillStyle = atEdge ? "#ffffff" : "#183f39";
            ctx.fillText(label, props.x + (atEdge ? -5 : 6), props.y);
          } else if (kind === "stacked" || kind === "percent") {
            ctx.textAlign = "center";
            ctx.fillStyle = datasetIndex === 0 ? "#ffffff" : "#183f39";
            ctx.fillText(label, props.x, props.y + props.height / 2);
          } else {
            ctx.textAlign = "center";
            ctx.fillText(label, props.x, Math.max(chartArea.top + 10, props.y - 9));
          }
        });
      });
      ctx.restore();
    },
  };
  const chart = new Chart(canvas, {
    type: circular ? kind : kind === "line" ? "line" : points ? "scatter" : "bar",
    data: {
      labels: payload.labels,
      datasets: payload.datasets.map((dataset, index) => ({
        ...dataset,
        data: scatter ? collapseCoincidentScatterPoints(dataset.data) : dataset.data,
        backgroundColor: circular ? colors : colors[index % colors.length],
        borderColor: colors[index % colors.length],
        borderWidth: kind === "line" ? 2 : 0,
        borderRadius: circular || stacked || points ? 0 : 4,
        pointRadius: scatter ? context => Math.min(16, 6 + 2 * Math.sqrt((context.raw?.overlap || 1) - 1)) : points ? 6 : undefined,
        pointHoverRadius: points ? 9 : undefined,
        pointBorderColor: scatter ? "#ffffff" : undefined,
        pointBorderWidth: scatter ? 1.5 : undefined,
        tension: 0,
      })),
    },
    plugins: [valueLabels],
    options: {
      responsive: true, maintainAspectRatio: false,
      locale: document.documentElement.lang || "es",
      indexAxis: horizontal ? "y" : "x",
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : {duration: 250},
      plugins: {
        legend: {display: circular || payload.datasets.length > 1, position: "bottom"},
        title: {display: true, text: [metricLabel, unitLabel].filter(Boolean).join(" · "), color: "#183f39", font: {size: 17}},
        subtitle: {display: true, text: [dimensionLabel, payload.filter_summary || payload.note].filter(Boolean), color: "#526963", font: {size: 12}},
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
          ticks: {stepSize: 1, color: "#526963", callback: value => payload.labels[Math.round(value)] || ""},
          grid: {display: false},
        },
      } : {
        x: {
          stacked, beginAtZero: true, grid: {display: horizontal},
          title: {display: true, text: horizontal ? axisUnit : dimensionLabel, color: "#526963"},
          ticks: {color: "#526963"},
        },
        y: {
          stacked, beginAtZero: true, max: kind === "percent" ? 100 : undefined,
          title: {display: true, text: horizontal ? dimensionLabel : (kind === "percent" ? t("Porcentaje de cada categoría (%)") : axisUnit), color: "#526963"},
          ticks: {color: "#526963"},
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
})();
