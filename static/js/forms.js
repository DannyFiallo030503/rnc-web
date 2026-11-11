"use strict";
(() => {
  const t = message => window.gettext ? window.gettext(message) : message;
  const format = (message, values) => window.interpolate
    ? window.interpolate(t(message), values, true)
    : message.replace(/%\((\w+)\)s/g, (_, key) => values[key]);
  const rules = {
    username: /^[A-Za-z0-9._-]+$/u,
    "person-name": /^[\p{L}\p{M} '’-]+$/u,
    "plain-text": /^[\p{L}\p{M}\p{N}_ \n.,;:()'·’–—+/%&!?@#-]+$/u,
    search: /^[\p{L}\p{M}\p{N}_ .@+'’-]*$/u,
    email: /^[A-Za-z0-9.!#$%&'*+\/=?^_`{|}~@-]+$/u,
  };
  const validCharacters = (input, value) => !rules[input.dataset.rule] || !value || rules[input.dataset.rule].test(value.normalize("NFC").replace(/\u00a0/g," "));
  document.querySelectorAll("[data-help-trigger]").forEach((help) => {
    const popover=help?.querySelector(".filter-help-popover");
    let holdTimer, longPressed=false;
    const place=()=>{
      if(!popover)return;
      const rect=help.getBoundingClientRect(),width=popover.offsetWidth,height=popover.offsetHeight;
      const left=Math.max(8,Math.min(innerWidth-width-8,rect.left+rect.width/2-width/2));
      let top=rect.top-height-9;
      const above=top>=8;
      if(!above)top=Math.min(innerHeight-height-8,rect.bottom+9);
      popover.classList.toggle("is-above",above);
      popover.style.left=`${left}px`;popover.style.top=`${top}px`;
      popover.style.setProperty("--tip-arrow-left",`${Math.max(10,Math.min(width-10,rect.left+rect.width/2-left))}px`);
    };
    help.addEventListener("pointerenter",place);
    help.addEventListener("focus",place);
    popover?.addEventListener("click",event=>event.stopPropagation());
    help.addEventListener("pointerdown",(event)=>{
      place();
      if(event.pointerType==="touch") holdTimer=setTimeout(()=>{longPressed=true;help.classList.add("is-open");},500);
    });
    ["pointerup","pointercancel","pointerleave"].forEach(type=>help.addEventListener(type,()=>clearTimeout(holdTimer)));
    help.addEventListener("click",(event)=>{
      if(longPressed){event.preventDefault();event.stopPropagation();longPressed=false;}
    });
    help.addEventListener("keydown",(event)=>{if(event.key==="Escape")help.classList.remove("is-open");});
  });
  document.addEventListener("click",(event)=>{
    if(!event.target.closest(".filter-help")) document.querySelectorAll(".filter-help.is-open").forEach(item=>item.classList.remove("is-open"));
  });
  document.querySelectorAll("form[data-validate]").forEach((form) => {
    form.noValidate = true; // Inline messages replace browser bubbles; backend still validates.
    const inputs = [...form.querySelectorAll("input:not([type=hidden]),select,textarea")];
    const summary = form.querySelector("[data-error-summary]");
    const links = form.querySelector("[data-error-links]");
    function show(input, message) {
      const container = input.closest("[data-field]");
      const error = document.getElementById(input.id + "_error");
      if (!container || !error) return;
      container.classList.toggle("has-error", Boolean(message));
      input.setAttribute("aria-invalid", String(Boolean(message)));
      error.textContent = message;
      error.hidden = !message;
      if(!message && links) {
        links.querySelectorAll("a").forEach(link=>{
          if(link.getAttribute("href") === `#${input.id}`) link.closest("li")?.remove();
        });
        if(summary && !links.children.length) summary.hidden=true;
      }
    }
    function message(input) {
      const value = input.type === "file" ? (input.files[0]?.name || "") : input.value;
      if (input.required && (input.type === "checkbox" ? !input.checked : !value.trim()))
        return input.type === "checkbox" ? t("Check this box to continue.") : t("Complete this field.");
      if (!value) return "";
      if(input.dataset.compatError) return input.dataset.compatError;
      if (!validCharacters(input, value)) return input.dataset.ruleMessage || t("Check the characters entered in this field.");
      if (input.minLength > 0 && value.length < input.minLength) return format("Enter at least %(length)s characters.", { length: input.minLength });
      if (input.maxLength > 0 && value.length > input.maxLength) return format("Enter no more than %(length)s characters.", { length: input.maxLength });
      if (input.type === "email" && input.validity.typeMismatch) return t("Enter a valid email address, for example name@domain.com.");
      if (input.type === "file") {
        if (!value.toLowerCase().endsWith(".csv")) return t("Choose a .csv file.");
        if (input.files[0].size > Number(input.dataset.maxBytes || Infinity)) return t("The file exceeds the 12 MB limit.");
      }
      if (input.dataset.rule === "person-name" && !/^[\p{L}\p{M}]+(?:[ '’-][\p{L}\p{M}]+)*$/u.test(value.normalize("NFC").replace(/\u00a0/g," ").trim())) return t("Separate name parts with a space, apostrophe, or hyphen; do not start or end with punctuation.");
      if (input.dataset.rule === "new-password" && /^\d+$/u.test(value)) return t("The password cannot contain only numbers.");
      if (input.dataset.matches && value !== form.elements.namedItem(input.dataset.matches)?.value) return t("The passwords do not match. Enter the same password again.");
      return "";
    }
    const serverErrors = new Map();
    const currentValue = (input) => input.type === "checkbox"
      ? String(input.checked)
      : input.type === "file"
        ? (input.files[0]?.name || "")
        : input.value;
    inputs.forEach((input) => {
      const error = document.getElementById(input.id + "_error");
      if (input.getAttribute("aria-invalid") === "true" && error && !error.hidden)
        serverErrors.set(input, { value: currentValue(input), text: error.textContent.trim(), changed: false });
    });
    function validate(input) {
      const serverError = serverErrors.get(input);
      if (serverError && currentValue(input) !== serverError.value) serverError.changed = true;
      show(input, serverError && !serverError.changed ? serverError.text : message(input));
    }
    function reject(input, event, value) {
      const selected = typeof input.selectionStart === "number" ? input.selectionEnd-input.selectionStart : 0;
      const projected = input.value.length-selected+value.length;
      if(input.maxLength>0 && (value.length>input.maxLength || (input.type!=="email" && projected>input.maxLength))) {
        event.preventDefault();show(input,format("Text was not added: enter no more than %(length)s characters.", { length: input.maxLength }));return;
      }
      if (!validCharacters(input, value)) {
        event.preventDefault();
        show(input, t("Disallowed text was not added. ") + (input.dataset.ruleMessage || t("Check the format of this field.")));
      }
    }
    inputs.forEach((input) => {
      input.addEventListener("beforeinput", (event) => {
        if (!event.isComposing && event.inputType?.startsWith("insert") && event.data)
          reject(input, event, event.data);
      });
      input.addEventListener("paste", (event) => {
        if (event.clipboardData) reject(input, event, event.clipboardData.getData("text"));
      });
      input.addEventListener("blur", () => {
        if (input.type !== "password" && input.type !== "file" && input.tagName !== "SELECT") input.value = input.value.normalize("NFC").replace(/\u00a0/g," ").trim();
        validate(input);
      });
      input.addEventListener("input", () => validate(input));
      input.addEventListener("change", () => { if(input.type==="file") { const label=input.closest("[data-field]")?.querySelector("[data-file-name]");if(label)label.textContent=input.files[0]?.name || t("No file selected");} validate(input); });
      input.addEventListener("compositionend", () => validate(input));
    });
    if (form.matches("[data-query-form]")) {
      const get=(name)=>form.elements.namedItem(name);
      const applyButton=form.querySelector(".apply-filters");
      const requirementsNode=document.getElementById("chart-requirements-data");
      const requirementsData=requirementsNode ? JSON.parse(requirementsNode.textContent) : {};
      const compatibilityNode=document.getElementById("chart-compatibility-data");
      const compatibilityData=compatibilityNode ? JSON.parse(compatibilityNode.textContent) : {};
      function updateRequiredMarkers() {
        const profile=requirementsData[get("chart").value];
        if(!profile) return;
        const dimensionFields={period:"year",territory:"territory",sex:"sex",age_group:"age",site:"site"};
        const requiredFilters=new Set((profile.filter_fields || []).map(field=>field==="dimension" ? dimensionFields[get("dimension").value] : field).filter(Boolean));
        const axisField=dimensionFields[get("dimension").value];
        if(axisField)requiredFilters.add(axisField);
        if(get("metric").value==="asr")requiredFilters.add("age");
        form.querySelectorAll("[data-chart-required-indicator]").forEach(mark=>{
          mark.hidden=!requiredFilters.has(mark.dataset.requiredFilter);
        });
      }
      function updateApplyButton() {
        if(applyButton) applyButton.disabled=Boolean(form.querySelector(".form-field.has-error"));
      }
      function clearFieldError(container) {
        if(!container) return;
        container.classList.remove("has-error");
        container.querySelectorAll("input").forEach(input=>input.setAttribute("aria-invalid","false"));
        const error=container.querySelector(".field-error");
        if(error){error.hidden=true;error.textContent="";}
        const ids=new Set([...container.querySelectorAll("input")].map(input=>input.id));
        links?.querySelectorAll("a").forEach(link=>{if(ids.has(link.getAttribute("href")?.slice(1)))link.closest("li")?.remove();});
        if(summary && links && !links.children.length) summary.hidden=true;
      }
      function refreshMultiGroup(group) {
        const selected=group.querySelectorAll(".query-multi-option input:checked").length;
        const summary=group.querySelector("summary");
        let count=group.querySelector("summary small");
        if(!count && summary) { count=document.createElement("small"); summary.append(" ",count); }
        if(!count) return;
        const selectedLabel = window.ngettext
          ? window.ngettext("%(count)s option selected", "%(count)s options selected", selected)
          : selected === 1 ? "%(count)s option selected" : "%(count)s options selected";
        count.textContent = selected ? format(selectedLabel, { count: selected }) : t("All");
      }
      form.querySelectorAll(".query-multi-field").forEach(group=>{
        refreshMultiGroup(group);
        group.querySelector("[data-select-all]")?.addEventListener("click",()=>{
          group.querySelectorAll(".query-multi-option input:checked").forEach(input=>{input.checked=false;validate(input);});
          clearFieldError(group.closest("[data-field]"));
          refreshMultiGroup(group);
          compatible();
          updateApplyButton();
        });
        group.querySelectorAll(".query-multi-option input").forEach(input=>input.addEventListener("change",()=>{
          clearFieldError(group.closest("[data-field]"));
          refreshMultiGroup(group);
          updateApplyButton();
        }));
      });
      function compatible() {
        const dimension=get("dimension").value,metric=get("metric").value,unit=get("unit").value;
        const selectedCount=name=>form.querySelectorAll(`input[name="${name}"]:checked`).length;
        const dimensionOptions=get("dimension").options,metricOptions=get("metric").options,unitOptions=get("unit").options;
        for(const option of get("chart").options) {
          let reason="";
          const rule=compatibilityData[option.value];
          if(rule && !rule.dimensions.includes(dimension)) reason=t("This chart does not support the selected dimension.");
          if(!reason && rule && !rule.metrics.includes(metric)) reason=t("This chart does not support the selected indicator.");
          if(!reason && rule && !rule.units.includes(unit)) reason=t("This chart does not support the selected unit.");
          if(!reason && ["pie","doughnut"].includes(option.value) && unit==="persons" && dimension!=="sex") reason=t("For distinct people, compare composition by sex.");
          if(option.value==="line" && dimension!=="period") reason=t("Line charts require comparison by period.");
          if(option.value==="line" && dimension==="period" && form.querySelectorAll('input[name="year"]:checked').length===1) reason=t("The series needs at least two years; clear the single-year selection.");
          if(["strip","swarm"].includes(option.value) && !["territory","age_group"].includes(dimension)) reason=t("Point charts compare values by province of residence or age group.");
          if(["strip","swarm","scatter"].includes(option.value) && ["territory","age_group"].includes(dimension) && selectedCount(dimension==="territory" ? "territory" : "age")===1) reason=t("This chart needs at least two categories; clear the single-province or single-age filter.");
          if(option.value==="scatter" && !["territory","age_group"].includes(dimension)) reason=t("Scatter plots compare provinces or age groups.");
          if(option.value==="scatter" && (metric!=="count" || unit!=="tumors")) reason=t("Scatter plots compare absolute counts of tumors and distinct people.");
          if(option.value==="scatter" && ["year","territory","municipality","sex","age","site"].some(key=>selectedCount(key)>1)) reason=t("A scatter plot needs a selection where distinct people can be counted without overlap.");
          if(["grouped","stacked","percent"].includes(option.value) && (selectedCount("sex")>0 || dimension==="sex")) reason=t("La comparación por sexo requiere ambos sexos y otra dimensión.");
          if(["stacked","percent"].includes(option.value) && metric!=="count") reason=t("Las barras apiladas requieren frecuencias absolutas.");
          if(["pie","doughnut"].includes(option.value) && (!["count","share"].includes(metric) || (unit==="persons" && dimension!=="sex"))) reason=t("La composición requiere categorías excluyentes; para personas, compare por sexo.");
          option.disabled=Boolean(reason);option.title=reason;
          if(option.selected)get("chart").dataset.compatError=reason;
        }
        const activeRule=compatibilityData[get("chart").value] || {};
        for(const option of dimensionOptions) {
          let allowed=(activeRule.dimensions || []).includes(option.value);
          if(["pie","doughnut"].includes(get("chart").value) && unit==="persons") allowed=option.value==="sex";
          option.disabled=!allowed && !option.selected;
          option.title=allowed ? "" : t("Esta dimensión no está disponible para el gráfico seleccionado.");
        }
        for(const option of metricOptions) {
          const allowed=(activeRule.metrics || []).includes(option.value);
          option.disabled=!allowed && !option.selected;
          option.title=allowed ? "" : t("Este indicador no está disponible para el gráfico seleccionado.");
        }
        for(const option of unitOptions) {
          let allowed=(activeRule.units || []).includes(option.value);
          if(["pie","doughnut"].includes(get("chart").value) && option.value==="persons") allowed=dimension==="sex";
          option.disabled=!allowed && !option.selected;
          option.title=allowed ? "" : t("Esta unidad no está disponible para el gráfico seleccionado.");
        }
        const chart=get("chart").value;
        const limitOne=unit==="persons" || chart==="scatter";
        for(const group of form.querySelectorAll(".query-multi-field")) {
          const field=group.querySelector("input")?.name;
          const selected=group.querySelectorAll("input:checked").length;
          const sexMustStayAll=["grouped","stacked","percent"].includes(chart) && field==="sex";
          const singleValueOnly=limitOne && ["year","territory","municipality","sex","age","site"].includes(field) && selected>0;
          group.querySelectorAll("input").forEach(input=>{
            input.disabled=(sexMustStayAll && !input.checked) || (singleValueOnly && !input.checked);
          });
          const clearAll=group.querySelector("[data-select-all]");
          if(clearAll)clearAll.disabled=!(sexMustStayAll || (singleValueOnly && selected>0));
        }
        updateRequiredMarkers();
        const asr=get("metric").querySelector('[value="asr"]');
        asr.disabled=Boolean(selectedCount("age") || dimension==="age_group");
        get("metric").dataset.compatError=asr.selected && asr.disabled ? t("El ajuste por edad requiere todos los grupos de edad y otra dimensión.") : "";
      }
      compatible();
      form.addEventListener("change",()=>{compatible();show(get("chart"),message(get("chart")));show(get("metric"),message(get("metric")));});
      form.addEventListener("input",updateApplyButton);
      form.addEventListener("change",updateApplyButton);
      updateApplyButton();
    }
    form.addEventListener("submit", (event) => {
      const errors=[];
      inputs.forEach((input) => { const text=message(input);show(input,text);if(text)errors.push({input,text}); });
      if (summary && links) {
        links.replaceChildren();
        errors.forEach(({input,text}) => {
          const li=document.createElement("li"),a=document.createElement("a");
          a.href="#"+input.id;a.textContent=(input.dataset.label || t("Campo"))+": "+text;
          a.addEventListener("click",(e)=>{e.preventDefault();input.focus();});li.append(a);links.append(li);
        });
        summary.hidden=!errors.length;
      }
      if (errors.length) {
        event.preventDefault();
        errors[0].input.focus();
        errors[0].input.scrollIntoView({block:"center",behavior:"instant"});
      }
    });
    if (summary && !summary.hidden && links?.children.length) summary.focus({preventScroll:false});
  });
})();
