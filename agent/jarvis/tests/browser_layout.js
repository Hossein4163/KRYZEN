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
  check(q('#jumpChatBtn').tagName==='BUTTON' && q('#sideExpandTrigger').tagName==='BUTTON', 'Expand controls must support the keyboard');
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
    if (mode === 'flow') check(jarvisStudio.state.view.z >= .55, 'Flow opens too far zoomed out to read card titles');
    for(const collapsed of [false,true]) {
      chatCollapsed=sideCollapsed=collapsed;applyLayoutCollapses();await pause(100);
      const workspace=q(selectors[mode]);
      check(visible(workspace), `${mode} workspace is hidden`);
      check(document.documentElement.scrollWidth<=innerWidth+1, `${mode} overflows horizontally`);
      for(const s of ['.stage','#studio','#codews','#control']) if(s!==selectors[mode]) check(!visible(q(s)), `${mode} shows inactive workspace ${s}`);
      if(mode!=='mesh') check(!visible(q('.side')), `${mode} shows an inactive side panel`);
      if(innerWidth>760) check(inside(rect(workspace),{left:0,right:innerWidth,top:rect(q('.top')).bottom,bottom:innerHeight}), `${mode} workspace extends outside the window`);
      else check(!visible(q('.chatp')), `${mode} shows the conversation outside the chat view`);
      if(mode==='mesh') {
        const journeyHost=rect(q('#journey')),nav=rect(q('.mesh-toolbar'));
        check(journeyHost.height>=100 && journeyHost.top>=nav.bottom-2,'Mesh is clipped or overlaps its toolbar');
        check(q('.jr-cell[aria-current="step"]')?.textContent === 'Start0%', 'Mesh is missing its current stage');
        check([...document.querySelectorAll('#jrWorld :is(.jr-card-name, .jr-card-sub, .jr-stage-name, .jr-stage-pct)')].every(label => {
          const {left, width} = rect(label);
          const center = new DOMPoint().matrixTransform(label.getScreenCTM()).x;
          return width > 0 && getComputedStyle(label).textAnchor === 'middle' &&
            Math.abs(left + width / 2 - center) < 1;
        }), 'Mesh labels must be centered within their nodes');
        for (const [layer, selector] of [['tools', '.jr-m-tools'], ['skills', '.jr-m-skills'], ['flow', '.jr-bus-flow']]) {
          const toggle = q(`.mesh-layer-controls [data-layer="${layer}"]`), content = q(selector);
          toggle.click();
          check(toggle.getAttribute('aria-pressed') === 'false' && getComputedStyle(content).display === 'none', `Mesh ${layer} toggle did not hide its layer`);
          toggle.click();
          check(toggle.getAttribute('aria-pressed') === 'true' && getComputedStyle(content).display !== 'none', `Mesh ${layer} toggle did not restore its layer`);
        }
        check(q('#journey').querySelectorAll('[data-agent]').length >= cfg.agents.length - 1,'Mesh did not render the whole team');
        check(getComputedStyle(q('#meshViewport')).backgroundColor === 'rgba(0, 0, 0, 0)' &&
          !q('#journey .jr-grid'), 'Mesh canvas still paints a background');
        const outlines = [...document.querySelectorAll('#jrWorld :is(.jr-stage-box, .jr-card-bg, .jr-gate-box, .jr-loop-label-box)')];
        check(outlines.length > 0 && outlines.every(node => {
          const hit = node.parentElement.querySelector('.jr-node-hit');
          return node.localName === 'polyline' && node.points.numberOfItems === 7 &&
            getComputedStyle(node).fill === 'none' && hit?.points.numberOfItems === 6 &&
            getComputedStyle(hit).fill === 'none' && getComputedStyle(hit).pointerEvents === 'all';
        }), 'Mesh nodes need an open hexagonal outline and a transparent interior hit area');
        const agents = [...document.querySelectorAll('#jrWorld .jr-agent')];
        const badges = agents.map(agent => agent.querySelector('.jr-identity-badge'));
        const glyphs = badges.map(badge => badge?.querySelector('i'));
        check(agents.length > 0 && badges.every(badge => badge && getComputedStyle(badge).color !== '') &&
          glyphs.every(glyph => glyph && getComputedStyle(glyph, '::before').content !== 'none') &&
          new Set(glyphs.map(glyph => glyph.className)).size === agents.length,
          'Each built-in specialist needs a distinct identity badge');
        const cells = [...document.querySelectorAll('#jrWorld .jr-node-hit')];
        check(cells.every(cell => {
          const points = Array.from(cell.points);
          const lengths = points.map((point, i) => {
            const next = points[(i + 1) % points.length];
            return Math.hypot(next.x - point.x, next.y - point.y);
          });
          return Math.max(...lengths) - Math.min(...lengths) < .001;
        }), 'Honeycomb cells need six equal sides');
        const [first, second, third] = [...document.querySelectorAll('.jr-stage')].map(stage =>
          stage.transform.baseVal.getItem(0).matrix);
        check(first.f === third.f && second.f > first.f &&
          Math.abs((second.e - first.e) / Math.sqrt(3) - (second.f - first.f)) < .001,
          'Mesh stages must stagger on a hexagonal grid');
        const gate = q('.jr-gate-breaker').transform.baseVal.getItem(0).matrix;
        check(Math.abs(gate.e - (first.e + second.e) / 2) < .001 &&
          Math.abs(gate.f - (first.f + second.f) / 2) < .001, 'Mesh gate must sit between its two stages');
        const fit=q('#meshFit'), fitBox=rect(fit);
        if (fitBox.bottom <= innerHeight) {
          const hit = document.elementFromPoint(fitBox.x + fitBox.width / 2, fitBox.y + fitBox.height / 2);
          check(hit?.closest('#meshFit'), `Fit is covered by ${hit?.outerHTML.slice(0,150) || 'nothing'} at ${fitBox.x},${fitBox.y}`);
        }
        fit.click();
        await pause(100);
        check([...document.querySelectorAll('.jr-planet')].every(n=>inside(rect(n),journeyHost)),'Fit hides agents');
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
