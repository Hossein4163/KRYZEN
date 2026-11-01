/* Run after a fresh page load against browser_fixture.py at each target viewport. */
(async () => {
  if (!(await fetch('/api/fixture').then(r => r.json())).fixture) throw new Error('Fixture required');
  const q = s => document.querySelector(s), pause = ms => new Promise(r => setTimeout(r, ms));
  const check = (v, m) => { if (!v) throw new Error(`${innerWidth}×${innerHeight}: ${m}`); };
  async function wait(fn, message) { for (let i=0;i<200;i++) { if(fn()) return; await pause(25); } throw new Error(message); }
  const rect = el => el.getBoundingClientRect();
  const visible = el => !!el && rect(el).width > 0 && rect(el).height > 0;
  const inside = (a,b) => a.left>=b.left-2 && a.right<=b.right+2 && a.top>=b.top-2 && a.bottom<=b.bottom+2;
  await wait(() => cfg?.agents?.length && q('#proj').options.length, 'Startup did not populate agents and projects');
  check(q('.brand').textContent.includes('K.R.Y.Z.E.N'), 'App name is missing');
  check(q('#chatExpandTrigger').tagName==='BUTTON' && q('#sideExpandTrigger').tagName==='BUTTON', 'Expand controls must support the keyboard');
  const checks=['cold startup populated agents and projects'];
  const originalFetch=window.fetch;
  try {
    window.fetch=(url,...args)=>url==='/api/config'?Promise.resolve(new Response(JSON.stringify({error:'Configuration unavailable'}),{status:503})):originalFetch(url,...args);
    await reloadMesh();
    check(!q('#meshRetry').hidden&&q('#meshSummary').textContent.includes('unavailable'),'Configuration failure has no recovery action');
  } finally { window.fetch=originalFetch; }
  q('#meshRetry').click();await wait(()=>q('#meshRetry').hidden,'Configuration retry did not recover');
  checks.push('configuration failure reports a recoverable state and Retry restores the team');
  const selectors={mesh:'.stage',flow:'#studio',plan:'#studio',code:'#codews',control:'#control'};
  for (const mode of Object.keys(selectors)) {
    jarvisStudio.setMode(mode,false);
    if(mode==='flow') await wait(()=>q('#flowViewport')&&jarvisStudio.state.flow,'Flow failed to open');
    if(mode==='plan') await wait(()=>q('.plan-layout'),'Plan failed to open');
    await pause(200);
    for(const collapsed of [false,true]) {
      chatCollapsed=sideCollapsed=collapsed;applyLayoutCollapses();await pause(100);
      const workspace=q(selectors[mode]);
      check(visible(workspace), `${mode} workspace is hidden`);
      check(document.documentElement.scrollWidth<=innerWidth+1, `${mode} overflows horizontally`);
      for(const s of ['.stage','#studio','#codews','#control']) if(s!==selectors[mode]) check(!visible(q(s)), `${mode} shows inactive workspace ${s}`);
      if(mode!=='mesh') check(!visible(q('.side')), `${mode} shows an inactive side panel`);
      if(innerWidth>760) check(inside(rect(workspace),{left:0,right:innerWidth,top:rect(q('.top')).bottom,bottom:innerHeight}), `${mode} workspace extends outside the window`);
      else check(rect(workspace).top<rect(q('.chatp')).top, `${mode} is buried below the conversation`);
      if(mode==='mesh') {
        const graph=rect(q('#graph')),nav=rect(q('.mesh-navigation'));
        check(graph.height>=100 && graph.bottom<=nav.top+2,'Mesh is clipped or overlaps navigation');
        check(q('#graph').querySelectorAll('.agent-node').length===cfg.agents.length,'Mesh did not render the whole team');
        check([...document.querySelectorAll('.agent-node .body')].every(n=>inside(rect(n),graph)),'Initial mesh fit hides agents');
        check(!visible(q('#pAgy')),'Inactive Agy log pane is visible');
      }
      if(mode==='flow') {
        q('#flowFit').click();await pause(50);
        const viewport=rect(q('#flowViewport'));
        check([...document.querySelectorAll('.flow-node')].every(n=>inside(rect(n),viewport)), 'Fit leaves canvas cards outside the viewport');
      }
    }
    checks.push(`${mode}: workspace, collapse states and viewport bounds`);
  }
  chatCollapsed=sideCollapsed=false;applyLayoutCollapses();jarvisStudio.setMode('mesh',false);
  return {ok:true,viewport:[innerWidth,innerHeight],passed:checks.length,checks};
})()
