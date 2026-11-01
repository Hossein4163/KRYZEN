/* Run at a 390px viewport against the disposable fixture. */
(async()=>{
  if(!(await fetch('/api/fixture').then(r=>r.json())).fixture)throw new Error('Fixture required');
  const q=s=>document.querySelector(s),checks=[],pause=ms=>new Promise(r=>setTimeout(r,ms));
  const check=(v,m)=>{if(!v)throw new Error(m);};
  async function wait(fn,m){for(let i=0;i<200;i++){if(fn())return;await pause(25);}throw new Error(m);}
  const usable=(selector)=>{const rect=q(selector).getBoundingClientRect();check(rect.width>=40&&rect.height>=40,selector+' target is too small: '+rect.width+'×'+rect.height);};
  check(innerWidth<=430,'Run the responsive check at a phone viewport');
  jarvisStudio.setMode('mesh',false);await wait(()=>meshMobile,'Mobile mesh did not render');
  check(document.documentElement.scrollWidth===innerWidth,'Mobile mesh overflows the document');
  ['#meshMotion','#meshReset','#meshZoomIn','#meshZoomOut','#meshZoomLabel','#meshFit','#addAgent','#syncN8n'].forEach(usable);
  document.querySelectorAll('.mesh-bar [data-layer]').forEach(control=>{const rect=control.getBoundingClientRect();check(rect.width>=40&&rect.height>=40,'Mesh layer target is too small');});
  checks.push('phone mesh has usable touch targets and no horizontal overflow');
  jarvisStudio.setMode('flow',false);await wait(()=>q('#flowViewport')&&q('#flowActivate'),'Flow did not load');
  ['#flowAddNote','#flowActivate','#flowCenterSelected','#flowDeselect','#flowZoomIn','#flowZoomOut','#flowFit'].forEach(usable);
  const route=q('.flow-routing .routing-badge')||q('.flow-route-status');
  check(route&&getComputedStyle(route).display!=='none'&&route.getBoundingClientRect().width>0,'Routing state is hidden on mobile');
  checks.push('phone flow controls have usable touch targets and visible routing state');
  const generated=[...document.querySelectorAll('[data-flow]')].find(el=>el.dataset.flow==='DevPilot Flow.canvas');
  generated.click();await wait(()=>jarvisStudio.state.flow?.name==='DevPilot Flow.canvas','Generated flow did not load');
  check(q('.flow-readonly')&&getComputedStyle(q('.flow-readonly')).display!=='none','Read-only badge is hidden on mobile');
  check(q('#flowAddNote').disabled&&q('#flowAddAgent').disabled,'Generated canvas editing is not disabled');
  check(document.documentElement.scrollWidth===innerWidth,'Mobile flow overflows the document');
  checks.push('generated flow keeps its read-only state visible and enforced on phones');
  return{ok:true,passed:checks.length,checks};
})()
