"use strict";
(() => {
  const form=document.querySelector(".language-picker");if(!form)return;
  let cookieSynchronized=false, synchronizing=false, applying=false, cookieTask=Promise.resolve();
  const supported=new Set([...form.querySelectorAll("option")].map(option=>option.value));
  const save=language=>{const preference={language,revision:Date.now()};try{localStorage.setItem("rnc-language-preference",JSON.stringify(preference));}catch{}navigator.serviceWorker?.controller?.postMessage({type:"rnc-language",...preference,offlineUnavailable:document.documentElement.dataset.offlineUnavailable || ""});};
  function synchronize(language) {
    cookieTask=cookieTask.catch(()=>{}).then(async()=>{
      const data=new FormData(form);data.set("language",language);
      const response=await fetch(form.action,{method:"POST",body:data,credentials:"same-origin",cache:"no-store"});if(!response.ok)throw new Error("Language update failed");cookieSynchronized=true;form.dataset.cookieLanguage=language;
    });
    return cookieTask;
  }

  form.addEventListener("submit",async event=>{
    event.preventDefault();event.stopImmediatePropagation();
    const language=form.elements.namedItem("language").value;if(!supported.has(language))return;
    const button=form.querySelector("button");button.disabled=true;applying=true;save(language);
    try{await synchronize(language);}catch{ /* Cached locale shell remains available offline. */ }
    const url=new URL(location.href);url.searchParams.set("__rnc_locale",language);location.assign(url.href);
  });
  form.dataset.localeBound="true";
  const restoreCookie=()=>{const language=form.elements.namedItem("language").value || document.documentElement.lang;if(applying || cookieSynchronized || synchronizing || !supported.has(language))return;synchronizing=true;synchronize(language).catch(()=>{}).finally(()=>{synchronizing=false;});};
  addEventListener("online",restoreCookie);
  document.addEventListener("rnc-connection",event=>{if(event.detail.online)restoreCookie();});

})();
