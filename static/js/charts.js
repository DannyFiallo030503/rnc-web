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
  new Chart(canvas, {
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
    options: {
      responsive: true, maintainAspectRatio: false,
      indexAxis: kind === "bar" ? "y" : "x",
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : {duration: 250},
      plugins: {
        legend: {display: circular || payload.datasets.length > 1, position: "bottom"},
        title: {display: true, text: payload.title, color: "#183f39", font: {size: 17}},
      },
      scales: circular ? {} : {
        x: {stacked, beginAtZero: true, grid: {display: kind === "bar"}, ticks: {color: "#526963"}},
        y: {stacked, beginAtZero: true, max: kind === "percent" ? 100 : undefined, ticks: {color: "#526963"}},
      },
    },
  });
})();
