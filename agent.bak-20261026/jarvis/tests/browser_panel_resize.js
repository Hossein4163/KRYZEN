/* Run at a fresh fixture page, with the target viewport already set. */
(async()=>{
  if(!(await fetch('/api/fixture').then(r=>r.json())).fixture)throw Error('Fixture required');
  const q=s=>document.querySelector(s),pause=ms=>new Promise(r=>setTimeout(r,ms)),check=(v,m)=>{if(!v)throw Error(m);};
  jarvisStudio.setMode('mesh',false);await pause(250);
  const phone=innerWidth<=760,tablet=innerWidth>760&&innerWidth<1200;
  chatCollapsed=sideCollapsed=false;applyLayoutCollapses();await pause(100);
  const results=[];
  for(const name of ['chat','side']){
    const panel=q(name==='chat'?'#chatPanel':'#sidePanel'),handle=q('#'+name+'PanelResize');
    check(handle&&!handle.hidden,'Missing '+name+' resize handle');
    const vertical=handle.getAttribute('aria-orientation')==='vertical';
    check(vertical===(!phone&&!(tablet&&name==='side')),'Wrong resize axis for '+name);
    const size=()=>vertical?panel.getBoundingClientRect().width:panel.getBoundingClientRect().height;
    handle.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));await pause(100);
    const before=size(),key=vertical?(name==='side'?'ArrowLeft':'ArrowRight'):(tablet?'ArrowUp':'ArrowDown');
    handle.dispatchEvent(new KeyboardEvent('keydown',{key,bubbles:true}));await pause(100);
    check(Math.abs(size()-before-10)<2,name+' keyboard resizing failed');
    const saved=JSON.parse(localStorage.getItem('kryzen.panel-sizes.v1'));
    check(saved[phone?'phone':tablet?'tablet':'desktop'][name]>=before+9,'Size was not persisted');
    handle.dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}));await pause(100);
    check(size()<=Number(handle.getAttribute('aria-valuemax'))+2,name+' exceeded maximum');
    check(document.documentElement.scrollWidth<=innerWidth+1,'Panel resizing caused horizontal overflow');
    handle.dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true}));await pause(100);
    check(size()>=Number(handle.getAttribute('aria-valuemin'))-2,name+' fell below minimum');
    handle.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));await pause(100);
    results.push(name+' supports keyboard resize, bounds, persistence and reset');
  }
  chatCollapsed=sideCollapsed=true;applyLayoutCollapses();await pause(100);
  check(q('#chatPanelResize').hidden&&q('#sidePanelResize').hidden,'Collapsed panels still show resize handles');
  chatCollapsed=sideCollapsed=false;applyLayoutCollapses();jarvisStudio.setMode('code',false);await pause(150);
  check(q('#sidePanelResize').hidden&&!q('#chatPanelResize').hidden,'Workspace switch exposes inactive splitter');
  jarvisStudio.setMode('mesh',false);await pause(100);
  results.push('collapse and workspace switching hide inactive splitters');
  return {ok:true,viewport:[innerWidth,innerHeight],passed:results.length,checks:results};
})()
