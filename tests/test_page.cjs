// Exercise the embedded page without a browser or network connection.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../codex_usage_widget.py'), 'utf8');
const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
const sample = {plan:'plus', windows:[{label:'5h',remainingPercent:75,resetsAt:1800000000}], fetchedAt:1700000000};
const tick = () => new Promise(resolve => setImmediate(resolve));

function page(fetch) {
  const elements = {};
  const context = vm.createContext({
    document: {title:'',getElementById(id) {
      return elements[id] ??= {textContent:'',innerHTML:'',disabled:false,addEventListener(){}};
    }},
    fetch, AbortController, setTimeout:()=>1, clearTimeout(){},setInterval:()=>1,clearInterval(){},
  });
  vm.runInContext(script, context);
  return {context,elements,run:code=>vm.runInContext(code,context)};
}

(async () => {
  let calls=[];
  let fail=false;
  const p = page(async (url, options)=>{
    calls.push([url,options]);
    return {ok:!fail,json:async()=>fail ? {error:'offline'} : sample};
  });
  await tick();
  assert.equal(p.context.document.title,'Codex Usage | 75% 5h');
  const previous=p.elements.updated.textContent;
  fail=true;
  await p.run('refresh(true)');
  assert.equal(calls.at(-1)[0],'/api/usage?refresh=1');
  assert.equal(p.elements.error.textContent,'offline');
  assert.equal(p.elements.updated.textContent,previous+' · Update failed');
  assert.match(p.elements.limits.innerHTML,/75%/);
  fail=false;
  await p.run('refresh()');
  assert.equal(p.elements.error.textContent,'');
  assert.equal(p.context.document.title,'Codex Usage | 75% 5h');

  const failed = page(async()=>({ok:false,json:async()=>({error:'network error'})}));
  await tick();
  assert.equal(failed.elements.plan.textContent,'Usage unavailable');

  let resolvePending;
  let count=0;
  const pending=page((url,options)=>{
    count++;
    if (url==='/api/shutdown') {
      assert.equal(options.method,'POST');
      assert.ok(options.headers['X-Widget-Token']);
      return Promise.resolve({ok:true});
    }
    return new Promise(resolve=>{resolvePending=resolve;});
  });
  await pending.run('refresh()');
  assert.equal(count,1,'overlapping refresh must be ignored');
  await pending.run('stopWidget()');
  resolvePending({ok:true,json:async()=>sample});
  await tick();
  assert.equal(pending.context.document.title,'Codex Usage | Stopped');
  assert.equal(pending.elements.refresh.disabled,true);
  assert.equal(pending.elements.stop.disabled,true);
  await pending.run('refresh()');
  assert.equal(count,2,'stopped page must not fetch again');
  console.log('Page checks passed: fresh refresh, stale display, recovery, initial error, in-flight shutdown.');
})().catch(error=>{console.error(error);process.exitCode=1;});
