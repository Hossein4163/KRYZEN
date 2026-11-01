/* Real interaction checks against tests/browser_fixture.py only. */
(async () => {
  const marker = await fetch('/api/fixture').then(r=>r.json());
  if (!marker.fixture) throw new Error('Refusing to modify a non-fixture workspace');
  const q=s=>document.querySelector(s), checks=[];
  const pause=ms=>new Promise(r=>setTimeout(r,ms));
  const check=(value,message)=>{if(!value)throw new Error(message);};
  async function wait(fn,message){for(let i=0;i<200;i++){if(fn())return;await pause(25);}throw new Error(message);}
  await wait(()=>window.jarvisStudio&&cfg?.agents?.length,'UI did not load');
  jarvisStudio.setMode('mesh',false);
  check(q('#meshMotion')&&q('#meshReset')&&q('#meshFit'),'Mesh navigation controls are missing');
  check(q('#meshSummary').textContent.includes('11'),'Mesh count does not match configured agents');
  check(document.querySelectorAll('.agent-node').length===cfg.agents.length,'Mesh lost configured agents');
  checks.push('mesh displays the configured team and grouped navigation controls');

  q('#meshReset').click();
  const node=q('#n-Marketing_Agent'), initial=[...pos['Marketing Agent']];
  const edge=q('#e-Marketing_Agent'), edgeBefore=edge.getAttribute('d');
  node.focus();node.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  check(pos['Marketing Agent'][0]>initial[0]&&pos['Marketing Agent'][1]===initial[1],'Arrow key did not move the agent');
  check(edge.getAttribute('d')!==edgeBefore,'Connection did not follow the moved agent');
  check(!q('#overlay').classList.contains('on'),'Moving an agent opened its editor');
  const firstMove=pos['Marketing Agent'][0];
  node.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',shiftKey:true,bubbles:true}));
  check(pos['Marketing Agent'][1]-initial[1]>firstMove-initial[0],'Shift did not increase movement distance');
  checks.push('keyboard node movement updates connections without opening configuration');

  const zoomBefore=q('#meshZoomLabel').textContent;q('#meshZoomIn').click();
  check(q('#meshZoomLabel').textContent!==zoomBefore,'Mesh zoom did not change');q('#meshFit').click();
  const pressed=q('#meshMotion').getAttribute('aria-pressed');q('#meshMotion').click();
  check(q('#meshMotion').getAttribute('aria-pressed')!==pressed,'Motion control does not expose its state');q('#meshMotion').click();
  for(const control of document.querySelectorAll('.mesh-bar [data-layer]')){
    const layer=control.dataset.layer, enabled=control.getAttribute('aria-pressed');
    control.click();check(control.getAttribute('aria-pressed')!==enabled,'Layer toggle state did not change');
    check(svg.classList.contains('no-'+layer),'Layer was not hidden');control.click();
  }
  checks.push('mesh zoom, fit, motion and layer controls change real state');

  const appearanceMotion=meshAppearanceMotion;
  try {
    applyUIValues({motion:false});
    check(q('#meshMotion').disabled&&q('#meshMotion').getAttribute('aria-pressed')==='false','Appearance motion setting was ignored');
    check(svg.classList.contains('motion-off')&&svg.animationsPaused(),'SVG activity animation was not paused');
    check(getComputedStyle(q('.agent-surface')).animationName==='none','Ambient card animation still runs');
  } finally {applyUIValues({motion:appearanceMotion});}
  checks.push('appearance motion preference pauses ambient and SVG animations');

  setActive('Marketing Agent',true);
  check(q('#n-Marketing_Agent').classList.contains('active'),'Live agent state was not shown');
  setActive('Marketing Agent',false);
  check(!q('#n-Marketing_Agent').classList.contains('active'),'Agent remained live after its work ended');
  checks.push('agent activity state follows real runtime hooks');

  q('#meshReset').click();
  check(pos['Marketing Agent'][0]===initial[0]&&pos['Marketing Agent'][1]===initial[1],'Reset did not restore default layout: '+JSON.stringify({initial,reset:pos['Marketing Agent'],mode:meshMode()}));
  q('#n-Marketing_Agent').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  window.__meshExpectedPosition=[...pos['Marketing Agent']];
  checks.push('Reset restores layout and subsequent moves can be persisted');

  const before=await api('/api/studio/flows');
  const made=await api('/api/studio/flow-create',{name:'Mesh interaction QA '+Date.now()});
  check(made.ok,'Could not prepare temporary test canvas');
  const canvas={nodes:[
    {id:'qa-lead',type:'file',file:'_DevPilot/Agents/Orchestrator.md',x:0,y:0,width:260,height:160},
    {id:'qa-build',type:'file',file:'_DevPilot/Agents/Build Agent.md',x:400,y:240,width:260,height:160},
    {id:'qa-note',type:'text',text:'# Design QA\nVerify controls',x:0,y:240,width:260,height:160}],
    edges:[{id:'qa-handoff',fromNode:'qa-lead',fromSide:'right',toNode:'qa-build',toSide:'left',label:'verify'}]};
  const loaded=await api('/api/studio/flow?name='+encodeURIComponent(made.name));
  check((await api('/api/studio/flow',{name:made.name,revision:loaded.revision,canvas})).ok,'Could not save test canvas');
  jarvisStudio.setMode('flow',false);
  await wait(()=>q('[data-flow="'+made.name+'"]'),'Canvas library did not load');
  q('[data-flow="'+made.name+'"]').click();
  await wait(()=>jarvisStudio.state.flow?.name===made.name&&q('[data-node="qa-lead"]'),'Test canvas did not load');
  check(q('#flowCenterSelected')&&q('#flowDeselect'),'Flow selection controls missing');
  const card=q('[data-node="qa-lead"]');card.focus();card.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  check(jarvisStudio.state.selected==='qa-lead','Keyboard could not select a flow card');
  q('#flowCenterSelected').click();
  const state=jarvisStudio.state, selected=state.flow.canvas.nodes.find(n=>n.id==='qa-lead'), vp=q('#flowViewport');
  check(Math.abs((selected.x+selected.width/2)*state.view.z+state.view.x-vp.clientWidth/2)<3,'Center selection did not center the chosen card');
  q('#flowDeselect').click();check(!state.selected&&!state.selectedEdge,'Clear selection did not clear the inspector');
  checks.push('flow cards support keyboard selection, center selection and clear selection');

  q('[data-node="qa-lead"]').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  vp.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  check(state.flow.canvas.nodes.find(n=>n.id==='qa-lead').x===5,'Flow movement stopped working');
  q('#flowSave').click();await wait(()=>q('#flowSave').disabled&&!state.flowSaving,'Flow save did not finish');
  const saved=await api('/api/studio/flow?name='+encodeURIComponent(made.name));
  check(saved.canvas.nodes.find(n=>n.id==='qa-lead').x===5,'Flow movement did not persist');
  check((await api('/api/studio/flows')).active===before.active,'Editing a canvas changed active routing');
  checks.push('flow movement and save preserve native geometry and active routing');
  jarvisStudio.setMode('mesh',false);
  return {ok:true,passed:checks.length,checks,persistedPosition:window.__meshExpectedPosition};
})()
