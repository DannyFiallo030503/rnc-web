/* Browser regression on a task-owned public server and temporary Chrome profile.
 * Reads an existing public aggregate publication; never opens or writes clinical input.
 * Usage: node scripts/review_public_navigation.cjs /absolute/public_releases
 */
const fs=require('node:fs/promises'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process');const net=require('node:net');const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),release=process.argv[2];if(!release)throw Error('Public release root is required');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label,timeout=30000){const end=Date.now()+timeout;while(Date.now()<end){try{const v=await fn();if(v)return v;}catch{}await delay(100);}throw Error('Timeout: '+label);}
async function freePort(){const s=net.createServer();await new Promise(r=>s.listen(0,'127.0.0.1',r));const p=s.address().port;await new Promise(r=>s.close(r));return p;}
(async()=>{
 const port=await freePort(),origin=`http://127.0.0.1:${port}`,profile=await fs.mkdtemp(path.join(os.tmpdir(),'rnc-navigation-'));
 let server,chrome,ws;const checks=[];
 const check=(label,condition)=>{assert.ok(condition,label);checks.push(label);};
 const startServer=async()=>{server=spawn(path.join(root,'.venv/bin/python'),['manage.py','runserver',`127.0.0.1:${port}`,'--noreload'],{cwd:root,env:{...process.env,DJANGO_SETTINGS_MODULE:'config.settings_public',RNC_PUBLIC_RELEASE_ROOT:path.resolve(release)},stdio:'ignore'});await until(async()=>(await fetch(origin+'/conexion.json')).ok,'public server');};
 const stopServer=async()=>{const p=server;if(p&&p.exitCode===null){const stopped=new Promise(r=>p.once('exit',r));p.kill('SIGTERM');await stopped;}server=null;};
 try{
  await startServer();
  chrome=spawn('/usr/bin/google-chrome',['--headless=new','--no-sandbox','--disable-extensions','--disable-dev-shm-usage','--disable-background-networking','--force-prefers-reduced-motion','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{stdio:'ignore'});
  const debug=await until(async()=>Number((await fs.readFile(path.join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]),'Chrome');
  const tabs=await(await fetch(`http://127.0.0.1:${debug}/json`)).json();ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let seq=0;const pending=new Map();const errors=[];
  ws.onmessage=event=>{const m=JSON.parse(event.data);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(Error(m.error.message)):p.resolve(m.result);}}else if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const id=++seq;pending.set(id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error('Browser evaluation failed');return r.result?.value;};
  await call('Page.enable');await call('Runtime.enable');await call('Network.enable');
  await call('Page.addScriptToEvaluateOnNewDocument',{source:`window.__adminFlash=false;window.__checkingFlash=false;const inspect=()=>{const state=document.querySelector('#connection-status')?.dataset.state;const visible=[...document.querySelectorAll('[data-admin-web-link]')].some(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden');if(state!=='online'&&visible)window.__adminFlash=true;if(sessionStorage.getItem('qa-offline')==='true'&&state==='checking')window.__checkingFlash=true;};new MutationObserver(inspect).observe(document,{childList:true,subtree:true,attributes:true});const paint=()=>{inspect();requestAnimationFrame(paint);};requestAnimationFrame(paint);`});
  const go=async(route,state='offline')=>{await call('Page.navigate',{url:origin+route});await until(()=>evaluate(`document.readyState==='complete' && location.pathname===${JSON.stringify(new URL(route,origin).pathname)} && document.querySelector('#connection-status')?.dataset.state===${JSON.stringify(state)}`),'navigate '+route,45000);await delay(400);check('URL preserved '+route,await evaluate(`location.pathname===${JSON.stringify(new URL(route,origin).pathname)}`));check('no admin flash '+route,await evaluate('!window.__adminFlash'));if(state==='offline'){check('offline at first paint '+route,await evaluate('!window.__checkingFlash'));check('admin hidden '+route,await evaluate('[...document.querySelectorAll("[data-admin-web-link]")].every(e=>!e.getClientRects().length)'));}};
  await go('/consulta/?dimension=sex&chart=bar&cohort=adult','online');
  await until(()=>evaluate('Boolean(navigator.serviceWorker.controller && document.querySelector("#connection-status")?.dataset.offlineReady==="true")'),'prepared public package',60000);
  check('online web admin available',await evaluate('[...document.querySelectorAll("[data-admin-web-link]")].some(e=>e.getClientRects().length)'));
  check('all static pages precached before visiting',await evaluate(`(async()=>{const key=(await caches.keys()).find(k=>k.startsWith('rnc-public-shell-'));const cache=await caches.open(key);return (await Promise.all(['/','/el-rnc/','/nomencladores/'].flatMap(p=>['es','en'].map(l=>cache.match(p+'?__rnc_locale='+l))))).every(Boolean)})()`));
  await evaluate('sessionStorage.setItem("qa-offline","true")');
  await call('Network.emulateNetworkConditions',{offline:true,latency:0,downloadThroughput:0,uploadThroughput:0});
  for(const route of ['/','/el-rnc/#que-hacemos','/nomencladores/']){await go(route);check('static content is not a query '+route,await evaluate('!document.querySelector("#query-form")'));}
  await evaluate(`document.querySelector('.sidebar-pages a[href="/"]').click()`);
  await until(()=>evaluate('location.pathname==="/" && document.readyState==="complete"'),'home link');
  await evaluate(`document.querySelector('.sidebar-pages a[href="/el-rnc/"]').click()`);
  await until(()=>evaluate('location.pathname==="/el-rnc/" && document.readyState==="complete"'),'about link');
  await evaluate(`document.querySelector('.sidebar-pages a[href="/nomencladores/"]').click()`);
  await until(()=>evaluate('location.pathname==="/nomencladores/" && document.readyState==="complete"'),'nomenclator link');
  await evaluate('history.back()');await until(()=>evaluate('location.pathname==="/el-rnc/" && document.readyState==="complete"'),'offline history back');check('history back preserves static page',await evaluate('!document.querySelector("#query-form") && !window.__adminFlash'));
  await evaluate('history.forward()');await until(()=>evaluate('location.pathname==="/nomencladores/" && document.readyState==="complete"'),'offline history forward');check('history forward preserves static page',await evaluate('!document.querySelector("#query-form") && !window.__adminFlash'));
  await go('/el-rnc/#que-hacemos');check('about sections operate offline',await evaluate('Boolean(document.getElementById("que-hacemos")?.getClientRects().length)'));
  await evaluate(`document.querySelector('.sidebar-pages a[href="/consulta/"]').click()`);
  await until(()=>evaluate('location.pathname==="/consulta/" && document.documentElement.dataset.queryMode==="local"'),'query link from static page');check('static to query navigation mounts local explorer',true);
  await evaluate(`const f=document.querySelector('#query-form');f.elements.dimension.value='sex';f.elements.dimension.dispatchEvent(new Event('change',{bubbles:true}));`);
  await until(()=>evaluate('document.documentElement.dataset.queryMode==="local" && new URLSearchParams(location.search).get("dimension")==="sex"'),'local filters');check('local query still updates',true);
  await go('/nomencladores/?__rnc_locale=en');check('English static page available offline',await evaluate('document.documentElement.lang==="en"'));
  await go('/el-rnc/?__rnc_locale=en#que-hacemos');check('English about available offline',await evaluate('document.documentElement.lang==="en"'));
  await go('/?__rnc_locale=es');await call('Page.reload');await until(()=>evaluate('document.readyState==="complete" && location.pathname==="/" && document.querySelector("#connection-status")?.dataset.state==="offline"'),'offline reload');check('home reload keeps home',true);
  await stopServer();
  await call('Network.emulateNetworkConditions',{offline:false,latency:0,downloadThroughput:-1,uploadThroughput:-1});
  check('network remains online while server is stopped',await evaluate('navigator.onLine'));
  for(const route of ['/','/el-rnc/#que-hacemos','/nomencladores/','/consulta/?dimension=sex&chart=table'])await go(route);
  await until(()=>evaluate('document.documentElement.dataset.queryMode==="local"'),'server down local query');check('query works with stopped server',true);
  check('private responses not present in cache',await evaluate(`(async()=>{for(const k of await caches.keys())for(const r of await(await caches.open(k)).keys())if(/^\\/(acceso|administracion|cuenta|admin)\\//.test(new URL(r.url).pathname))return false;return true;})()`));
  await evaluate(`new Promise((resolve,reject)=>{const r=indexedDB.open('rnc-public-offline',2);r.onsuccess=()=>{const db=r.result,tx=db.transaction('package','readwrite');tx.objectStore('package').delete('active');tx.oncomplete=()=>{db.close();resolve(true)};tx.onerror=reject};r.onerror=reject})`);
  for(const route of ['/','/el-rnc/','/nomencladores/']){await go(route);check('static page independent of aggregate package '+route,await evaluate('document.querySelector("#connection-status").dataset.offlineReady==="false"'));}
  await startServer();await evaluate('sessionStorage.removeItem("qa-offline");window.dispatchEvent(new Event("online"))');await until(()=>evaluate('document.querySelector("#connection-status")?.dataset.state==="online"'),'reconnect');
  check('admin restored after server recovery',await evaluate('[...document.querySelectorAll("[data-admin-web-link]")].some(e=>e.getClientRects().length)'));
  await evaluate(`window.__realFetch=window.fetch;window.fetch=(url,options)=>String(url)==='/conexion.json'?new Promise(resolve=>setTimeout(()=>resolve(new Response(JSON.stringify({online:true,publication:null}),{headers:{'Content-Type':'application/json'}})),250)):window.__realFetch(url,options);window.dispatchEvent(new Event('online'));window.dispatchEvent(new Event('offline'));`);
  await delay(450);check('stale successful probe cannot override offline event',await evaluate('document.querySelector("#connection-status").dataset.state==="offline" && [...document.querySelectorAll("[data-admin-web-link]")].every(e=>!e.getClientRects().length)'));
  await evaluate('window.fetch=window.__realFetch;window.dispatchEvent(new Event("online"))');await until(()=>evaluate('document.querySelector("#connection-status").dataset.state==="online"'),'real probe restored');
  await evaluate('Object.defineProperty(navigator,"standalone",{value:true,configurable:true});window.dispatchEvent(new Event("online"))');await until(()=>evaluate('[...document.querySelectorAll("[data-admin-web-link]")].every(e=>!e.getClientRects().length)'),'standalone guard');check('standalone does not expose admin',true);
  check('no uncaught browser exceptions',errors.length===0);
  console.log(JSON.stringify({status:'pass',checks:checks.length,scenarios:checks,server_down:'task-owned Django process actually terminated; navigator.onLine stayed true',standalone:'simulated navigator.standalone, not OS installation'},null,2));
 }finally{
  ws?.close();if(chrome&&chrome.exitCode===null){const exit=new Promise(r=>chrome.once('exit',r));chrome.kill('SIGTERM');await exit;}await stopServer();await fs.rm(profile,{recursive:true,force:true,maxRetries:10,retryDelay:100});
 }
})().catch(error=>{console.error(error.stack);process.exitCode=1;});
