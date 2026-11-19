"use strict";
// One explorer; only public aggregates are stored, never administrative responses.
(() => {
  const t = message => window.gettext ? window.gettext(message) : message;
  const categoryLabel=value=>{const text=String(value);if(text.startsWith("Etapa · código "))return t("Etapa")+" · "+t("código")+" "+text.slice(15);const index=text.indexOf(" · ");return index<0 ? t(text):text.slice(0,index+3)+t(text.slice(index+3));};
  const fields={year:"period",territory:"territory",municipality:"municipality",sex:"sex",age:"age_group",site:"site"};
  const defaults={cohort:"all",dimension:"site",metric:"count",unit:"tumors",chart:"bar"};
  const status=document.getElementById("connection-status");
  if(!status)return;
  let connected=null,pkg=null,db=null,worker=null,workerVersion=null,sequence=0,current=null,installPrompt=null,geometry=null,refreshing=false;
  let probeSequence=0,probeController=null,serverPublication;
  const onExplorer=()=>["/consulta/","/consulta-offline/","/consulta-sintetica/"].includes(location.pathname) && Boolean(document.querySelector("#query-form"));
  const requests=new Map(),numbers=new Intl.NumberFormat(document.documentElement.lang,{maximumFractionDigits:2});
  const node=(tag,text,className)=>{const element=document.createElement(tag);if(text!==undefined)element.textContent=text;if(className)element.className=className;return element;};
  const valid=release=>release?.schema_version===3 && release.synthetic===false && release.publication_approved===true && release.query_contract?.unified===true;
  const openDB=()=>new Promise((resolve,reject)=>{const request=indexedDB.open("rnc-public-offline",2);request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains("package"))request.result.createObjectStore("package");};request.onsuccess=()=>{db=request.result;resolve();};request.onerror=()=>reject(request.error);});
  const store=(mode,action)=>new Promise((resolve,reject)=>{const tx=db.transaction("package",mode),request=action(tx.objectStore("package"));tx.oncomplete=()=>resolve(request?.result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});
  function showConnection(online) {
    document.querySelectorAll("[data-admin-web-link]").forEach(link=>{link.hidden=!online || matchMedia("(display-mode: standalone)").matches || navigator.standalone===true;});
    connected=online;status.dataset.state=online ? "online":"offline";
    document.documentElement.dataset.serverConnection=status.dataset.state;
    try{sessionStorage.setItem("rnc-server-connection",status.dataset.state);}catch{}
    status.querySelector(".connection-label").textContent=online ? t("Online"):t("Offline");
    status.title=online ? t("Conexión con el servidor disponible."):t("Sin conexión con el servidor. Se utiliza la publicación guardada.");
    showCopy();document.dispatchEvent(new CustomEvent("rnc-connection",{detail:{online}}));
  }
  function showCopy(message) {
    status.dataset.offlineReady=String(Boolean(pkg));
    const label=status.querySelector(".connection-copy");
    label.textContent=message || (pkg ? t("Datos disponibles sin conexión"):t("Sin copia guardada"));
    label.title=pkg ? `${pkg.title} · ${pkg.release_id} · ${new Date(pkg.published_at).toLocaleString()}`:"";
  }
  function stopWorker() {worker?.terminate();worker=null;workerVersion=null;for(const request of requests.values())request.reject(new Error(t("La publicación local se actualizó. Repita la consulta.")));requests.clear();}
  async function prepareWorker() {
    if(worker && workerVersion===pkg.publication_fingerprint)return;
    stopWorker();worker=new Worker("/static/js/offline-worker.js");workerVersion=pkg.publication_fingerprint;
    const ready=new Promise((resolve,reject)=>{
      worker.onmessage=({data})=>{if(data.ready){resolve();return;}const pending=requests.get(data.request_id);if(pending){requests.delete(data.request_id);data.ok ? pending.resolve(data):pending.reject(new Error(data.error));}};
      worker.onerror=()=>{reject(new Error(t("No se pudo iniciar el cálculo local.")));for(const request of requests.values())request.reject(new Error(t("No se pudo completar el cálculo local.")));requests.clear();};
    });
    worker.postMessage({type:"initialize",release:pkg});await ready;
  }
  const paramsFromURL=()=>{const query=new URLSearchParams(location.search),params={...defaults};for(const key of Object.keys(defaults))params[key]=query.get(key)||defaults[key];for(const key of Object.keys(fields))params[key]=query.getAll(key).filter(Boolean);params.page=Number(query.get("page"))||1;return params;};
  const paramsFromForm=form=>{const data=new FormData(form),params={...defaults};for(const key of Object.keys(defaults))params[key]=data.get(key)||defaults[key];for(const key of Object.keys(fields))params[key]=data.getAll(key);params.page=1;return params;};
  function queryURL(params) {const query=new URLSearchParams();query.set("__rnc_locale",document.documentElement.lang);for(const key of Object.keys(defaults))query.set(key,params[key]);for(const key of Object.keys(fields))for(const value of params[key]||[])query.append(key,value);if(params.page>1)query.set("page",params.page);return "/consulta/?"+query;}
  function showError(message) {
    let element=document.getElementById("local-query-status");
    if(!element){element=node("p",undefined,"local-query-status");element.id="local-query-status";element.setAttribute("role","status");document.querySelector(".query-results")?.prepend(element);}
    element.textContent=message;
  }
  function choices(field,params) {
    let values=pkg.options[fields[field]] || [];
    if(field==="age" && params.cohort!=="all")values=values.filter(age=>(Number.parseInt(age,10)<20)===(params.cohort==="child"));
    if(field==="site" && params.cohort!=="all")values=values.filter(site=>pkg.site_systems[site]===(params.cohort==="child" ? "CICN":"C10"));
    if(field==="municipality" && params.territory?.length)values=values.filter(code=>params.territory.includes(code.slice(0,2)));
    let result=values.map(value=>[value,categoryLabel(pkg.option_labels?.[fields[field]]?.[value] || value)]);
    if(field==="site" && params.cohort==="adult")result=[["DOCX:C00-97",t("Total C00–97 · diccionario RNC")],["ANUARIO:C00-96",t("Total C00–96 · Anuario 2022")],...result];
    return result;
  }
  function prepareForm(workspace,params) {
    const form=workspace.querySelector("#query-form");form.dataset.personsDisjoint=String(pkg.persons_disjoint);
    for(const key of Object.keys(fields)) {
      const fieldset=form.querySelector(`[data-field="${key}"] .query-multi-options`);if(!fieldset)continue;
      fieldset.querySelectorAll(".query-multi-option").forEach(option=>option.remove());
      choices(key,params).forEach(([value,label],index)=>{const wrapper=node("label",undefined,"query-multi-option"),input=node("input");input.type="checkbox";input.name=key;input.value=value;input.id=`id_${key}_${index}`;input.checked=(params[key] || []).includes(value);wrapper.append(input,node("span",label));fieldset.append(wrapper);});
    }
    for(const key of Object.keys(defaults))form.elements.namedItem(key).value=params[key];
    const scale=params.cohort==="child" ? "1 000 000":"100 000";
    for(const option of form.elements.namedItem("metric").options)if(["rate","asr"].includes(option.value))option.textContent=(option.value==="rate" ? t("Tasa cruda / específica"):t("Tasa ajustada Segi–Doll"))+" · "+t("por")+" "+scale;
    for(const option of form.elements.namedItem("chart").options)option.disabled=!pkg.query_contract.charts.includes(option.value);
    form.querySelectorAll(".field-error").forEach(error=>{error.hidden=true;error.textContent="";});
    form.querySelectorAll(".has-error").forEach(field=>field.classList.remove("has-error"));
    const summary=form.querySelector("[data-error-summary]");if(summary)summary.hidden=true;
    return form;
  }
  function makePayload(params,result,form) {
    const dimensions=pkg.display_labels.dimensions,chartLabel=t(pkg.display_labels.charts[params.chart]),scale=params.cohort==="child" ? "1 000 000":"100 000";
    const metric=params.metric==="rate" ? t("Tasa cruda / específica")+" · "+t("por")+" "+scale:params.metric==="asr" ? t("Tasa ajustada Segi–Doll")+" · "+t("por")+" "+scale:t(pkg.display_labels.metrics[params.metric]);
    const unit=params.unit==="persons" ? t("Personas distintas"):t("Tumores");
    const filters=Object.keys(fields).map(key=>({key,label:form.querySelector(`[data-field="${key}"] summary`)?.textContent.trim() || key,value:(params[key] || []).map(value=>choices(key,params).find(item=>item[0]===value)?.[1] || value).join(", ") || t("Todos")}));
    const label=row=>params.dimension==="site_group" ? categoryLabel(pkg.site_group_labels[row.label] || row.label) : categoryLabel(pkg.option_labels?.[params.dimension]?.[row.label] || row.label);
    const rows=result.rows.map(row=>({...row,display_label:label(row)})),labelMap=new Map(rows.map(row=>[row.label,row.display_label]));
    const payload={type:params.chart,labels:rows.map(row=>row.display_label),datasets:result.datasets.map(dataset=>({...dataset,label:result.datasets.length===1 ? metric:dataset.label,data:dataset.data.map(value=>typeof value==="object" ? {...value,category:labelMap.get(value.category)||value.category}:value)})),metric,unit,unit_label:unit,axis_unit:["share"].includes(params.metric)||params.chart==="percent" ? t("Porcentaje (%)"):["rate","asr"].includes(params.metric) ? metric:unit,dimension_label:t(dimensions[params.dimension]),title:t(dimensions[params.dimension]),chart_label:chartLabel,rate_scale_label:scale,adjusted_rate_label:t("Tasa ajustada Segi–Doll")+" · "+t("por")+" "+scale,note:`${pkg.title} · ${t("Versión")} ${pkg.release_id}`,filter_summary:filters.map(filter=>`${filter.label}: ${filter.value}`).join(" · "),filters,persons_disjoint:pkg.persons_disjoint,person_identity_verified:pkg.person_identity_verified,cohort:params.cohort};
    if(params.chart==="scatter"){payload.axis_unit=t("Tumores");payload.y_axis_unit=t("Personas distintas");}
    if(["pie","doughnut"].includes(params.chart)) {const composition=window.RncChartLayout.composition(payload.labels,payload.datasets,t("Otras categorías"));payload.labels=composition.labels;payload.datasets=composition.datasets;if(composition.grouped)payload.display_note=t("El gráfico muestra las siete categorías mayores y agrupa el resto en Otras categorías. La tabla conserva todas las categorías.");}
    return {payload,rows};
  }
  const number=value=>value===null || value===undefined ? "—":numbers.format(value);
  function tableData(rows,params,payload) {
    const headers=[payload.dimension_label,t("Tumores"),t("Personas distintas"),t("Frecuencia relativa (%)"),t("Población denominadora"),t("Tasa cruda/específica")+" · "+payload.rate_scale_label,payload.adjusted_rate_label,"VH (%)","SCD (%)"];
    const cells=rows.map(row=>[row.display_label,row.tumors,row.persons,row.relative_frequency,row.population,row.crude_rate,row.adjusted_rate,row.vh_percent,row.scd_percent]);
    if(payload.datasets.length>1){headers.push(...payload.datasets.map(dataset=>dataset.label+(params.chart==="percent" ? " (%)":"")));cells.forEach((row,index)=>row.push(...payload.datasets.map(dataset=>dataset.data[index])));}
    if(params.chart==="ranking"){headers.unshift(t("Posición"));cells.forEach((row,index)=>row.unshift(index+1));}
    return {headers,cells};
  }
  function addTable(container,rows,params,payload,all=false) {
    const {headers,cells}=tableData(rows,params,payload),scroll=node("div",undefined,"table-scroll"),table=node("table",undefined,"result-table"),thead=node("thead"),head=node("tr"),body=node("tbody");
    for(const heading of headers){const th=node("th",heading);th.scope="col";head.append(th);}thead.append(head);
    const pages=Math.max(1,Math.ceil(cells.length/10)),page=Math.min(Math.max(1,params.page||1),pages),start=all ? 0:(page-1)*10;
    for(const row of cells.slice(start,all ? cells.length:start+10)){const tr=node("tr");row.forEach((value,index)=>{const cell=node(index===0 ? "th":"td",typeof value==="number" ? number(value):value??"—");if(index)cell.className="numeric";tr.append(cell);});body.append(tr);}
    table.append(thead,body);scroll.append(table);container.append(scroll);
    if(!all && pages>1){const nav=node("nav",undefined,"pagination");nav.setAttribute("aria-label",t("Paginación de resultados"));for(const [text,target] of [[t("Anterior"),page-1],[t("Siguiente"),page+1]])if(target>=1 && target<=pages){const link=node("a",text);link.href=queryURL({...params,page:target})+"#visualizacion";nav.append(link);}nav.insertBefore(node("span",`${t("Página")} ${page} / ${pages}`),nav.lastChild);container.append(nav);}
  }
  function renderMap(container,rows) {
    const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox",pkg.map_geometry.viewbox);svg.setAttribute("role","img");svg.setAttribute("aria-label",t("Mapa de incidencia por provincia"));
    const values=new Map(rows.map(row=>[row.display_label,row.value])),present=rows.filter(row=>row.value!==null).map(row=>row.value),minimum=Math.min(...present),maximum=Math.max(...present),colors=["#e1f0ec","#abd7cc","#69b8a6","#258e7b","#075e5b"];
    for(const region of pkg.map_geometry.regions){const path=document.createElementNS(svg.namespaceURI,"path"),value=values.get(region.name);path.setAttribute("d",region.path);path.setAttribute("stroke","white");path.setAttribute("fill",value===undefined ? "#dedede":colors[maximum>minimum ? Math.min(4,Math.floor((value-minimum)/(maximum-minimum)*5)):0]);const title=document.createElementNS(svg.namespaceURI,"title");title.textContent=`${region.name}: ${number(value)}`;path.append(title);svg.append(path);}
    const wrapper=node("div",undefined,"province-map");wrapper.append(svg);container.append(wrapper,node("p",`${number(minimum)} – ${number(maximum)} · ${t("Sin datos")}: gris`,"muted"),node("p","geoBoundaries · © OpenStreetMap contributors / Wambacher · ODbL 1.0 · 2017","muted"));
  }
  function render(params,result) {
    const old=document.querySelector(".query-workspace");if(!old || !window.RncQueryTemplate)return;
    const workspace=window.RncQueryTemplate.cloneNode(true),form=prepareForm(workspace,params),{payload,rows}=makePayload(params,result,form),results=workspace.querySelector(".query-results");results.replaceChildren();results.classList.toggle("query-table-view",params.chart==="table");
    const panel=node("section",undefined,"panel"),heading=node("div",undefined,"panel-heading");heading.append(node("h2",params.chart==="table" ? t("Tabla de datos"):t("Visualización")));panel.append(heading,node("p",`${payload.metric} · ${payload.unit} · ${payload.dimension_label}`));
    let canvas=null;
    if(params.chart==="map")renderMap(panel,rows);
    else if(params.chart!=="table" && rows.length){const frame=node("div",undefined,"chart-frame");canvas=node("canvas");canvas.id="result-chart";canvas.setAttribute("role","img");canvas.setAttribute("aria-label",t("Gráfico de la consulta; valores disponibles en la tabla inferior"));frame.append(canvas);panel.append(frame);}
    const payloadNode=node("script");payloadNode.id="chart-payload";payloadNode.type="application/json";payloadNode.textContent=JSON.stringify(payload);panel.append(payloadNode);
    panel.append(node("p",payload.filter_summary,"muted"));if(payload.display_note)panel.append(node("p",payload.display_note,"muted"));
    const actions=node("div",undefined,"actions export-actions");for(const [format,label] of [["png",t("Imagen PNG")],["svg",t("Imagen SVG")],["pdf",t("Informe PDF")],["csv",t("Tabla CSV")],["xlsx",t("Excel")]]){const button=node("button",label);button.type="submit";button.name="format";button.value=format;button.setAttribute("form","query-form");if(format==="svg" && params.chart!=="map")button.title=t("El SVG contiene una imagen del gráfico. El mapa conserva formato vectorial.");actions.append(button);}panel.append(actions);
    results.append(panel);const dataPanel=params.chart==="table" ? panel:node("section",undefined,"panel");if(dataPanel!==panel){dataPanel.append(node("h2",t("Resultados")));results.append(dataPanel);}addTable(dataPanel,rows,params,payload);
    dataPanel.append(node("p",`${pkg.title} · ${t("Versión")} ${pkg.release_id} · ${new Date(pkg.published_at).toLocaleString()}`,"muted"));
    if(params.cohort!=="all")dataPanel.append(node("p",t("La población denominadora y los pesos de la tasa ajustada se limitan a las edades de la población analizada."),"muted"));
    if(params.dimension==="stage")dataPanel.append(node("p",t("Se muestran los códigos de etapa recibidos. Leucemias y linfomas están excluidos; la excepción incompleta del diccionario sigue pendiente de aclaración."),"muted"));
    window.Chart?.getChart(document.getElementById("result-chart"))?.destroy();old.replaceWith(workspace);
    window.RncForms.initialize(workspace);if(canvas)window.RncCharts.render(payload,canvas);window.RncExplorer.initialize(workspace);
    current={params,rows,payload};document.documentElement.dataset.queryMode="local";document.dispatchEvent(new CustomEvent("rnc-query-rendered"));
  }
  async function localQuery(params,format,replace=false) {
    if(!pkg){showError(t("No hay una publicación guardada en este dispositivo. Conéctese para prepararla."));return;}
    const run=++sequence;
    try {await prepareWorker();const result=await new Promise((resolve,reject)=>{requests.set(run,{resolve,reject});worker.postMessage({type:"query",request_id:run,params});});if(run!==sequence)return;render(params,result);if(replace)history.replaceState({},"",queryURL(params));else history.pushState({},"",queryURL(params));if(format)await exportLocal(format);}
    catch(error){showError(error.message);}
  }
  const download=(name,blob)=>{const url=URL.createObjectURL(blob),anchor=node("a");anchor.href=url;anchor.download=name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),30000);};
  const escapeXML=value=>String(value??"").replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&apos;"}[char]));
  function excelBlob(headers,cells) {
    const rows=[headers,...cells],sheet='<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+rows.map((row,index)=>'<row r="'+(index+1)+'">'+row.map(value=>typeof value==="number" ? '<c><v>'+value+'</v></c>':'<c t="inlineStr"><is><t>'+escapeXML(value)+'</t></is></c>').join('')+'</row>').join('')+'</sheetData></worksheet>';
    const files={'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>','_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>','xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Consulta" sheetId="1" r:id="rId1"/></sheets></workbook>','xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>','xl/worksheets/sheet1.xml':sheet};
    let offset=0;const chunks=[],central=[];const encode=new TextEncoder();
    const header=(length,entries)=>{const bytes=new Uint8Array(length),view=new DataView(bytes.buffer);for(const [position,value,size] of entries)(size===2 ? view.setUint16.bind(view):view.setUint32.bind(view))(position,value,true);return bytes;};
    for(const [filename,text] of Object.entries(files)){const name=encode.encode(filename),data=encode.encode(text);let crc=0xffffffff;for(const byte of data){crc^=byte;for(let i=0;i<8;i++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}crc=(crc^0xffffffff)>>>0;const local=header(30,[[0,0x04034b50,4],[4,20,2],[14,crc,4],[18,data.length,4],[22,data.length,4],[26,name.length,2]]);chunks.push(local,name,data);central.push(header(46,[[0,0x02014b50,4],[4,20,2],[6,20,2],[16,crc,4],[20,data.length,4],[24,data.length,4],[28,name.length,2],[42,offset,4]]),name);offset+=30+name.length+data.length;}
    const centralLength=central.reduce((sum,bytes)=>sum+bytes.length,0),count=Object.keys(files).length;return new Blob([...chunks,...central,header(22,[[0,0x06054b50,4],[8,count,2],[10,count,2],[12,centralLength,4],[16,offset,4]])],{type:"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"});
  }
  async function exportLocal(format) {
    const renderedChart=window.Chart?.getChart(document.getElementById("result-chart"));if(renderedChart){renderedChart.stop();renderedChart.update("none");}
    const {params,rows,payload}=current,{headers,cells}=tableData(rows,params,payload),metadata=[[t("Fuente y corte"),payload.note],[t("Filtros aplicados"),payload.filter_summary],[t("Indicador"),payload.metric]];
    if(format==="csv"){const cell=value=>'"'+String(value??"").replaceAll('"','""')+'"';download("rnc-query.csv",new Blob(['\ufeff'+[...metadata,[],headers,...cells].map(row=>row.map(cell).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"}));return;}
    if(format==="xlsx"){download("rnc-query.xlsx",excelBlob(headers,[...metadata,[],...cells]));return;}
    if(format==="pdf"){const section=node("section");section.id="local-print-result";section.append(node("h1",`${payload.metric} · ${payload.dimension_label}`),node("p",payload.note),node("p",payload.filter_summary));const source=document.getElementById("result-chart");if(source){const chart=Chart.getChart(source),count=chart.data.labels.length,ratio=source.height/chart.height;if(chart.options.indexAxis==="y" && count>16){const top=chart.chartArea.top*ratio,bottom=chart.chartArea.bottom*ratio,step=(bottom-top)/count,footer=source.height-bottom;for(let first=0;first<count;first+=12){const size=Math.min(12,count-first),piece=document.createElement("canvas");piece.width=source.width;piece.height=top+step*size+footer;const context=piece.getContext("2d");context.drawImage(source,0,0,source.width,top,0,0,source.width,top);context.drawImage(source,0,top+first*step,source.width,size*step,0,top,source.width,size*step);context.drawImage(source,0,bottom,source.width,footer,0,top+size*step,source.width,footer);const image=node("img");image.src=piece.toDataURL();image.style.width="100%";image.style.breakInside="avoid";section.append(image);}}else{const image=node("img");image.src=source.toDataURL();image.style.width="100%";section.append(image);}}addTable(section,rows,params,payload,true);document.body.append(section);document.body.classList.add("printing-local-result");const cleanup=()=>{section.remove();document.body.classList.remove("printing-local-result");};window.addEventListener("afterprint",cleanup,{once:true});window.print();setTimeout(cleanup,60000);return;}
    const map=document.querySelector(".query-results .province-map svg");let canvas=document.getElementById("result-chart");
    if(map && format==="svg"){download("rnc-query.svg",new Blob([new XMLSerializer().serializeToString(map)],{type:"image/svg+xml"}));return;}
    if(map && !canvas){const clone=map.cloneNode(true),box=map.viewBox.baseVal;clone.setAttribute("width",1600);clone.setAttribute("height",1600*box.height/box.width);const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)],{type:"image/svg+xml"}));try{const image=new Image();image.src=url;await image.decode();canvas=document.createElement("canvas");canvas.width=1600;canvas.height=1600*box.height/box.width;canvas.getContext("2d").drawImage(image,0,0);}finally{URL.revokeObjectURL(url);}}
    if(!canvas){canvas=document.createElement("canvas");canvas.width=2200;const rowHeight=50,fullHeight=(cells.length+4)*rowHeight,ratio=Math.min(1,16000/fullHeight);canvas.height=Math.ceil(fullHeight*ratio);const context=canvas.getContext("2d");context.scale(ratio,ratio);context.fillStyle="white";context.fillRect(0,0,2200,fullHeight);context.fillStyle="#183f39";context.font="20px sans-serif";context.fillText(payload.note,15,25);context.font="16px sans-serif";[headers,...cells].forEach((row,index)=>{row.forEach((value,column)=>{const x=column ? 650+(column-1)*185:15;const text=typeof value==="number" ? number(value):String(value??"—");window.RncChartLayout.wrap(text,column ? 18:58).slice(0,2).forEach((line,lineIndex)=>context.fillText(line,x,85+index*rowHeight+lineIndex*18));});});}
    if(format==="png"){canvas.toBlob(blob=>{if(blob)download("rnc-query.png",blob);},"image/png");return;}
    if(format==="svg"){const image=canvas.toDataURL(),svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${canvas.width}" height="${canvas.height}"><title>${escapeXML(payload.note)}</title><image href="${image}" width="100%" height="100%"/></svg>`;download("rnc-query.svg",new Blob([svg],{type:"image/svg+xml"}));}
  }
  async function synchronize(fingerprint) {
    if(refreshing || !db)return;refreshing=true;showCopy(t("Preparando datos sin conexión…"));
    try {const response=await fetch("/paquete-offline.json",{cache:"no-store",credentials:"omit"});if(!response.ok)throw new Error();const next=await response.json();if(!valid(next) || next.publication_fingerprint!==fingerprint)throw new Error();await store("readwrite",storage=>storage.put(next,"active"));pkg=next;stopWorker();showCopy();}
    catch{showCopy(pkg ? t("Copia anterior disponible sin conexión"):t("No se pudo guardar una copia local"));}
    finally{refreshing=false;}
  }
  async function reconcilePublication() {
    if(!db || connected!==true || serverPublication===undefined)return;
    if(!serverPublication){pkg=null;stopWorker();try{await store("readwrite",storage=>storage.delete("active"));}catch{}showCopy(t("No hay publicación disponible"));}
    else if(!pkg || pkg.publication_fingerprint!==serverPublication)await synchronize(serverPublication);
  }
  async function checkConnection() {
    const run=++probeSequence;
    probeController?.abort();const controller=new AbortController();probeController=controller;
    if(navigator.onLine===false){showConnection(false);return;}
    const timeout=setTimeout(()=>controller.abort(),5000);
    try {
      const response=await fetch("/conexion.json",{cache:"no-store",credentials:"omit",signal:controller.signal});
      if(!response.ok)throw new Error();const info=await response.json();
      if(run!==probeSequence || navigator.onLine===false)return;
      if(info.online!==true)throw new Error();showConnection(true);
      serverPublication=info.publication;await reconcilePublication();
    } catch{if(run===probeSequence)showConnection(false);}
    finally{clearTimeout(timeout);}
  }
  document.addEventListener("submit",event=>{if(event.target.id!=="query-form" || connected!==false)return;event.preventDefault();event.stopImmediatePropagation();localQuery(paramsFromForm(event.target),event.submitter?.name==="format" ? event.submitter.value:null);},true);
  document.addEventListener("click",event=>{if(connected!==false || !onExplorer())return;const anchor=event.target.closest("a");if(!anchor)return;const url=new URL(anchor.href,location.href);if(url.origin!==location.origin || url.pathname!=="/consulta/")return;event.preventDefault();history.pushState({},"",url.pathname+url.search);localQuery(paramsFromURL(),null,true);});
  addEventListener("popstate",()=>{if(connected===false && onExplorer())localQuery(paramsFromURL(),null,true);});
  addEventListener("offline",()=>{++probeSequence;probeController?.abort();showConnection(false);});addEventListener("online",checkConnection);
  document.addEventListener("visibilitychange",()=>{if(!document.hidden)checkConnection();});setInterval(()=>{if(!document.hidden)checkConnection();},30000);
  addEventListener("pagehide",()=>{document.querySelectorAll("[data-admin-web-link]").forEach(link=>{link.hidden=true;});});
  addEventListener("pageshow",event=>{
    if(!event.persisted)return;
    let knownOffline=navigator.onLine===false;
    try{knownOffline ||= sessionStorage.getItem("rnc-server-connection")==="offline";}catch{}
    if(knownOffline)showConnection(false);
    checkConnection();
  });
  addEventListener("beforeinstallprompt",event=>{event.preventDefault();installPrompt=event;document.getElementById("install-public-app").hidden=false;});
  document.getElementById("install-public-app").addEventListener("click",async()=>{if(installPrompt){await installPrompt.prompt();installPrompt=null;}});
  async function initialize() {
    let knownOffline=document.documentElement.dataset.serverConnection==="offline" || navigator.onLine===false;
    try{knownOffline ||= sessionStorage.getItem("rnc-server-connection")==="offline";}catch{}
    if(knownOffline)showConnection(false);
    // Connectivity does not depend on IndexedDB availability or its startup time.
    const connection=checkConnection();
    try{await openDB();const saved=await store("readonly",storage=>storage.get("active"));if(valid(saved))pkg=saved;}catch{showCopy(t("El almacenamiento local no está disponible"));}
    await connection;await reconcilePublication();if(connected===false && onExplorer())await localQuery(paramsFromURL(),null,true);
  }
  initialize();
})();
