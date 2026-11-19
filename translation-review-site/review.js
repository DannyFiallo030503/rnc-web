const PAGE_SIZE = 60;
let catalogData;
let visibleRows = [];
let displayed = 0;

const languageSelect = document.querySelector("#language");
const domainSelect = document.querySelector("#domain");
const searchInput = document.querySelector("#search");
const statusSelect = document.querySelector("#status");
const messages = document.querySelector("#messages");
const loadMore = document.querySelector("#load-more");

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function renderLanguageOptions() {
  catalogData.languages.forEach(language => {
    const option = document.createElement("option");
    option.value = language.code;
    option.textContent = `${language.nativeName} · ${language.englishName}${language.draft ? " · borrador / draft" : ""}`;
    languageSelect.append(option);
  });
}

function collectRows(language) {
  const domains = domainSelect.value === "all" ? ["django", "djangojs"] : [domainSelect.value];
  return domains.flatMap(domain => language.domains[domain].map((row, index) => ({
    ...row, domain, index,
  })));
}

function drawCard(row, language) {
  const card = document.createElement("article");
  card.className = `message-card${row.missing ? " is-missing" : ""}`;
  card.lang = language.code;
  card.dir = language.rtl ? "rtl" : "auto";
  const context = row.context ? `<span class="context">${escapeHTML(row.context)}</span>` : "";
  const origin = row.origin === "source" ? "Texto fuente / Source text (español)" : "Propuesta / Proposal";
  const sourceLabel = row.domain === "djangojs" ? "Texto fuente / Source text (inglés)" : "Texto fuente / Source text (español)";
  const markers = [
    row.fuzzy ? '<span class="tag pending">Pendiente / Pending</span>' : "",
    row.missing ? '<span class="tag missing">Sin propuesta / Missing</span>' : "",
    row.origin === "source" ? '<span class="tag source-tag">Idioma fuente / Source</span>' : "",
  ].join("");
  const refs = row.references?.length
    ? `<small class="reference">${escapeHTML(row.references.join(" · "))}</small>` : "";
  card.innerHTML = `${context}<div class="card-head"><span>${row.domain === "django" ? "Portal / administración · Portal / administration" : "JavaScript / PWA"}</span><span>${markers}</span></div><div class="text-pair"><div><small>${sourceLabel}</small><p lang="${row.domain === "djangojs" ? "en" : "es"}" dir="auto">${escapeHTML(row.source)}</p></div><div class="target"><small>${origin} · ${escapeHTML(language.nativeName)}</small><p>${escapeHTML(row.target || "(sin propuesta / no proposal)")}</p></div></div>${row.pluralSource ? `<details><summary>Ver plural / View plural form</summary><p lang="en">${escapeHTML(row.pluralSource)}</p></details>` : ""}${refs}`;
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-reference";
  copyButton.textContent = "Copiar referencia / Copy reference";
  copyButton.addEventListener("click", async () => {
    const reference = [
      `Language: ${language.code} (${language.nativeName})`,
      `Domain: ${row.domain}`,
      row.context ? `Context: ${row.context}` : "",
      `Source: ${row.source}`,
      `Proposal: ${row.target}`,
      row.references?.length ? `Code reference: ${row.references.join(", ")}` : "",
    ].filter(Boolean).join("\n");
    try {
      await navigator.clipboard.writeText(reference);
      copyButton.textContent = "Copiado / Copied";
      window.setTimeout(() => {
        copyButton.textContent = "Copiar referencia / Copy reference";
      }, 1800);
    } catch {
      const textarea = document.createElement("textarea");
      textarea.className = "copy-fallback";
      textarea.readOnly = true;
      textarea.setAttribute("aria-label", "Referencia para comentarios / Feedback reference");
      textarea.value = reference;
      textarea.style.cssText = "display:block;width:100%;min-height:8rem;margin-top:.75rem;padding:.6rem;border:1px solid #c8d6d2;border-radius:.5rem;font: .8rem ui-monospace,monospace";
      card.append(textarea);
      textarea.focus();
      textarea.select();
      copyButton.textContent = "Selecciona y copia la referencia / Select and copy the reference";
    }
  });
  card.append(copyButton);
  return card;
}

function render() {
  const language = catalogData.languages.find(item => item.code === languageSelect.value);
  if (!language) return;
  document.documentElement.lang = language.code;
  document.documentElement.dir = language.rtl ? "rtl" : "ltr";
  const query = searchInput.value.trim().toLocaleLowerCase();
  const status = statusSelect.value;
  const allRows = collectRows(language);
  const fuzzyCount = allRows.filter(row => row.fuzzy).length;
  const missingCount = allRows.filter(row => row.missing).length;
  visibleRows = allRows.filter(row => {
    if (status === "fuzzy" && !row.fuzzy) return false;
    if (status === "missing" && !row.missing) return false;
    return !query || [row.source, row.target, row.context, ...(row.references || [])]
      .some(value => String(value).toLocaleLowerCase().includes(query));
  });
  document.querySelector("#shown-count").textContent = visibleRows.length.toLocaleString(language.code);
  document.querySelector("#draft-count").textContent = fuzzyCount.toLocaleString(language.code);
  document.querySelector("#missing-count").textContent = missingCount.toLocaleString(language.code);
  document.querySelector("#language-status").textContent = language.draft
    ? "Borrador sin aprobación; cada mensaje requiere revisión humana. / Unapproved draft; every message needs human review."
    : language.code === "es"
      ? "Español es el idioma fuente del portal. / Spanish is the portal source language."
      : "El catálogo inglés es parcial y requiere revisión. / The English catalog is partial and needs review.";
  messages.replaceChildren();
  displayed = 0;
  appendRows(language);
}

function appendRows(language) {
  const nextRows = visibleRows.slice(displayed, displayed + PAGE_SIZE);
  nextRows.forEach(row => messages.append(drawCard(row, language)));
  displayed += nextRows.length;
  loadMore.hidden = displayed >= visibleRows.length;
}

fetch("translations.json")
  .then(response => {
    if (!response.ok) throw new Error("No se pudieron cargar los catálogos.");
    return response.json();
  })
  .then(data => {
    catalogData = data;
    renderLanguageOptions();
    const preferred = new URLSearchParams(location.search).get("lang");
    if (preferred && catalogData.languages.some(language => language.code === preferred)) {
      languageSelect.value = preferred;
    }
    render();
  })
  .catch(() => {
    messages.textContent = "No se pudo abrir el inventario de traducciones. Recarga la página o informa del problema al responsable del prototipo.";
  });

languageSelect.addEventListener("change", render);
domainSelect.addEventListener("change", render);
statusSelect.addEventListener("change", render);
searchInput.addEventListener("input", render);
loadMore.addEventListener("click", () => appendRows(catalogData.languages.find(item => item.code === languageSelect.value)));
