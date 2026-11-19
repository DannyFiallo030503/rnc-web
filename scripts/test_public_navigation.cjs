/* Contract tests for public offline navigation, without a browser or health data. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const path=require('node:path');
const source=fs.readFileSync(process.env.RNC_WORKER_SOURCE||path.join(__dirname,'../static/js/service-worker.js'),'utf8');
const origin='https://rnc.example';
function fixtureResponse(url,status=200){
  const u=new URL(url,origin),lang=u.searchParams.get('__rnc_locale')||'es';
  const html=`<html lang="${lang}" data-server-connection="checking"><body data-page="${u.pathname}"><a data-admin-web-link hidden>Administración</a><div data-state="checking"><span class="connection-label">Comprobando conexión</span></div></body></html>`;
  const response=new Response(html,{status,headers:{'Content-Type':'text/html'}});
  Object.defineProperty(response,'url',{value:u.href});
  Object.defineProperty(response,'clone',{value:()=>fixtureResponse(u.href,status)});
  return response;
}
async function worker(initialFailure=0){
  const entries=new Map(),listeners={};let failure=initialFailure;
  const key=x=>new URL(x.url||x,origin).href;
  const cache={match:async x=>entries.get(key(x))?.clone(),put:async(x,r)=>entries.set(key(x),r.clone()),addAll:async paths=>{for(const p of paths)await cache.put(p,fixtureResponse(p));}};
  const self={location:{origin},navigator:{onLine:true},clients:{claim:async()=>{}},skipWaiting:async()=>{},addEventListener:(n,fn)=>listeners[n]=fn};
  const context={self,URL,Response,Headers,AbortSignal,Set,Map,Promise,console,caches:{open:async()=>cache,keys:async()=>[],delete:async()=>true,match:cache.match},fetch:async request=>{if(failure===-1)throw new TypeError('Server unavailable');return fixtureResponse(request.url||request,failure||200);}};
  vm.runInNewContext(source,context);
  let pending;listeners.install({waitUntil:p=>pending=p});await pending;
  const navigate=async target=>{let response;listeners.fetch({request:{url:new URL(target,origin).href,method:'GET',mode:'navigate',headers:new Headers({'accept-language':'es'})},respondWith:p=>response=p,waitUntil:()=>{}});return response?await response:null;};
  return {entries,cache,self,listeners,navigate,fail:value=>failure=value};
}
test('install prepares every public page in Spanish and English',async()=>{
 const w=await worker();
 for(const p of ['/','/el-rnc/','/consulta/','/nomencladores/'])for(const lang of ['es','en'])assert.ok(w.entries.has(`${origin}${p}?__rnc_locale=${lang}`),p+lang);
 assert.ok(w.entries.has(origin+'/static/js/about-tabs.js'));
});
test('server unavailable preserves each public page, language and first-paint offline state',async()=>{
 const w=await worker();w.fail(-1);
 for(const p of ['/','/el-rnc/','/consulta/','/nomencladores/'])for(const lang of ['es','en']){
  const r=await w.navigate(p+'?__rnc_locale='+lang),html=await r.text();assert.equal(r.status,200);assert.ok(html.includes(`data-page="${p}"`));assert.ok(html.includes(`lang="${lang}"`));assert.ok(html.includes('data-server-connection="offline"'));assert.ok(html.includes('data-state="offline"'));assert.ok(html.includes('>Offline</span>'));assert.ok(!html.includes('Comprobando conexión'));
 }
});
test('HTTP 503 uses the matching cached page rather than the error document',async()=>{
 const w=await worker();w.fail(503);const r=await w.navigate('/nomencladores/');assert.equal(r.status,200);assert.match(await r.text(),/data-page="\/nomencladores\/"/);
});
test('a missing public page never falls back to the query page',async()=>{
 const w=await worker();for(const k of w.entries.keys())if(new URL(k).pathname==='/')w.entries.delete(k);w.fail(-1);const r=await w.navigate('/');assert.equal(r.status,503);assert.ok(!(await r.text()).includes('data-page="/consulta/"'));
});
test('query aliases alone can share the query shell',async()=>{
 const w=await worker();w.fail(-1);for(const p of ['/consulta-offline/','/consulta-sintetica/'])assert.match(await(await w.navigate(p)).text(),/data-page="\/consulta\/"/);
});
test('private routes, cross-origin requests and package/probe fetches are not cached',async()=>{
 const w=await worker();for(const p of ['/acceso/','/administracion/','/cuenta/','/admin/','/paquete-offline.json','/conexion.json', 'https://other.example/'])assert.equal(await w.navigate(p),null,p);
 assert.ok(![...w.entries.keys()].some(k=>/\/(acceso|administracion|cuenta|admin)\//.test(new URL(k).pathname)));
});
test('explicit offline language beats a saved preference',async()=>{
 const w=await worker();let pending;w.listeners.message({data:{type:'rnc-language',language:'en',revision:2},waitUntil:p=>pending=p});await pending;w.fail(-1);
 assert.match(await(await w.navigate('/el-rnc/')).text(),/lang="en"/);
 assert.match(await(await w.navigate('/el-rnc/?__rnc_locale=es')).text(),/lang="es"/);
});

test('failed localized page preparation does not install a partial replacement',async()=>{
 await assert.rejects(worker(503),/Public page preparation failed/);
});
