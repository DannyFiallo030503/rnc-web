"use strict";
(() => {
  const wrap = (text, width = 34) => {
    const words = String(text).split(/\s+/), lines = [];
    let line = "";
    for (let word of words) {
      if (line && line.length + word.length + 1 > width) { lines.push(line); line = ""; }
      while (word.length > width) { if (line) { lines.push(line); line = ""; } lines.push(word.slice(0, width)); word = word.slice(width); }
      line = line ? `${line} ${word}` : word;
    }
    if (line) lines.push(line);
    return lines.length ? lines : [""];
  };
  function prepare(canvas, kind, labels) {
    const horizontal = ["bar", "ranking", "strip", "swarm"].includes(kind) || (["grouped", "stacked", "percent"].includes(kind) && labels.length > 10);
    const frame = canvas.parentElement;
    let viewport = frame.parentElement;
    if (!viewport.classList.contains("chart-scroll")) {
      viewport = document.createElement("div"); viewport.className = "chart-scroll";
      frame.before(viewport); viewport.append(frame);
      viewport.tabIndex = 0; viewport.setAttribute("role", "region");
      viewport.setAttribute("aria-label", canvas.getAttribute("aria-label") || "Gráfico");
    }
    const width = viewport.clientWidth || 800;
    const wrapped = labels.map(label => wrap(label, width < 600 ? 26 : 40));
    const rowHeight = Math.max(34, ...wrapped.map(lines => lines.length * 15 + 14));
    frame.style.height = `${horizontal ? Math.max(390, labels.length * rowHeight + 150) : 460}px`;
    // Preserve room for each category instead of compressing columns into the viewport.
    const categoricalX = ["column", "line", "trend", "curve", "grouped", "stacked", "percent"].includes(kind);
    const categoryWidth = labels.length * 112 + 80;
    const minWidth = horizontal ? 650 : categoricalX && categoryWidth > width ? categoryWidth : 0;
    frame.style.minWidth = `${minWidth}px`;
    frame.style.maxWidth = "none"; frame.style.margin = "0";
    return {horizontal, wrapped, pixelRatio:Math.min(window.devicePixelRatio || 1, 16000 / parseFloat(frame.style.height), 16000 / Math.max(width, minWidth))};
  }
  function composition(labels, datasets, otherLabel) {
    if (labels.length <= 8) return {labels, datasets, grouped: false};
    const order = labels.map((label, index) => ({label, index, value: Number(datasets[0].data[index])})).sort((a,b) => b.value-a.value);
    return {
      labels: [...order.slice(0,7).map(item => item.label), otherLabel],
      datasets: datasets.map(dataset => ({...dataset, data:[...order.slice(0,7).map(item => dataset.data[item.index]), order.slice(7).reduce((sum,item) => sum + Number(dataset.data[item.index]),0)]})),
      grouped: true,
    };
  }
  window.RncChartLayout = {wrap, prepare, composition};
})();
