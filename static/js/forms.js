"use strict";
(() => {
  const rules = {
    username: /^[A-Za-z0-9._-]+$/u,
    "person-name": /^[\p{L}\p{M} '’-]+$/u,
    "plain-text": /^[\p{L}\p{M}\p{N}_ \n.,;:()'·’–—+/%&!?@#-]+$/u,
    search: /^[\p{L}\p{M}\p{N}_ .@+'’-]*$/u,
    email: /^[A-Za-z0-9.!#$%&'*+\/=?^_`{|}~@-]+$/u,
  };
  const validCharacters = (input, value) => !rules[input.dataset.rule] || !value || rules[input.dataset.rule].test(value.normalize("NFC").replace(/\u00a0/g," "));
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
    }
    function message(input) {
      const value = input.type === "file" ? (input.files[0]?.name || "") : input.value;
      if (input.required && (input.type === "checkbox" ? !input.checked : !value.trim()))
        return input.type === "checkbox" ? "Marque esta confirmación para continuar." : "Complete este campo.";
      if (!value) return "";
      if(input.dataset.compatError) return input.dataset.compatError;
      if (!validCharacters(input, value)) return input.dataset.ruleMessage || "Revise los caracteres introducidos en este campo.";
      if (input.minLength > 0 && value.length < input.minLength) return `Use al menos ${input.minLength} caracteres.`;
      if (input.maxLength > 0 && value.length > input.maxLength) return `Use como máximo ${input.maxLength} caracteres.`;
      if (input.type === "email" && input.validity.typeMismatch) return "Escriba un correo válido; por ejemplo, nombre@dominio.cu.";
      if (input.type === "file") {
        if (!value.toLowerCase().endsWith(".csv")) return "Seleccione un archivo con extensión .csv.";
        if (input.files[0].size > Number(input.dataset.maxBytes || Infinity)) return "El archivo supera el límite de 12 MB.";
      }
      if (input.dataset.rule === "person-name" && !/^[\p{L}\p{M}]+(?:[ '’-][\p{L}\p{M}]+)*$/u.test(value.normalize("NFC").replace(/\u00a0/g," ").trim())) return "Separe los nombres con un espacio, apóstrofo o guion; sin signos al comienzo o al final.";
      if (input.dataset.rule === "new-password" && /^\d+$/u.test(value)) return "La contraseña no puede contener solo números.";
      if (input.dataset.matches && value !== form.elements.namedItem(input.dataset.matches)?.value) return "Las contraseñas no coinciden. Vuelva a escribir la misma contraseña.";
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
        event.preventDefault();show(input,`No se incorporó el texto: use como máximo ${input.maxLength} caracteres.`);return;
      }
      if (!validCharacters(input, value)) {
        event.preventDefault();
        show(input, "No se incorporó el texto no permitido. " + (input.dataset.ruleMessage || "Revise el formato de este campo."));
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
      input.addEventListener("change", () => { if(input.type==="file") { const label=input.closest("[data-field]")?.querySelector("[data-file-name]");if(label)label.textContent=input.files[0]?.name || "No se ha seleccionado un archivo";} validate(input); });
      input.addEventListener("compositionend", () => validate(input));
    });
    if (form.matches("[data-query-form]")) {
      const get=(name)=>form.elements.namedItem(name);
      function compatible() {
        const dimension=get("dimension").value,metric=get("metric").value,unit=get("unit").value;
        for(const option of get("chart").options) {
          let reason="";
          if(option.value==="line" && dimension!=="period") reason="Las líneas requieren comparar por período.";
          if(["grouped","stacked","percent"].includes(option.value) && (get("sex").value || dimension==="sex")) reason="La comparación por sexo requiere ambos sexos y otra dimensión.";
          if(["stacked","percent"].includes(option.value) && metric!=="count") reason="Las barras apiladas requieren frecuencias absolutas.";
          if(["pie","doughnut"].includes(option.value) && (!["count","share"].includes(metric) || (unit==="persons" && dimension!=="sex"))) reason="La composición requiere categorías excluyentes; para personas, compare por sexo.";
          option.disabled=Boolean(reason);option.title=reason;
          if(option.selected)get("chart").dataset.compatError=reason;
        }
        const asr=get("metric").querySelector('[value="asr"]');
        asr.disabled=Boolean(get("age").value || dimension==="age_group");
        get("metric").dataset.compatError=asr.selected && asr.disabled ? "El ajuste por edad requiere todos los grupos de edad y otra dimensión." : "";
      }
      compatible();
      form.addEventListener("change",()=>{compatible();show(get("chart"),message(get("chart")));show(get("metric"),message(get("metric")));});
    }
    form.addEventListener("submit", (event) => {
      const errors=[];
      inputs.forEach((input) => { const text=message(input);show(input,text);if(text)errors.push({input,text}); });
      if (summary && links) {
        links.replaceChildren();
        errors.forEach(({input,text}) => {
          const li=document.createElement("li"),a=document.createElement("a");
          a.href="#"+input.id;a.textContent=(input.dataset.label || "Campo")+": "+text;
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
