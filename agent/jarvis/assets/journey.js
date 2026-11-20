/* Agent mesh, stage gates, and live execution routes. */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const STAGES = [
    {id: 'start', label: 'Start', pct: 0, sun: true},
    {id: 'discover', label: 'Discover', pct: 15, match: /research|reference|\bproduct\b|discover/i},
    {id: 'plan', label: 'Plan', pct: 30, match: /architect|planner|plan\b/i},
    {id: 'design', label: 'Design', pct: 45, match: /design|brand|ux/i},
    {id: 'build', label: 'Build', pct: 60, match: /build|engineer|frontend|backend|develop/i},
    {id: 'verify', label: 'Verify', pct: 75, match: /\bqa\b|test|review|security|audit/i},
    {id: 'launch', label: 'Launch', pct: 90, match: /devops|production|deploy|release|ops\b/i},
    {id: 'grow', label: 'Grow', pct: 100, match: /seo|market|content|growth|sales|support/i},
  ];
  
  const CELL_RADIUS = 58, CELL_PITCH = 72, CELL_GAP = 8;
  const COLUMN_STEP = 1.5 * CELL_PITCH, ROW_STEP = Math.sqrt(3) * CELL_PITCH;
  const MARGIN = 76, STAGE_Y = 122, FEEDBACK_Y = 42, GATE_RADIUS = 13;
  const AGENT_BAR_WIDTH = 64, AGENT_BAR_Y = 34;
  const ROLE_ICONS = {
    orchestrator: 'network', product: 'box', architect: 'blocks', design: 'palette',
    research: 'search', reference: 'copy', planner: 'list-todo', build: 'code',
    qa: 'activity', devops: 'server', production: 'upload', seo: 'waypoints',
    marketing: 'sparkles', content: 'pencil'
  };
  const labelMetrics = document.createElement('canvas').getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');

  let host, svg, world, liveLayer, hoverLayer, ruler, fill, info, zoomLabel, minimapSvg, drawerEl;
  let agents = [], nodes = {}, stages = [], onOpen = () => {}, width = 0, height = 0;
  const view = {x: 0, y: 0, z: 1, auto: true};
  const live = new Map(), done = new Set(), calls = {}, gates = {}, steps = {};
  let agentColors = {};
  let drag = null, hovering = null, activeViewMode = 'macro', gateProject = '';
  const pendingGates = new Set();

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const mk = (tag, attrs = {}, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.append(n);
    return n;
  };
  const short = a => (typeof a === 'string' ? a : (a.orchestrator ? 'Orchestrator' : a.name.replace(/ Agent$/, '')));

  function hexagon(radius) {
    const half = radius / 2, apothem = half * Math.sqrt(3);
    return [[-half, -apothem], [half, -apothem], [radius, 0], [half, apothem], [-half, apothem], [-radius, 0]];
  }

  function fitCellText(text, font) {
    labelMetrics.font = `${font} ${getComputedStyle(svg).getPropertyValue('--sans').trim()}`;
    if (labelMetrics.measureText(text).width <= 90) return text;
    let prefix = '';
    for (const character of text) {
      if (labelMetrics.measureText(prefix + character + '…').width > 90) break;
      prefix += character;
    }
    return prefix + '…';
  }

  function openCorner(points, gap) {
    const [topLeft, corner, right, bottomRight, bottomLeft, left] = points;
    const awayFromCorner = ([x, y]) => {
      const dx = x - corner[0], dy = y - corner[1];
      const fraction = gap / Math.hypot(dx, dy);
      return [corner[0] + dx * fraction, corner[1] + dy * fraction];
    };
    return [awayFromCorner(right), right, bottomRight, bottomLeft, left, topLeft, awayFromCorner(topLeft)].join(' ');
  }

  function outline(parent, mask, className, radius, gap, x, y) {
    const vertices = hexagon(radius);
    const points = vertices.join(' ');
    mk('polygon', {class: 'jr-node-hit', points, 'aria-hidden': 'true'}, parent);
    mk('polyline', {class: className, points: openCorner(vertices, gap)}, parent);
    // Cut wires out of the node interior so the outline needs no background fill.
    mk('polygon', {points, fill: 'black', transform: `translate(${x} ${y})`}, mask);
  }

  function setAgentColor(element, agent) {
    const color = Object.hasOwn(agentColors, agent.color) ? agentColors[agent.color] : '';
    if (color) element.style.setProperty('--jr-agent-color', color);
    else element.style.removeProperty('--jr-agent-color');
  }

  function identityBadge(agent, y = 0) {
    const name = short(agent).trim();
    const key = name.toLowerCase();
    const icon = Object.hasOwn(ROLE_ICONS, key) ? ROLE_ICONS[key] : '';
    const words = name.split(/[\s-]+/).filter(Boolean);
    const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] || '?').slice(0, 2);
    return `<svg class="jr-identity-badge" x="-14" y="${y}" width="28" height="28" viewBox="-14 -14 28 28" aria-hidden="true">
      <polyline points="${openCorner(hexagon(13), 2.5)}"/>
      <foreignObject x="-10" y="-10" width="20" height="20">
        <span class="jr-identity-glyph">${icon ? `<i class="icon-${icon}"></i>` : esc(letters.toUpperCase())}</span>
      </foreignObject>
    </svg>`;
  }

  /* ---------- stage assignment ---------- */
  function stageIndex(agent, i, n) {
    if (agent.orchestrator) return 0;
    const configured = STAGES.findIndex(stage => stage.id === agent.stage);
    if (configured > 0) return configured;
    const text = agent.name;
    const hit = STAGES.findIndex(s => s.match && s.match.test(text));
    return hit > 0 ? hit : Math.min(STAGES.length - 1, 1 + Math.floor(i / Math.max(1, n) * (STAGES.length - 1)));
  }

  function routePath(points) {
    return 'M ' + points.map(({x, y}) => `${x} ${y}`).join(' L ');
  }

  function routeFor(node) {
    const points = !node || node.main ? stages : [...stages.slice(0, node.stage.i + 1), node];
    return {d: routePath(points), rev: routePath([...points].reverse())};
  }

  /* ---------- render main mesh ---------- */
  function render(list, opts = {}) {
    agents = list || [];
    onOpen = opts.open || onOpen;
    agentColors = opts.colors || agentColors;
    world.textContent = '';
    nodes = {};
    stages = STAGES.map((s, i) => ({
      ...s, i, x: MARGIN + i * COLUMN_STEP, y: STAGE_Y + (i % 2) * ROW_STEP / 2, agents: []
    }));

    const others = agents.filter(a => !a.orchestrator);
    const orch = agents.find(a => a.orchestrator) || agents[0];
    if (orch) orch.orchestrator = true;

    agents.forEach(a => {
      if (a !== orch) stages[stageIndex(a, others.indexOf(a), others.length)].agents.push(a);
    });

    width = stages.at(-1).x + MARGIN;
    height = Math.max(...stages.map(stage => stage.y + stage.agents.length * ROW_STEP)) + MARGIN;

    const mask = mk('mask', {
      id: 'jr-wire-mask', maskUnits: 'userSpaceOnUse', x: 0, y: 0, width, height
    }, mk('defs', {}, world));
    mk('rect', {width, height, fill: 'white'}, mask);
    const wireMask = {mask: 'url(#jr-wire-mask)'};
    const links = mk('g', {class: 'jr-links', ...wireMask}, world);
    const annotations = mk('g', {}, world);

    const mainBusD = routePath(stages);
    mk('path', {class: 'jr-main-bus', d: mainBusD}, links);
    mk('path', {class: 'jr-bus-flow', d: mainBusD}, links);

    // Gates sit in the gap between neighboring stage cells.
    for (let i = 0; i < stages.length - 1; i++) {
      const s1 = stages[i], s2 = stages[i + 1];
      const gx = (s1.x + s2.x) / 2, gy = (s1.y + s2.y) / 2;
      const gateG = mk('g', {
        class: 'jr-gate-breaker' + (gates[s1.id] ? ' locked' : ''),
        transform: `translate(${gx} ${gy})`,
        'data-gate': s1.id,
        role: 'button',
        tabindex: gateProject ? 0 : -1,
        'aria-disabled': String(!gateProject),
        'aria-pressed': String(Boolean(gates[s1.id])),
        'aria-label': 'Hold execution after ' + s1.label
      }, annotations);
      outline(gateG, mask, 'jr-gate-box', GATE_RADIUS, 2.5, gx, gy);
      const lab = mk('text', {class: 'jr-gate-label'}, gateG);
      lab.textContent = gates[s1.id] ? 'HOLD' : 'GATE';
      const toggle = event => {
        event.preventDefault();
        event.stopPropagation();
        toggleGate(s1.id);
      };
      gateG.onclick = toggle;
      gateG.onkeydown = event => {
        if (event.key === 'Enter' || event.key === ' ') toggle(event);
      };
    }

    // Regression Loop Track linking QA / Verify (Stage 75) to Build (Stage 60)
    const verifyStage = stages.find(s => s.id === 'verify') || stages[5];
    const buildStage = stages.find(s => s.id === 'build') || stages[4];
    if (verifyStage && buildStage) {
      const loopPath = routePath([
        verifyStage, {x: verifyStage.x, y: FEEDBACK_Y + 14}, {x: verifyStage.x - 14, y: FEEDBACK_Y},
        {x: buildStage.x + 14, y: FEEDBACK_Y}, {x: buildStage.x, y: FEEDBACK_Y + 14}, buildStage
      ]);
      const loopG = mk('g', {class: 'jr-loop-track', id: 'jrLoopTrack'}, links);
      mk('path', {d: loopPath, class: 'jr-loop-wire'}, loopG);
      const badgeX = (verifyStage.x + buildStage.x) / 2;
      const badge = mk('g', {transform: `translate(${badgeX} ${FEEDBACK_Y})`}, annotations);
      outline(badge, mask, 'jr-loop-label-box', 31, 4, badgeX, FEEDBACK_Y);
      const loopTxt = mk('text', {class: 'jr-loop-label'}, badge);
      loopTxt.textContent = 'Feedback';
      nodes._loopTrack = {el: loopG, txt: loopTxt, path: loopPath};
    }

    liveLayer = mk('g', {class: 'jr-live', ...wireMask}, world);
    hoverLayer = mk('g', {class: 'jr-hover', ...wireMask}, world);

    const planets = mk('g', {class: 'jr-planets'}, world);

    stages.forEach(stage => {
      let previous = stage;
      drawStage(planets, stage, orch, mask);
      stage.agents.forEach((agent, row) => {
        const node = nodes[agent.name] = {agent, stage, x: stage.x, y: stage.y + (row + 1) * ROW_STEP};
        mk('path', {class: 'jr-sub-link jr-wire', d: routePath([previous, node]), 'data-agent': agent.name}, links);
        drawAgent(planets, node, mask);
        previous = node;
      });
    });

    if (orch) {
      nodes[orch.name] = {agent: orch, stage: stages[0], x: stages[0].x, y: stages[0].y, main: true, el: stages[0].el};
    }

    renderRuler();
    renderMinimap();

    for (const name of live.keys()) {
      const n = nodes[name];
      if (n) {
        live.get(name)?.remove();
        live.set(name, drawRoutes(liveLayer, [routeFor(n)], 'live'));
        n.el?.classList.add('active');
      }
    }
    done.forEach(name => nodes[name]?.el?.classList.add('done'));
    updateFill();
    showInfo(null);
    fit();
  }

  function drawStage(parent, s, orch, mask) {
    const g = mk('g', {
      class: 'jr-planet jr-stage' + (s.sun ? ' jr-sun' : ''),
      transform: `translate(${s.x} ${s.y})`,
      tabindex: 0,
      role: s.sun ? 'button' : 'img',
      'aria-label': s.sun && orch ? `${short(orch)}, start of the journey` : `${s.label}, ${s.pct} percent, ${s.agents.length} agents`,
      'data-stage': s.id
    }, parent);

    outline(g, mask, 'jr-stage-box', CELL_RADIUS, CELL_GAP, s.x, s.y);
    const label = mk('text', {class: 'jr-stage-name', x: 0, y: -8, 'text-anchor': 'middle'}, g);
    label.textContent = s.label;
    const percent = mk('text', {class: 'jr-stage-pct', x: 0, y: 8, 'text-anchor': 'middle'}, g);
    percent.textContent = s.pct + '%';

    s.el = g;
    wire(g, () => ({stage: s, agent: s.sun ? orch : null}), s.sun && orch ? () => openAgentInspector(orch, nodes[orch.name]) : null);
  }

  function drawAgent(parent, n, mask) {
    const a = n.agent;
    const g = mk('g', {
      class: 'jr-planet jr-agent',
      transform: `translate(${n.x} ${n.y})`,
      tabindex: 0,
      role: 'button',
      'aria-label': [short(a), a.role, 'Open inspector'].filter(Boolean).join('. '),
      'data-agent': a.name
    }, parent);

    setAgentColor(g, a);
    outline(g, mask, 'jr-card-bg', CELL_RADIUS, CELL_GAP, n.x, n.y);
    g.insertAdjacentHTML('beforeend', identityBadge(a, -46));
    mk('polyline', {class: 'jr-card-led', points: openCorner(hexagon(4), 1), transform: 'translate(32 -28)'}, g);

    const title = mk('text', {class: 'jr-card-name', x: 0, y: -3}, g);
    title.textContent = fitCellText(short(a), '600 14px');

    const tools = (a.tools || []).filter(tool => tool.kind !== 'agent').length;
    const skills = (a.skills || []).length;
    const metadata = mk('text', {class: 'jr-card-sub', x: 0, y: 13}, g);
    mk('tspan', {class: 'jr-m-tools'}, metadata).textContent = `${tools} tools`;
    mk('tspan', {class: 'jr-m-separator'}, metadata).textContent = ' · ';
    n.metricEl = mk('tspan', {class: 'jr-m-skills'}, metadata);
    n.metricEl.textContent = `${skills} skills`;
    n.tickerEl = mk('text', {class: 'jr-card-ticker', x: 0, y: 22}, g);

    n.barEl = mk('rect', {class: 'jr-bar-fill', x: -AGENT_BAR_WIDTH / 2, y: AGENT_BAR_Y, width: 0, height: 2, rx: 1}, g);

    n.el = g;
    wire(g, () => ({stage: n.stage, agent: a, node: n}), () => openAgentInspector(a, n));
  }

  function wire(g, target, open) {
    g.addEventListener('pointerenter', () => hover(target()));
    g.addEventListener('pointerleave', () => hover(null));
    g.addEventListener('focus', () => hover(target()));
    g.addEventListener('blur', () => hover(null));
    if (!open) return;
    g.classList.add('jr-click');
    g.addEventListener('click', () => { if (!drag?.moved) open(); });
    g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
  }

  /* ---------- Real-Time SSE Telemetry Packets ---------- */
  function drawRoutes(parent, routes, cls) {
    const g = mk('g', {class: 'jr-routes ' + cls}, parent);
    for (const r of routes) {
      if (!r.d) continue;
      const reqP = mk('path', {class: 'jr-req', d: r.d}, g);
      const backG = mk('g', {}, g);
      mk('path', {class: 'jr-res', d: r.rev}, backG);
      if (reduced.matches) continue;
      const dur = 1.2;
      dot(g, r.d, 'jr-dot-req', dur, '0s');
      dot(backG, r.rev, 'jr-dot-res', dur, `${dur / 2}s`);
    }
    return g;
  }

  function dot(parent, d, cls, dur, begin, once) {
    const c = mk('polygon', {class: cls, points: hexagon(4).join(' ')}, parent);
    const anim = mk('animateMotion', {path: d, dur: dur + 's', begin, repeatCount: once ? 1 : 'indefinite', fill: 'remove'}, c);
    return {c, anim};
  }

  function packet(parent, d, cls, labelText) {
    const c = mk('g', {class: 'jr-packet'}, parent);
    mk('polygon', {class: cls, points: hexagon(5).join(' '), stroke: '#FFF', 'stroke-width': 1.5}, c);
    if (labelText) {
      const gLab = mk('g', {transform: 'translate(10 -6)'}, c);
      const labelWidth = labelText.length * 7 + 10;
      mk('rect', {x: 0, y: -9, width: labelWidth, height: 16, class: 'jr-packet-label'}, gLab);
      const txt = mk('text', {x: labelWidth / 2, y: -1, class: 'jr-packet-text'}, gLab);
      txt.textContent = labelText;
    }
    const anim = mk('animateMotion', {path: d, dur: '1.2s', begin: '0s', repeatCount: 1, fill: 'remove'}, c);
    anim.addEventListener('endEvent', () => c.remove());
    setTimeout(() => c.remove(), 1500);
    try { anim.beginElement(); } catch (_) { c.remove(); }
    return c;
  }

  function hover(t) {
    if (drag?.moved) return;
    hovering = t;
    hoverLayer.textContent = '';
    svg.classList.toggle('jr-focus', !!t);
    host.querySelectorAll('.jr-rel').forEach(e => e.classList.remove('jr-rel'));
    if (!t) return showInfo(null);
    const rel = [t.stage.el];
    let routes = [];
    if (t.node) {
      routes = [routeFor(t.node)];
      rel.push(t.node.el, stages[0].el);
    } else if (t.agent) {
      routes = [routeFor(null)];
      rel.push(...stages.map(s => s.el));
    } else {
      routes = t.stage.agents.map(a => routeFor(nodes[a.name]));
      rel.push(...t.stage.agents.map(a => nodes[a.name].el));
    }
    drawRoutes(hoverLayer, routes, 'hover');
    rel.forEach(e => e?.classList.add('jr-rel'));
    showInfo(t);
  }

  function showInfo(t) {
    if (!t) {
      info.className = 'jr-info jr-hint';
      info.innerHTML = '<span><i class="jr-key jr-key-req"></i>Request</span><span><i class="jr-key jr-key-res"></i>Response</span>';
      return;
    }
    const orch = agents.find(a => a.orchestrator);
    const from = orch ? short(orch) : 'Orchestrator';
    let rows = '', title = '', sub = '';
    if (t.agent && !t.agent.orchestrator || (t.agent && t.node)) {
      const a = t.agent;
      title = short(a);
      sub = `${t.stage.label} · ${t.stage.pct}%`;
      rows = `${a.role ? `<tr><th>Role</th><td>${esc(a.role)}</td></tr>` : ''}
        <tr><th class="jr-th-req">Request</th><td>${esc(from)} → ${esc(short(a))}</td></tr>
        <tr><th class="jr-th-res">Response</th><td>${esc(short(a))} → ${esc(from)}</td></tr>
        <tr><th>Stage Gate</th><td>${gates[t.stage.id] ? 'LOCKED (Pulsing hold)' : 'OPEN'}</td></tr>
        <tr><th>Tools</th><td>${(a.tools || []).map(x => esc(x.title || x.name)).join(', ') || '—'}</td></tr>`;
    } else {
      title = t.stage.label;
      sub = `${t.stage.pct}% of journey`;
      rows = `<tr><th class="jr-th-req">Gate</th><td>${gates[t.stage.id] ? 'LOCKED' : 'OPEN'}</td></tr>
        <tr><th>Agents</th><td>${t.stage.agents.map(short).join(', ') || 'None'}</td></tr>`;
    }
    info.className = 'jr-info';
    info.innerHTML = `<div class="jr-info-head"><b>${esc(title)}</b><span>${esc(sub)}</span></div><table>${rows}</table>`;
  }

  /* ---------- Stage Gate Breakers ---------- */
  function setGates(project, values) {
    gateProject = project;
    for (const stage of STAGES) gates[stage.id] = Boolean(values?.[stage.id]);
    for (const node of host?.querySelectorAll('[data-gate]') || []) {
      const locked = gates[node.dataset.gate];
      node.classList.toggle('locked', locked);
      node.setAttribute('aria-pressed', String(locked));
      node.setAttribute('aria-disabled', String(!gateProject));
      node.setAttribute('tabindex', gateProject ? '0' : '-1');
      const label = node.querySelector('text');
      label.textContent = locked ? 'HOLD' : 'GATE';
    }
  }

  async function toggleGate(stage) {
    if (!gateProject || pendingGates.has(stage)) return;
    const project = gateProject;
    pendingGates.add(stage);
    try {
      const result = await window.setStageGate(project, stage, !gates[stage]);
      if (project !== gateProject) return;
      if (!result.ok) throw new Error(result.error || 'Could not update the stage gate');
      setGates(project, {...gates, [stage]: result.locked});
      window.toast?.(result.locked ? 'Stage held after ' + stage : 'Stage released after ' + stage, 'ok');
    } catch (error) {
      window.toast?.(error.message, 'err');
    } finally {
      pendingGates.delete(stage);
    }
  }

  /* ---------- Slide-over Agent Technical Inspector ---------- */
  function closeDrawer() {
    if (!drawerEl) return;
    drawerEl.style.display = 'none';
    drawerEl.style.pointerEvents = 'none';
    drawerEl.classList.remove('open');
    drawerEl.classList.add('hidden');
    drawerEl.hidden = true;
    drawerEl.dataset.agent = '';
  }

  function openAgentInspector(agent, node, initialTab = 'config') {
    if (!drawerEl) return onOpen(agent.name);
    // If clicking the same open agent with same tab, toggle closed
    if (drawerEl.style.display !== 'none' && !drawerEl.hidden && drawerEl.dataset.agent === agent.name && !initialTab) {
      closeDrawer();
      return;
    }

    drawerEl.dataset.agent = agent.name;
    drawerEl.hidden = false;
    drawerEl.style.display = 'flex';
    drawerEl.style.pointerEvents = 'auto';
    drawerEl.classList.remove('hidden');
    drawerEl.classList.add('open');

    const a = agent;
    setAgentColor(drawerEl, a);
    const tools = (a.tools || []).map(t => t.title || t.name);
    const skills = a.skills || [];
    const parts = [
      {name: 'Name', detail: short(a), x: -43, y: -24},
      {name: 'Status', detail: 'The outline changes while the agent runs or finishes.', x: 44, y: -36},
      {name: 'Tools and skills', detail: `${tools.length} tools · ${skills.length} skills`, x: -46, y: 21},
      {name: 'Step progress', detail: 'The line grows as the agent advances through its steps.', x: -38, y: 43},
      {name: 'Route', detail: 'The connector shows requests and responses between the stage and the agent.', x: 16, y: -59},
    ];

    let currentTab = initialTab || 'config';

    function renderDrawerContent() {
      drawerEl.innerHTML = `
        <button type="button" class="jr-drawer-tab" id="jrDrawerTab" title="Collapse inspector panel" aria-label="Collapse inspector">›</button>
        <div class="jr-drawer-head">
          <div class="jr-drawer-identity">
            ${identityBadge(a)}
            <div class="jr-drawer-title-wrap">
              <h3>${esc(short(a))}</h3>
              ${a.role ? `<p class="jr-drawer-role">${esc(a.role)}</p>` : ''}
            </div>
          </div>
          <div class="jr-drawer-actions">
            <button type="button" class="jr-drawer-close" id="jrDrawerClose" title="Hide inspector (Esc)" aria-label="Close inspector">
              <span class="jr-drawer-close-icon">✕</span>
              <span class="jr-drawer-close-text">CLOSE</span>
              <kbd>ESC</kbd>
            </button>
          </div>
        </div>

        <div class="jr-drawer-nav-tabs">
          <button type="button" class="jr-tab-btn ${currentTab === 'config' ? 'active' : ''}" id="jrTabConfig">
            <span class="jr-tab-indicator"></span> CONFIG & RUNTIME
          </button>
          <button type="button" class="jr-tab-btn ${currentTab === 'anatomy' ? 'active' : ''}" id="jrTabAnatomy">
            <span class="jr-tab-indicator"></span> CELL ANATOMY
          </button>
        </div>

        <div class="jr-drawer-body">
          ${currentTab === 'config' ? `
            <div class="jr-drawer-field">
              <label>MODEL TIER & HOT-SWAP</label>
              <select id="jrModelSwap">
                <option value="gemini-3.8-flash">gemini-3.8-flash (Reasoning Tier)</option>
                <option value="gemini-3-flash">gemini-3-flash (Fast Tier)</option>
                <option value="claude-3.5-sonnet">claude-3.5-sonnet (High-Capability)</option>
                <option value="ollama/qwen2.5-coder">ollama/qwen2.5-coder (Local Offline)</option>
              </select>
            </div>
            <div class="jr-drawer-field">
              <label>ASSIGNED ROLE SYSTEM INSTRUCTIONS</label>
              <textarea rows="5" readonly style="font-size:10px;resize:vertical">${esc(a.system || 'Standard execution role.')}</textarea>
            </div>
            <div class="jr-drawer-field">
              <label>SANDBOXED TOOLS (${tools.length})</label>
              <div style="display:flex;gap:4px;flex-wrap:wrap">
                ${tools.map(t => `<span class="jr-field-chip">${esc(t)}</span>`).join('') || '<span style="color:#666">No direct tools</span>'}
              </div>
            </div>
            <div class="jr-drawer-field">
              <label>LOADED SKILLS (${skills.length})</label>
              <div style="display:flex;gap:4px;flex-wrap:wrap">
                ${skills.map(s => `<span class="jr-field-chip">${esc(s)}</span>`).join('') || '<span style="color:#666">No custom skills</span>'}
              </div>
            </div>
            <div class="jr-drawer-links">
              <button type="button" class="btn" id="jrViewAnatomyBtn">View node anatomy</button>
              <button type="button" class="btn" id="jrEditAgentBtn">Open editor</button>
            </div>
          ` : `
            <svg viewBox="-76 -72 152 144" class="jr-anatomy" id="jrAnatomySvg" aria-label="Anatomy of an outlined agent node">
              <polyline points="${openCorner(hexagon(CELL_RADIUS), CELL_GAP)}" class="jr-card-bg"/>
              <path d="M 0 -65 V ${-CELL_RADIUS * Math.sqrt(3) / 2} M 0 ${CELL_RADIUS * Math.sqrt(3) / 2} V 65" class="jr-wire"/>
              ${identityBadge(a, -46)}
              <text x="0" y="-3" class="jr-card-name">${esc(fitCellText(short(a), '600 14px'))}</text>
              <text x="0" y="13" class="jr-card-sub">${(a.tools || []).filter(tool => tool.kind !== 'agent').length} tools · ${skills.length} skills</text>
              <polyline points="${openCorner(hexagon(4), 1)}" transform="translate(32 -28)" class="jr-card-led"/>
              <path d="M ${-AGENT_BAR_WIDTH / 2} ${AGENT_BAR_Y} H 10" class="jr-anatomy-progress"/>
              ${parts.map((part, i) => `<g class="jr-anat-pin" role="button" tabindex="0" data-part="${i + 1}"
                aria-label="${part.name}" transform="translate(${part.x} ${part.y})">
                <polygon class="jr-node-hit" points="${hexagon(8).join(' ')}"/>
                <polyline points="${openCorner(hexagon(8), 1.5)}"/>
                <text>${i + 1}</text>
              </g>`).join('')}
            </svg>
            <ol class="jr-anatomy-parts">
              ${parts.map((part, i) => `<li id="jrAnatPart${i + 1}"><strong>${part.name}</strong><span>${esc(part.detail)}</span></li>`).join('')}
            </ol>
          `}
        </div>
      `;

      // Attach button and interactive events
      const closeBtn = drawerEl.querySelector('#jrDrawerClose');
      if (closeBtn) {
        closeBtn.onclick = e => { if (e) { e.preventDefault(); e.stopPropagation(); } closeDrawer(); };
        closeBtn.onpointerdown = e => { if (e) { e.preventDefault(); e.stopPropagation(); } closeDrawer(); };
      }
      const tabBtn = drawerEl.querySelector('#jrDrawerTab');
      if (tabBtn) {
        tabBtn.onclick = e => { if (e) { e.preventDefault(); e.stopPropagation(); } closeDrawer(); };
        tabBtn.onpointerdown = e => { if (e) { e.preventDefault(); e.stopPropagation(); } closeDrawer(); };
      }

      const cfgTab = drawerEl.querySelector('#jrTabConfig');
      if (cfgTab) {
        cfgTab.onclick = () => { currentTab = 'config'; renderDrawerContent(); };
      }
      const anatTab = drawerEl.querySelector('#jrTabAnatomy');
      if (anatTab) {
        anatTab.onclick = () => { currentTab = 'anatomy'; renderDrawerContent(); };
      }

      const viewAnatBtn = drawerEl.querySelector('#jrViewAnatomyBtn');
      if (viewAnatBtn) {
        viewAnatBtn.onclick = () => { currentTab = 'anatomy'; renderDrawerContent(); };
      }

      const editBtn = drawerEl.querySelector('#jrEditAgentBtn');
      if (editBtn) {
        editBtn.onclick = () => { closeDrawer(); onOpen(a.name); };
      }
      const swapSelect = drawerEl.querySelector('#jrModelSwap');
      if (swapSelect) {
        swapSelect.onchange = e => {
          if (window.toast) window.toast(`✓ Agent ${short(a)} model set to ${e.target.value}`, 'ok');
        };
      }

      // Interactive pins in SVG schematic
      drawerEl.querySelectorAll('.jr-anat-pin').forEach(pin => {
        const reveal = () => {
          const partNum = pin.dataset.part;
          const targetCard = drawerEl.querySelector(`#jrAnatPart${partNum}`);
          if (targetCard) {
            targetCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            targetCard.classList.add('highlight');
            setTimeout(() => targetCard.classList.remove('highlight'), 1500);
          }
        };
        pin.addEventListener('click', reveal);
        pin.addEventListener('keydown', event => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          reveal();
        });
      });
    }

    renderDrawerContent();
  }

  /* ---------- Wireframe Minimap ---------- */
  function renderMinimap() {
    if (!minimapSvg || !width) return;
    minimapSvg.innerHTML = '';
    minimapSvg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    const points = openCorner(hexagon(CELL_RADIUS), CELL_GAP);
    for (const stage of stages) {
      for (const cell of [stage, ...stage.agents.map(agent => nodes[agent.name])]) {
        const marker = mk('polyline', {
          points, transform: `translate(${cell.x} ${cell.y})`,
          class: cell.sun ? 'jr-mini-start' : 'jr-mini-node'
        }, minimapSvg);
        if (cell.agent) setAgentColor(marker, cell.agent);
      }
    }

    const left = Math.max(0, -view.x / view.z), top = Math.max(0, -view.y / view.z);
    const right = Math.min(width, (svg.clientWidth - view.x) / view.z);
    const bottom = Math.min(height, (svg.clientHeight - view.y) / view.z);
    mk('rect', {
      class: 'jr-minimap-viewport', x: left, y: top,
      width: Math.max(0, right - left), height: Math.max(0, bottom - top)
    }, minimapSvg);
  }

  /* ---------- 0 to 100 ruler ---------- */
  function renderRuler() {
    ruler.innerHTML = `<div class="jr-fill" id="jrFill"></div>` +
      stages.map(s => `<button type="button" class="jr-cell" data-i="${s.i}" title="Go to ${esc(s.label)}"><b>${esc(s.label)}</b><span>${s.pct}%</span></button>`).join('');
    fill = ruler.querySelector('#jrFill');
    ruler.querySelectorAll('.jr-cell').forEach(b => {
      const s = stages[+b.dataset.i];
      b.onclick = () => center(s.x, s.y);
      b.onpointerenter = () => hover({stage: s, agent: s.sun ? agents.find(a => a.orchestrator) : null});
      b.onpointerleave = () => hover(null);
    });
    updateFill();
  }

  function updateFill() {
    if (!fill) return;
    let top = -1;
    for (const name of [...live.keys(), ...done]) {
      const n = nodes[name];
      if (n && !n.main) top = Math.max(top, n.stage.i);
    }
    const running = [...live.keys()].length > 0;
    fill.style.width = top < 0 ? '0' : `${(top + 1) / stages.length * 100}%`;
    fill.classList.toggle('run', running);
    ruler.querySelectorAll('.jr-cell').forEach((b, i) => {
      b.classList.toggle('reached', i <= top);
      if (i === Math.max(0, top)) b.setAttribute('aria-current', 'step');
      else b.removeAttribute('aria-current');
    });
  }

  /* ---------- camera ---------- */
  function apply() {
    world.setAttribute('transform', `translate(${view.x} ${view.y}) scale(${view.z})`);
    if (zoomLabel) zoomLabel.textContent = Math.round(view.z * 100) + '%';
    renderMinimap();
  }

  function clampView() {
    if (!svg?.clientWidth || !svg?.clientHeight) return;
    const w = svg.clientWidth, h = svg.clientHeight;
    const cw = width * view.z, ch = height * view.z;
    if (view.auto) {
      view.x = cw <= w ? (w - cw) / 2 : Math.min(0, Math.max(w - cw, view.x));
      view.y = ch <= h ? (h - ch) / 2 : Math.min(0, Math.max(h - ch, view.y));
    } else {
      const padX = Math.min(160, Math.max(60, w * 0.2));
      const padY = Math.min(140, Math.max(60, h * 0.2));
      const minX = padX - cw;
      const maxX = w - padX;
      const minY = padY - ch;
      const maxY = h - padY;
      view.x = Math.min(maxX, Math.max(minX, view.x));
      view.y = Math.min(maxY, Math.max(minY, view.y));
    }
    apply();
  }

  function fit(whole) {
    if (!svg?.clientWidth || !width) return;
    const w = svg.clientWidth, h = svg.clientHeight;
    view.auto = !whole;
    const scale = Math.min(w / width, h / height, 1.4);
    view.z = whole ? scale : Math.max(.62, scale);
    view.x = Math.max(0, (w - width * view.z) / 2);
    view.y = Math.max(0, (h - height * view.z) / 2);
    clampView();
  }

  function zoomTo(z, px, py) {
    const w = svg.clientWidth, h = svg.clientHeight, cx = px ?? w / 2, cy = py ?? h / 2;
    z = Math.max(.3, Math.min(2.2, z));
    const wx = (cx - view.x) / view.z, wy = (cy - view.y) / view.z;
    view.z = z; view.x = cx - wx * z; view.y = cy - wy * z; view.auto = false;
    clampView();
  }

  function center(wx, wy) {
    view.x = svg.clientWidth / 2 - wx * view.z;
    view.y = svg.clientHeight / 2 - wy * view.z;
    view.auto = false;
    clampView();
  }

  /* ---------- live run & SSE Telemetry methods ---------- */
  function setActive(name, on) {
    const n = nodes[name];
    if (on) {
      done.delete(name);
      n?.el?.classList.remove('done');
      n?.el?.classList.add('active');
      n?.barEl?.setAttribute('width', '0');
      if (n?.tickerEl) n.tickerEl.textContent = '';
      if (!live.has(name) && n) live.set(name, drawRoutes(liveLayer, [routeFor(n)], 'live'));
    } else {
      live.get(name)?.remove();
      live.delete(name);
      n?.el?.classList.remove('active');
      n?.el?.classList.add('done');
      if (n?.tickerEl) n.tickerEl.textContent = '';
      done.add(name);
    }
    updateFill();
  }

  function burst(name, dir, labelText) {
    const n = nodes[name];
    if (!n || n.main || document.hidden || reduced.matches) return;
    const r = routeFor(n);
    const d = dir === 'out' ? r.d : r.rev;
    packet(liveLayer, d, dir === 'out' ? 'jr-dot-req' : 'jr-dot-res', labelText || (dir === 'out' ? `${short(n.agent).toUpperCase()}` : 'DONE'));
  }

  function setCalls(name, count) {
    calls[name] = count;
    const n = nodes[name];
    if (n?.metricEl) {
      n.metricEl.classList.remove('jr-m-skills');
      n.metricEl.textContent = `${count} calls`;
    }
  }

  function setStep(name, step, max) {
    steps[name] = {step, max};
    const n = nodes[name];
    if (n?.barEl && max > 0) {
      const pct = Math.max(0, Math.min(1, step / max)) * AGENT_BAR_WIDTH;
      n.barEl.setAttribute('width', String(pct));
    }
  }

  function setLiveTicker(name, text) {
    const n = nodes[name];
    if (n?.tickerEl) {
      n.tickerEl.textContent = fitCellText(text, '11px');
    }
  }

  function onRetry(attempt) {
    if (nodes._loopTrack) {
      nodes._loopTrack.el.classList.add('active');
      nodes._loopTrack.txt.textContent = `RETRY ${attempt}/3`;
      packet(liveLayer, nodes._loopTrack.path, 'jr-dot-req', `RETRY ${attempt}/3`);
    }
  }

  function resetRun() {
    done.forEach(name => {
      const n = nodes[name];
      n?.el?.classList.remove('done');
      n?.barEl?.setAttribute('width', '0');
      if (n?.callsEl) {
        const tools = (n.agent.tools || []).filter(tool => tool.kind !== 'agent').length;
        n.callsEl.textContent = `${tools} tools · ${(n.agent.skills || []).length} skills`;
      }
    });
    done.clear();
    if (nodes._loopTrack) {
      nodes._loopTrack.el.classList.remove('active');
      nodes._loopTrack.txt.textContent = 'Feedback';
    }
    updateFill();
  }

  /* ---------- initialization ---------- */
  function init(root) {
    host = root;
    host.innerHTML = `
      <div class="jr-canvas">
        <svg class="jr-svg" id="jrSvg" aria-label="Agent mesh"><g id="jrWorld"></g></svg>
        <div class="jr-info" id="jrInfo" aria-live="polite"></div>
        <div class="jr-minimap-wrap" id="jrMinimapWrap">
          <div class="jr-minimap-modes">
            <button type="button" class="btn on" data-mode="macro" aria-pressed="true">Overview</button>
            <button type="button" class="btn" data-mode="telemetry" aria-pressed="false">Telemetry</button>
            <button type="button" class="btn" data-mode="diff" aria-pressed="false">Handoff</button>
          </div>
          <svg class="jr-minimap" id="jrMinimap"></svg>
        </div>
        <div class="jr-agent-drawer hidden" id="jrAgentDrawer" style="display:none" hidden></div>
      </div>
    `;

    ruler = document.getElementById('jrRuler');
    svg = host.querySelector('#jrSvg');
    world = host.querySelector('#jrWorld');
    info = host.querySelector('#jrInfo');
    minimapSvg = host.querySelector('#jrMinimap');
    drawerEl = host.querySelector('#jrAgentDrawer');

    if (drawerEl) {
      drawerEl.addEventListener('click', e => {
        if (e.target.closest('#jrDrawerClose') || e.target.closest('#jrDrawerTab') || e.target.closest('.jr-drawer-close')) {
          e.preventDefault();
          e.stopPropagation();
          closeDrawer();
        }
      });
    }

    zoomLabel = document.getElementById('meshZoomLabel');
    document.getElementById('meshZoomIn').onclick = () => zoomTo(view.z * 1.2);
    document.getElementById('meshZoomOut').onclick = () => zoomTo(view.z / 1.2);
    if (zoomLabel) zoomLabel.onclick = () => fit();
    document.getElementById('meshFit').onclick = () => fit(true);

    const anatomyBtn = document.getElementById('meshAnatomyBtn');
    if (anatomyBtn) {
      anatomyBtn.onclick = () => {
        const orch = agents.find(a => a.orchestrator) || agents[0];
        const targetNode = nodes[orch?.name] || Object.values(nodes)[0];
        if (orch && targetNode) {
          openAgentInspector(orch, targetNode, 'anatomy');
        }
      };
    }

    // Minimap View Modes
    host.querySelectorAll('.jr-minimap-modes button').forEach(btn => {
      btn.onclick = () => {
        host.querySelectorAll('.jr-minimap-modes button').forEach(button => {
          button.classList.toggle('on', button === btn);
          button.setAttribute('aria-pressed', String(button === btn));
        });
        activeViewMode = btn.dataset.mode;
        if (activeViewMode === 'macro') fit(true);
        else if (activeViewMode === 'telemetry') zoomTo(1.3);
        else if (activeViewMode === 'diff') {
          fit(true);
          if (nodes._loopTrack) nodes._loopTrack.el.classList.add('active');
        }
      };
    });

    document.querySelectorAll('.mesh-layer-controls [data-layer]').forEach(b => b.onclick = () => {
      const on = b.getAttribute('aria-pressed') !== 'true';
      b.setAttribute('aria-pressed', String(on));
      svg.classList.toggle('no-' + b.dataset.layer, !on);
    });

    svg.addEventListener('pointerdown', e => {
      if (e.button) return;
      if (drawerEl && !drawerEl.hidden && !e.target.closest('#jrAgentDrawer') && !e.target.closest('.jr-click')) {
        closeDrawer();
      }
      drag = {x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false, id: e.pointerId};
    });
    svg.addEventListener('pointermove', e => {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 5) return;
      if (!drag.moved) { drag.moved = true; svg.classList.add('dragging'); svg.setPointerCapture(e.pointerId); }
      view.x = drag.vx + dx; view.y = drag.vy + dy; view.auto = false;
      clampView();
    });
    const end = () => { const d = drag; svg.classList.remove('dragging'); setTimeout(() => { if (drag === d) drag = null; }, 0); };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);

    host.addEventListener('wheel', e => {
      // Let the drawer body scroll vertically when pointer is inside it
      if (e.target.closest('#jrAgentDrawer')) return;

      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const r = svg.getBoundingClientRect();
        const factor = e.deltaY < 0 ? 1.08 : 0.92;
        zoomTo(view.z * factor, e.clientX - r.left, e.clientY - r.top);
        return;
      }
      view.auto = false;

      // Trackpad 2D scrolling, Shift+Wheel horizontal, or standard 1D mouse wheel
      if (e.shiftKey) {
        view.x -= (e.deltaY || e.deltaX) * 1.2;
      } else if (Math.abs(e.deltaX) > 0) {
        view.x -= e.deltaX * 1.2;
        view.y -= e.deltaY * 1.2;
      } else {
        const w = svg.clientWidth || 1, h = svg.clientHeight || 1;
        const cw = width * view.z, ch = height * view.z;
        if (cw > w && ch <= h * 1.1) {
          view.x -= e.deltaY * 1.2;
        } else {
          view.y -= e.deltaY * 1.2;
        }
      }
      clampView();
    }, {passive: false});

    // Keyboard navigation (Escape closes drawer with capture, Arrow keys scroll mesh)
    const handleEsc = e => {
      if (e.key === 'Escape' || e.keyCode === 27) {
        if (drawerEl && drawerEl.style.display !== 'none' && !drawerEl.hidden) {
          closeDrawer();
          e.preventDefault();
          e.stopPropagation();
        }
      }
    };
    window.addEventListener('keydown', handleEsc, true);
    document.addEventListener('keydown', handleEsc, true);

    window.addEventListener('keydown', e => {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;
      if (e.key === 'ArrowRight') { view.x -= 60; view.auto = false; clampView(); }
      else if (e.key === 'ArrowLeft') { view.x += 60; view.auto = false; clampView(); }
      else if (e.key === 'ArrowDown') { view.y -= 60; view.auto = false; clampView(); }
      else if (e.key === 'ArrowUp') { view.y += 60; view.auto = false; clampView(); }
    });

    // Dismiss drawer when clicking outside on document
    document.addEventListener('pointerdown', e => {
      if (!drawerEl || drawerEl.hidden || drawerEl.style.display === 'none') return;
      if (e.target.closest('#jrAgentDrawer')) return;
      if (e.target.closest('.jr-click')) return;
      closeDrawer();
    });

    // Minimap quick-jump navigation
    if (minimapSvg) {
      minimapSvg.addEventListener('pointerdown', e => {
        const matrix = minimapSvg.getScreenCTM();
        if (!matrix) return;
        const {x, y} = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse());
        center(Math.max(0, Math.min(width, x)), Math.max(0, Math.min(height, y)));
      });
    }

    new ResizeObserver(() => {
      if (!width) return;
      if (view.auto) fit();
      else clampView();
    }).observe(svg);

    // Listen to live SSE Telemetry Events
    window.addEventListener('kryzen:event', ev => {
      const d = ev.detail;
      if (!d) return;
      if (d.type === 'step' && d.agent) {
        setStep(d.agent, d.step, d.max);
      } else if (d.type === 'tool_start' && d.agent) {
        setLiveTicker(d.agent, d.tool);
        burst(d.agent, 'out', `TOOL: ${d.tool}`);
      } else if (d.type === 'retry') {
        onRetry(d.attempt || 1);
      }
    });

    showInfo(null);
  }

  window.Journey = {
    init,
    render,
    setActive,
    burst,
    setCalls,
    setStep,
    setLiveTicker,
    setGates,
    onRetry,
    resetRun,
    fit,
    closeDrawer,
    openAgentInspector,
    openAnatomy: (agentName) => {
      const a = (agentName && agents.find(x => x.name === agentName)) || agents.find(x => x.orchestrator) || agents[0];
      const n = nodes[a?.name] || Object.values(nodes)[0];
      if (a && n) openAgentInspector(a, n, 'anatomy');
    }
  };
})();
