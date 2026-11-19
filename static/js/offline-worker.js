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
  const requested=fields.filter(field => Object.hasOwn(conditions,field)),key=requested.join(",");
  if (Object.hasOwn(cube,key)) return key;
  const candidate=Object.keys(cube).filter(source => requested.every(field => source.split(",").includes(field))).sort((a,b)=>a.length-b.length)[0];
  if(candidate===undefined)return null;
  const grouped=new Map();
  for(const cell of cube[candidate]) {
    const index=JSON.stringify(requested.map(field=>cell[field]));
    if(!grouped.has(index))grouped.set(index,Object.fromEntries(requested.map(field=>[field,cell[field]])));
    const row=grouped.get(index);
    for(const metric of ["tumors","persons","population","vh","vh_known","scd","scd_known"])if(Object.hasOwn(cell,metric))row[metric]=(row[metric] || 0)+Number(cell[metric] || 0);
  }
  cube[key]=[...grouped.values()];return key;
}

function matches(cell, conditions) {
  return Object.entries(conditions).every(([field, selected]) =>
    !selected.length || selected.includes(String(cell[field]))
  );
}

function selectedCells(release, conditions) {
  const key = cubeKey(release.cube, release.fields, conditions);
  if (key === null) return [];
  const cells = release.cube[key];
  const fields = key ? key.split(",") : [];
  const indexes = release._cubeIndexes || (release._cubeIndexes = {});
  let index = indexes[key];
  if (!index) {
    index = new Map();
    for (const cell of cells) {
      index.set(JSON.stringify(fields.map(field => String(cell[field] ?? ""))), cell);
    }
    indexes[key] = index;
  }
  const selections = fields.map(field => values(conditions[field]));
  let combinations = 1;
  for (const selected of selections) combinations *= selected.length;
  if (combinations > Math.max(1, cells.length)) {
    return cells.filter(cell => matches(cell, conditions));
  }
  const selected = [];
  const visit = (position, tuple) => {
    if (position === selections.length) {
      const cell = index.get(JSON.stringify(tuple));
      if (cell) selected.push(cell);
      return;
    }
    for (const value of selections[position]) visit(position + 1, [...tuple, value]);
  };
  visit(0, []);
  return selected;
}

function summary(release, conditions) {
  const cells = selectedCells(release, conditions);
  const multiple = hasMultiple(conditions) && !release.persons_disjoint;
  const populationKey = cubeKey(release.population_cube || {}, release.population_fields || [], conditions);
  const populationConditions = Object.fromEntries(
    Object.entries(conditions).filter(([field]) => (release.population_fields || []).includes(field))
  );
  let population;
  if (Array.isArray(release.population_cube)) {
    population = release.population_cube.reduce((total, cell) => total + Number(cell.population || 0), 0);
  } else if (release.population_cube && populationKey !== null) {
    const fields = populationKey ? populationKey.split(",") : [];
    const populationCells = release.population_cube[populationKey];
    const indexes = release._populationIndexes || (release._populationIndexes = {});
    let index = indexes[populationKey];
    if (!index) {
      index = new Map();
      for (const cell of populationCells) {
        const key = JSON.stringify(fields.map(field => String(cell[field] ?? "")));
        index.set(key, (index.get(key) || 0) + Number(cell.population || 0));
      }
      indexes[populationKey] = index;
    }
    const selections = fields.map(field => values(populationConditions[field]));
    let combinations = 1;
    for (const selected of selections) combinations *= selected.length;
    if (combinations <= Math.max(1, populationCells.length)) {
      const selected = [];
      const visit = (position, tuple) => {
        if (position === selections.length) {
          selected.push(index.get(JSON.stringify(tuple)) || 0);
          return;
        }
        for (const value of selections[position]) visit(position + 1, [...tuple, value]);
      };
      visit(0, []);
      population = selected.reduce((sum, value) => sum + value, 0);
    } else {
      population = populationCells
        .filter(cell => matches(cell, populationConditions))
        .reduce((total, cell) => total + Number(cell.population || 0), 0);
    }
  } else {
    population = cells.reduce((total, cell) => total + Number(cell.population || 0), 0);
  }
  return {
    tumors: cells.reduce((total, cell) => total + Number(cell.tumors || 0), 0),
    persons: !release.person_identity_verified || (multiple && !release.persons_disjoint) ? null : cells.reduce((total, cell) => total + Number(cell.persons || 0), 0),
    population,
    ...Object.fromEntries(["vh","vh_known","scd","scd_known"].map(field => [field,cells.reduce((total,cell)=>total+(cell[field] || 0),0)])),
  };
}

function metricCount(summaryResult, unit) {
  return unit === "persons" ? summaryResult.persons : summaryResult.tumors;
}

const QUALITY = ["vh", "vh_known", "scd", "scd_known"];
const agesFor = (release, cohort="all") => Object.keys(release.standard_weights).filter((_age,index) => cohort === "all" || (cohort === "child" ? index < 4 : index >= 4));
const rateScale = cohort => cohort === "child" ? 1000000 : 100000;
function categoryNumbers(expression) {
  return expression.split(",").flatMap(part => {
    const match = part.match(/^([CD])(\d{2})(?:-([CD])?(\d{2}))?$/);
    if (!match) return [];
    return Array.from({length:Number(match[4] || match[2])-Number(match[2])+1},(_v,index) => match[1]+String(Number(match[2])+index).padStart(2,"0"));
  });
}
function expandTotals(release, params) {
  const totals={"DOCX:C00-97":97,"ANUARIO:C00-96":96};
  const sites=values(params.site), selected=sites.filter(site => Object.hasOwn(totals,site));
  if (!selected.length) return params;
  const max=Math.max(...selected.map(site => totals[site]));
  const included=release.options.site.filter(site => site.startsWith("C10:") && categoryNumbers(site.slice(4)).every(code => code.startsWith("C") && Number(code.slice(1))<=max));
  return {...params,site:[...new Set([...sites.filter(site => !selected.includes(site)),...included])]};
}
function directAdjustedRate(release, conditions, dimension, label, unit, cohort="all") {
  const ages=agesFor(release,cohort);
  if (["age_group","stage"].includes(dimension) || (conditions.age_group && (conditions.age_group.length !== ages.length || !ages.every(age => conditions.age_group.includes(age))))) return null;
  const caseBase={...conditions}, populationBase={...conditions};
  delete caseBase.age_group; delete populationBase.age_group; delete populationBase.site;
  caseBase[dimension]=values(label);
  if (dimension!=="site") populationBase[dimension]=values(label);
  let weighted=0,weightSum=0;
  for (const age of ages) {
    const count=metricCount(summary(release,{...caseBase,age_group:[age]}),unit);
    const population=summary(release,{...populationBase,age_group:[age]}).population;
    if (count===null || population<=0) return null;
    const weight=Number(release.standard_weights[age]);
    weighted+=count/population*weight; weightSum+=weight;
  }
  return weightSum ? round2(weighted/weightSum*rateScale(cohort)) : null;
}
function round2(value) { return Math.round((value + Number.EPSILON) * 100) / 100; }
function validate(release, original) {
  const params=expandTotals(release,original), contract=release.query_contract || {};
  const chart=params.chart || "bar", dimension=params.dimension || "site", metric=params.metric || "count", unit=params.unit || "tumors", cohort=params.cohort || "all";
  const conditions=conditionsFor(params), errors=[];
  for (const [key,value] of [["charts",chart],["dimensions",dimension],["metrics",metric]]) if (contract[key] && !contract[key].includes(value)) errors.push(t("Selección fuera de la publicación local."));
  if (release.schema_version!==3 || release.synthetic!==false) errors.push(t("Publicación incompatible."));
  if (!["all","adult","child"].includes(cohort)) errors.push(t("Población de análisis no reconocida."));
  if (!["tumors","persons"].includes(unit)) errors.push(t("Unidad no reconocida."));
  if (unit==="persons" && (!release.person_identity_verified || (!release.persons_disjoint && hasMultiple(conditions)))) errors.push(t("No se pueden deduplicar personas para esta selección."));
  if (dimension==="stage" && (cohort!=="adult" || !["count","share"].includes(metric))) errors.push(t("La etapa clínica se consulta en adultos, mediante frecuencias o porcentajes."));
  if ((["site","site_group"].includes(dimension) || conditions.site?.length) && cohort==="all" && ["rate","asr"].includes(metric)) errors.push(t("Seleccione población adulta o infantil para calcular tasas por grupo tumoral."));
  for (const [key,value] of [["chart_dimensions",dimension],["chart_metrics",metric],["chart_units",unit]]) if (contract[key]?.[chart] && !contract[key][chart].includes(value)) errors.push(t("Configuración incompatible con el gráfico."));
  if (metric==="asr" && (values(params.age).length || dimension==="age_group")) errors.push(t("El ajuste requiere todos los grupos de edad y otra dimensión."));
  if (["pie","doughnut"].includes(chart) && unit==="persons" && dimension!=="sex") errors.push(t("Para personas distintas, la composición solo se puede comparar por sexo."));
  if (["grouped","stacked","percent"].includes(chart) && (values(params.sex).length || dimension==="sex")) errors.push(t("La comparación por sexo requiere ambos sexos y otra dimensión."));
  for (const [filter,field] of Object.entries(FILTER_FIELDS)) if (values(params[filter]).some(value => !release.options[field]?.includes(value))) errors.push(t("Valor fuera de la publicación local."));
  if (cohort!=="all") conditions.age_group=values(params.age).length ? values(params.age).filter(age => agesFor(release,cohort).includes(age)) : agesFor(release,cohort);
  return {errors,conditions,chart,dimension,metric,unit,cohort,params};
}
function resultsFor(release, params) {
  params=expandTotals(release,params);
  const cohort=params.cohort || "all",dimension=params.dimension || "site",unit=params.unit || "tumors",metric=params.metric || "count";
  const conditions=conditionsFor(params);
  if (cohort!=="all") conditions.age_group=values(params.age).length ? values(params.age).filter(age => agesFor(release,cohort).includes(age)) : agesFor(release,cohort);
  if (conditions.age_group && !conditions.age_group.length) return {rows:[],summary:{tumors:0,persons:null,population:0}};
  if (dimension==="site_group") {
    const leaf=resultsFor(release,{...params,dimension:"site",metric:"count"}),groups=new Map();
    for (const row of leaf.rows) {
      const label=release.site_groups[row.label];
      if (!groups.has(label)) groups.set(label,{label,members:[],tumors:0,population:row.population,...Object.fromEntries(QUALITY.map(field => [field,0]))});
      const group=groups.get(label); group.members.push(row.label); group.tumors+=row.tumors;
      for (const field of QUALITY) group[field]+=row[field];
    }
    const rows=[...groups.values()].map(row => {
      row.persons=summary(release,{...conditions,site:row.members}).persons;
      const count=row[unit];
      row.relative_frequency=count!==null && leaf.summary[unit] ? round2(count/leaf.summary[unit]*100) : null;
      row.crude_rate=count!==null && row.population ? round2(count/row.population*rateScale(cohort)) : null;
      row.adjusted_rate=cohort!=="all" ? directAdjustedRate(release,conditions,"site",row.members,unit,cohort) : null;
      row.vh_percent=row.tumors && row.vh_known===row.tumors ? round2(row.vh/row.tumors*100) : null;
      row.scd_percent=row.tumors && row.scd_known===row.tumors ? round2(row.scd/row.tumors*100) : null;
      row.value={count,share:row.relative_frequency,rate:row.crude_rate,asr:row.adjusted_rate}[metric]; delete row.members;return row;
    }).sort((a,b)=>(b.value || 0)-(a.value || 0));
    return {rows,summary:leaf.summary};
  }
  const multiple=!release.person_identity_verified || (!release.persons_disjoint && hasMultiple(conditions));
  const empty=()=>({tumors:0,persons:multiple ? null : 0,...Object.fromEntries(QUALITY.map(field=>[field,0]))});
  const groupConditions={...conditions,[dimension]:conditions[dimension] || []};
  const key=cubeKey(release.cube,release.fields,groupConditions),grouped=new Map();
  for (const cell of release.cube[key] || []) {
    if (!matches(cell,conditions)) continue;
    const label=String(cell[dimension]);if(!grouped.has(label))grouped.set(label,empty());const row=grouped.get(label);
    row.tumors+=cell.tumors;if(!multiple)row.persons+=cell.persons;
    for(const field of QUALITY)row[field]+=cell[field] || 0;
  }
  const coverage={...groupConditions};delete coverage.site;
  const coverageKey=cubeKey(release.cube,release.fields,coverage);
  if(dimension!=="site") for(const cell of release.cube[coverageKey] || []) {
    if(matches(cell,Object.fromEntries(Object.entries(conditions).filter(([field])=>field!=="site"))) && !grouped.has(String(cell[dimension])))grouped.set(String(cell[dimension]),empty());
  }
  else if(conditions.site?.length && selectedCells(release,Object.fromEntries(Object.entries(conditions).filter(([field])=>field!=="site"))).length) for(const label of conditions.site)if(!grouped.has(label))grouped.set(label,empty());
  const total=summary(release,conditions);
  if(dimension==="stage") {total.tumors=[...grouped.values()].reduce((sum,row)=>sum+row.tumors,0);total.persons=summary(release,{...conditions,stage:[...grouped.keys()]}).persons;}
  const rows=[...grouped.entries()].map(([label,counts])=>{
    const base={...conditions};delete base.site;if(dimension!=="site")base[dimension]=[label];
    const rates=dimension!=="stage" && !(cohort==="all" && (dimension==="site" || conditions.site?.length));
    const population=rates ? summary(release,base).population : null,count=counts[unit];
    const row={label,...counts,population,relative_frequency:count!==null && total[unit] ? round2(count/total[unit]*100):null,crude_rate:count!==null && population ? round2(count/population*rateScale(cohort)):null,adjusted_rate:rates ? directAdjustedRate(release,conditions,dimension,label,unit,cohort):null};
    row.vh_percent=counts.tumors && counts.vh_known===counts.tumors ? round2(counts.vh/counts.tumors*100):null;
    row.scd_percent=counts.tumors && counts.scd_known===counts.tumors ? round2(counts.scd/counts.tumors*100):null;
    row.value=metric==="count" ? count : metric==="share" ? (count!==null && total[unit] ? round2(count/total[unit]*100):null) : metric==="rate" ? row.crude_rate : row.adjusted_rate;
    return row;
  });
  if(dimension==="age_group")rows.sort((a,b)=>agesFor(release).indexOf(a.label)-agesFor(release).indexOf(b.label));
  else if(dimension==="period")rows.sort((a,b)=>a.label.localeCompare(b.label));else rows.sort((a,b)=>(b.value||0)-(a.value||0));
  return {rows,summary:total};
}
function runQuery(release, params) {
  const query=validate(release,params);if(query.errors.length)throw new Error(query.errors.join(" "));
  const result=resultsFor(release,query.params),{rows}=result,{chart,metric}=query;
  rows.forEach((row,index)=>row.rank=index+1);
  if(["line","trend","curve","scatter","strip","swarm"].includes(chart) && rows.length<2)throw new Error(t("Este gráfico necesita al menos dos categorías con datos."));
  if(["pie","doughnut"].includes(chart) && !rows.some(row=>row.value>0))throw new Error(t("No hay valores positivos para representar una composición."));
  if(rows.some(row=>row.value===null))throw new Error(t("No hay cobertura de población completa para el ajuste seleccionado."));
  let datasets=[{label:t(METRIC_LABELS[metric]),data:rows.map(row=>row.value)}];
  if(chart==="scatter")datasets=[{label:t("Tumores y personas distintas"),data:rows.map(row=>({x:row.tumors,y:row.persons,category:row.label}))}];
  else if(["strip","swarm"].includes(chart))datasets=[{label:t(METRIC_LABELS[metric]),data:rows.map((row,index)=>({x:row.value,y:chart==="strip" ? index:index+((index*37)%9-4)/20,category:row.label}))}];
  else if(["grouped","stacked","percent"].includes(chart)) {
    datasets=["Mujeres","Hombres"].map(sex=>{const byLabel=new Map(resultsFor(release,{...query.params,sex:[sex]}).rows.map(row=>[row.label,row.value]));return {label:t(sex),data:rows.map(row=>byLabel.get(row.label)||0)};});
    if(chart==="percent")for(let i=0;i<rows.length;i++){const base=datasets.reduce((sum,dataset)=>sum+dataset.data[i],0);for(const dataset of datasets)dataset.data[i]=base ? round2(dataset.data[i]/base*100):0;}
  }
  return {...result,query,datasets,elapsed:0};
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
    self.postMessage({ ok: true, request_id:data.request_id, ...result });
  } catch (error) {
    self.postMessage({ ok: false, request_id:data.request_id, error: error.message });
  }
};
