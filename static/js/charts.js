"use strict";
(() => {
  const element = document.getElementById("chart-payload");
  const canvas = document.getElementById("result-chart");
  if (!element || !canvas || typeof Chart === "undefined") return;
  const payload = JSON.parse(element.textContent);
  const colors = ["#177c70", "#df785d", "#778fb5", "#b89b52", "#8c78ad", "#65a3a5", "#bd7795", "#809763"];
  const kind = payload.type;
  const circular = ["pie", "doughnut"].includes(kind);
  const stacked = ["stacked", "percent"].includes(kind);
  const metricLabel = payload.metric || payload.title || "Consulta estadística";
  const unitLabel = payload.unit || "";
  const dimensionLabel = payload.dimension_label || payload.title || "Categoría";
  const axisUnit = payload.axis_unit || unitLabel;
  const numberFormat = new Intl.NumberFormat("es-ES", {maximumFractionDigits: 2});
  const valueLabels = {
    id: "rncValueLabels",
    afterDatasetsDraw(renderedChart) {
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
          if (kind === "bar") {
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
    type: circular ? kind : kind === "line" ? "line" : "bar",
    data: {
      labels: payload.labels,
      datasets: payload.datasets.map((dataset, index) => ({
        ...dataset,
        backgroundColor: circular ? colors : colors[index % colors.length],
        borderColor: colors[index % colors.length],
        borderWidth: kind === "line" ? 2 : 0,
        borderRadius: circular || stacked ? 0 : 4,
        tension: 0,
      })),
    },
    plugins: [valueLabels],
    options: {
      responsive: true, maintainAspectRatio: false,
      indexAxis: kind === "bar" ? "y" : "x",
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : {duration: 250},
      plugins: {
        legend: {display: circular || payload.datasets.length > 1, position: "bottom"},
        title: {display: true, text: [metricLabel, unitLabel].filter(Boolean).join(" · "), color: "#183f39", font: {size: 17}},
        subtitle: {display: true, text: [dimensionLabel, payload.filter_summary || payload.note].filter(Boolean), color: "#526963", font: {size: 12}},
      },
      scales: circular ? {} : {
        x: {
          stacked, beginAtZero: true, grid: {display: kind === "bar"},
          title: {display: true, text: kind === "bar" ? axisUnit : dimensionLabel, color: "#526963"},
          ticks: {color: "#526963"},
        },
        y: {
          stacked, beginAtZero: true, max: kind === "percent" ? 100 : undefined,
          title: {display: true, text: kind === "bar" ? dimensionLabel : (kind === "percent" ? "Porcentaje de cada categoría (%)" : axisUnit), color: "#526963"},
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
