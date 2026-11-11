"use strict";

const FILTER_FIELDS = {
  year: "period",
  territory: "territory",
  municipality: "municipality",
  sex: "sex",
  age: "age_group",
  site: "site",
};
const FILTER_KEYS = Object.keys(FILTER_FIELDS);
let activeTranslations = {};
const t = message => activeTranslations[message] || message;
const fmt = (message, values) => t(message).replace(/%\((\w+)\)s/g, (_, key) => values[key]);
const METRIC_LABELS = {
  count: "Frecuencia absoluta",
  share: "Frecuencia relativa (%)",
  rate: "Tasa cruda / específica por 100 000",
  asr: "Tasa ajustada Segi–Doll por 100 000",
};

function values(value) {
  if (value === undefined || value === null || value === "") return [];
  return (Array.isArray(value) ? value : [value]).filter(item => item !== "").map(String);
}

function hasMultiple(conditions) {
  return Object.values(conditions).some(selection => selection.length > 1);
}

function conditionsFor(params) {
  const conditions = {};
  for (const [key, field] of Object.entries(FILTER_FIELDS)) {
    const selected = values(params[key]);
    if (selected.length) conditions[field] = selected;
  }
  return conditions;
}

function cubeKey(cube, fields, conditions) {
  const key = fields.filter(field => Object.hasOwn(conditions, field)).join(",");
  return Object.hasOwn(cube, key) ? key : null;
}

function matches(cell, conditions) {
  return Object.entries(conditions).every(([field, selected]) =>
    !selected.length || selected.includes(String(cell[field]))
  );
}

function selectedCells(release, conditions) {
  const key = cubeKey(release.cube, release.fields, conditions);
  return key === null ? [] : release.cube[key].filter(cell => matches(cell, conditions));
}

function summary(release, conditions) {
  const cells = selectedCells(release, conditions);
  const multiple = hasMultiple(conditions);
  return {
    tumors: cells.reduce((total, cell) => total + Number(cell.tumors || 0), 0),
    persons: multiple ? null : cells.reduce((total, cell) => total + Number(cell.persons || 0), 0),
    population: cells.reduce((total, cell) => total + Number(cell.population || 0), 0),
  };
}

function metricCount(summaryResult, unit) {
  return unit === "persons" ? summaryResult.persons : summaryResult.tumors;
}

function directAdjustedRate(release, conditions, dimension, label, unit) {
  if (Object.hasOwn(conditions, "age_group") || dimension === "age_group") return null;
  const caseBase = { ...conditions };
  delete caseBase.age_group;
  const populationBase = { ...conditions };
  delete populationBase.age_group;
  delete populationBase.site;
  if (dimension !== "site") {
    caseBase[dimension] = [label];
    populationBase[dimension] = [label];
  } else {
    caseBase.site = [label];
  }

  let weightedRate = 0;
  let totalWeight = 0;
  for (const [age, weightValue] of Object.entries(release.standard_weights || {})) {
    const caseConditions = { ...caseBase, age_group: [age] };
    const populationConditions = { ...populationBase, age_group: [age] };
    const cases = metricCount(summary(release, caseConditions), unit);
    const population = summary(release, populationConditions).population;
    if (cases === null || population <= 0) return null;
    const weight = Number(weightValue);
    weightedRate += cases / population * weight;
    totalWeight += weight;
  }
  return totalWeight > 0 ? round2(weightedRate / totalWeight * 100000) : null;
}

function round2(value) {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function validate(release, params) {
  const contract = release.query_contract || {};
  const chart = params.chart || "bar";
  const dimension = params.dimension || "site";
  const metric = params.metric || "count";
  const unit = params.unit || "tumors";
  const conditions = conditionsFor(params);
  const selected = Object.fromEntries(FILTER_KEYS.map(key => [key, values(params[key])]));
  const errors = [];
  const dimensions = contract.chart_dimensions?.[chart];
  const metrics = contract.chart_metrics?.[chart];
  const units = contract.chart_units?.[chart];

  if (dimensions && !dimensions.includes(dimension)) errors.push(t("dimensión"));
  if (metrics && !metrics.includes(metric)) errors.push(t("indicador"));
  if (units && !units.includes(unit)) errors.push(t("unidad"));
  if (unit === "persons" && hasMultiple(conditions)) errors.push(t("personas distintas con selección múltiple"));
  if (metric === "asr" && (selected.age.length || dimension === "age_group")) errors.push(t("ajuste por edad incompatible con la selección"));
  if (["pie", "doughnut"].includes(chart) && unit === "persons" && dimension !== "sex") errors.push(t("composición de personas solo por sexo"));
  if (["grouped", "stacked", "percent"].includes(chart) && (selected.sex.length || dimension === "sex")) errors.push(t("comparación por sexo necesita ambos sexos"));
  if (chart === "scatter" && hasMultiple(conditions)) errors.push(t("dispersión requiere filtros simples"));

  for (const key of FILTER_KEYS) {
    const allowed = release.options?.[key === "year" ? "period" : key === "age" ? "age_group" : key];
    if (allowed && selected[key].some(value => !allowed.map(String).includes(value))) errors.push(fmt("valor de %(key)s fuera del paquete", {key}));
  }
  if (["grouped", "stacked", "percent"].includes(chart)
    && !["Mujeres", "Hombres"].every(sex => (release.options?.sex || []).map(String).includes(sex))) {
    errors.push(t("la publicación no contiene ambos sexos"));
  }
  return { errors, conditions, chart, dimension, metric, unit };
}

function runQuery(release, params) {
  const query = validate(release, params);
  if (query.errors.length) throw new Error(fmt("Selección no compatible: %(errors)s.", {errors: query.errors.join(", ")}));
  const { conditions, chart, dimension, metric, unit } = query;
  const multiple = hasMultiple(conditions);
  const total = summary(release, conditions);
  const groupConditions = { ...conditions };
  groupConditions[dimension] = [];
  const key = cubeKey(release.cube, release.fields, groupConditions);
  const cells = key === null ? [] : release.cube[key].filter(cell => matches(cell, conditions));
  const grouped = new Map();
  for (const cell of cells) {
    if (!Object.hasOwn(cell, dimension)) continue;
    const label = String(cell[dimension]);
    const row = grouped.get(label) || { tumors: 0, persons: multiple ? null : 0 };
    row.tumors += Number(cell.tumors || 0);
    if (!multiple) row.persons += Number(cell.persons || 0);
    grouped.set(label, row);
  }

  if (dimension !== "site") {
    const coverageConditions = { ...conditions };
    delete coverageConditions.site;
    const coverageKey = cubeKey(release.cube, release.fields, coverageConditions);
    const coverageCells = coverageKey === null ? [] : release.cube[coverageKey].filter(cell => matches(cell, coverageConditions));
    for (const cell of coverageCells) {
      if (!Object.hasOwn(cell, dimension)) continue;
      const label = String(cell[dimension]);
      if (!grouped.has(label)) grouped.set(label, { tumors: 0, persons: multiple ? null : 0 });
    }
  } else if (conditions.site?.length && selectedCells(release, Object.fromEntries(Object.entries(conditions).filter(([field]) => field !== "site"))).length) {
    for (const site of conditions.site) {
      if (!grouped.has(site)) grouped.set(site, { tumors: 0, persons: multiple ? null : 0 });
    }
  }

  let labels = [...grouped.keys()];
  if (dimension === "age_group") {
    const order = Object.keys(release.standard_weights || {});
    labels.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  } else if (dimension === "period") {
    labels.sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
  }

  const rows = labels.map(label => {
    const counts = grouped.get(label);
    const baseConditions = { ...conditions };
    delete baseConditions.site;
    if (dimension !== "site") baseConditions[dimension] = [label];
    const population = summary(release, baseConditions).population;
    const count = metricCount(counts, unit);
    let value = count;
    if (metric === "share") {
      const totalCount = metricCount(total, unit);
      value = count === null || !totalCount ? null : count / totalCount * 100;
    } else if (metric === "rate") {
      value = count === null ? null : population ? count / population * 100000 : 0;
    } else if (metric === "asr") {
      value = directAdjustedRate(release, conditions, dimension, label, unit);
    }
    const relativeFrequency = count === null || !metricCount(total, unit)
      ? null
      : round2(count / metricCount(total, unit) * 100);
    const crudeRate = count === null
      ? null
      : round2(population ? count / population * 100000 : 0);
    return {
      label,
      tumors: counts.tumors,
      persons: counts.persons,
      population,
      relative_frequency: relativeFrequency,
      crude_rate: crudeRate,
      adjusted_rate: directAdjustedRate(release, conditions, dimension, label, unit),
      value: value === null ? null : round2(value),
    };
  });
  if (!["age_group", "period"].includes(dimension)) rows.sort((a, b) => (b.value || 0) - (a.value || 0));
  rows.forEach((row, index) => { row.rank = index + 1; });
  if (["line", "scatter", "strip", "swarm"].includes(chart) && rows.length < 2) {
    throw new Error(t("Este gráfico necesita al menos dos categorías con datos."));
  }
  if (["pie", "doughnut"].includes(chart) && rows.length > 8) {
    throw new Error(t("El gráfico circular necesita hasta ocho categorías."));
  }
  if (["pie", "doughnut"].includes(chart) && !rows.some(row => row.value > 0)) {
    throw new Error(t("No hay valores positivos para representar una composición."));
  }
  if (rows.some(row => row.value === null) && metric === "asr") {
    throw new Error(t("Falta población en algún grupo de edad para calcular la tasa ajustada."));
  }
  let datasets;
  if (chart === "scatter") {
    datasets = [{
      label: t("Tumores y personas distintas"),
      data: rows.map(row => ({ x: row.tumors, y: row.persons, category: row.label })),
    }];
  } else if (["strip", "swarm"].includes(chart)) {
    datasets = [{
      label: t(METRIC_LABELS[metric]),
      data: rows.filter(row => row.value !== null).map((row, index) => ({
        x: row.value,
        y: chart === "strip" ? index : index + ((index * 37) % 9 - 4) / 20,
        category: row.label,
      })),
    }];
  } else if (["grouped", "stacked", "percent"].includes(chart)) {
    datasets = ["Mujeres", "Hombres"].map(sex => {
      const series = runQuery(release, { ...params, chart: "bar", sex: [sex] });
      const byLabel = new Map(series.rows.map(row => [row.label, row.value]));
      return { label: t(sex), data: rows.map(row => byLabel.get(row.label) || 0) };
    });
    if (chart === "percent") {
      for (let index = 0; index < rows.length; index += 1) {
        const base = datasets.reduce((sum, dataset) => sum + dataset.data[index], 0);
        for (const dataset of datasets) dataset.data[index] = base ? round2(dataset.data[index] / base * 100) : 0;
      }
    }
  } else {
    datasets = [{ label: t(METRIC_LABELS[metric]), data: rows.map(row => row.value) }];
  }
  return { rows, summary: total, query, datasets, elapsed: 0 };
}

let activeRelease = null;
self.onmessage = ({ data }) => {
  if (data.type === "initialize") {
    activeTranslations = data.translations || {};
    activeRelease = data.release;
    self.postMessage({ ok: true, ready: true, release_id: activeRelease.release_id });
    return;
  }
  const start = performance.now();
  try {
    if (!activeRelease) throw new Error(t("No se cargó una publicación local."));
    const result = runQuery(activeRelease, data.params);
    result.elapsed = performance.now() - start;
    self.postMessage({ ok: true, ...result });
  } catch (error) {
    self.postMessage({ ok: false, error: error.message });
  }
};
