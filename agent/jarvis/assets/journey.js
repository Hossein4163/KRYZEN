/* Agent mesh: Industrial-grade Swiss-Modernist Mission Control telemetry.
   Deterministic 90-degree orthogonal SVG Manhattan circuit-board routing,
   tactile instrument-cluster agent modules, real-time SSE telemetry packets,
   stage gate breakers, regression loop tracks, and radar minimap. */
(() => {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const STAGES = [
    {id: 'start', label: 'Start', pct: 0, pal: ['#ffd98a', '#f7a531', '#d9640f'], sun: true},
    {id: 'discover', label: 'Discover', pct: 15, match: /research|reference|\bproduct\b|discover/i, pal: ['#d9c7a3', '#a68a5f', '#6d5638']},
    {id: 'plan', label: 'Plan', pct: 30, match: /architect|planner|plan\b/i, pal: ['#a9cfe0', '#4d86a8', '#23506e']},
    {id: 'design', label: 'Design', pct: 45, match: /design|brand|ux/i, pal: ['#e8b49d', '#c0694f', '#7c3324'], ring: true},
    {id: 'build', label: 'Build', pct: 60, match: /build|engineer|frontend|backend|develop/i, pal: ['#c9d6a0', '#7d9455', '#44592f']},
    {id: 'verify', label: 'Verify', pct: 75, match: /\bqa\b|test|review|security|audit/i, pal: ['#c9c2dc', '#7f75a3', '#463f66']},
    {id: 'launch', label: 'Launch', pct: 90, match: /devops|production|deploy|release|ops\b/i, pal: ['#a8d8cf', '#3f8f83', '#1e5650']},
    {id: 'grow', label: 'Grow', pct: 100, match: /seo|market|content|growth|sales|support/i, pal: ['#efd3a8', '#c98f4e', '#7d5426'], ring: true},
  ];
  const AGENT_PALS = [['#cfe0e8', '#6f9bb0', '#35566a'], ['#e7cfc0', '#b57f62', '#6c4531'], ['#d7dcb8', '#8d9a62', '#4e5a33'], ['#dcd2e6', '#8f7fae', '#524570'], ['#e9dcb4', '#b89c55', '#6f5a28'], ['#bfe0da', '#5b9f93', '#2d5f57']];
  
  // Swiss architectural grid coordinates (flat horizontal stage bus, zero wobble)
  const COL = 220, PAD = 110, MAIN_Y = 110, ROW0 = 230, ROW = 90, R_MAIN = 36, R_SUB = 24;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');

  let host, svg, world, liveLayer, hoverLayer, ruler, fill, info, zoomLabel, minimapSvg, drawerEl;
  let agents = [], nodes = {}, stages = [], onOpen = () => {}, width = 0, height = 0;
  const view = {x: 0, y: 0, z: 1, auto: true};
  const live = new Map(), done = new Set(), calls = {}, gates = {}, steps = {};
  let drag = null, hovering = null, activeViewMode = 'macro';

  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const mk = (tag, attrs = {}, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.append(n);
    return n;
  };
  const short = a => (typeof a === 'string' ? a : (a.orchestrator ? 'Orchestrator' : a.name.replace(/ Agent$/, '')));
  const hash = s => { let h = 2166136261; for (const c of s) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return h >>> 0; };

  /* ---------- Linear Honeycomb Geometry Helpers ---------- */
  function hexPoints(r, pointy = true) {
    const angles = pointy ? [0, 60, 120, 180, 240, 300] : [30, 90, 150, 210, 270, 330];
    return angles.map(deg => {
      const rad = (deg - 90) * Math.PI / 180;
      return `${(r * Math.cos(rad)).toFixed(1)},${(r * Math.sin(rad)).toFixed(1)}`;
    }).join(' ');
  }

  function elongatedHexPoints(w = 196, h = 76, s = 18) {
    const hw = w / 2;
    const hh = h / 2;
    return `${(-hw + s).toFixed(1)},${(-hh).toFixed(1)} ${(hw - s).toFixed(1)},${(-hh).toFixed(1)} ${hw.toFixed(1)},0 ${(hw - s).toFixed(1)},${hh.toFixed(1)} ${(-hw + s).toFixed(1)},${hh.toFixed(1)} ${(-hw).toFixed(1)},0`;
  }

  /* ---------- procedural textures for stage badges ---------- */
  const textures = new Map();
  function planetTexture(key, pal, size, sun) {
    const id = key + size;
    if (textures.has(id)) return textures.get(id);
    const c = document.createElement('canvas');
    c.width = c.height = size;
    const ctx = c.getContext('2d');
    const grad = ctx.createLinearGradient(0, 0, size, size);
    grad.addColorStop(0, pal[0] || '#222');
    grad.addColorStop(0.5, pal[1] || '#444');
    grad.addColorStop(1, pal[2] || '#111');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, size, size);
    const url = c.toDataURL();
    textures.set(id, url);
    return url;
  }

  /* ---------- stage assignment ---------- */
  function stageIndex(agent, i, n) {
    if (agent.orchestrator) return 0;
    const text = agent.name;
    const hit = STAGES.findIndex(s => s.match && s.match.test(text));
    return hit > 0 ? hit : Math.min(STAGES.length - 1, 1 + Math.floor(i / Math.max(1, n) * (STAGES.length - 1)));
  }

  /* ---------- Deterministic 90-Degree Manhattan Routing ---------- */
  function manhattanLink(p1, p2) {
    const [x1, y1] = p1, [x2, y2] = p2;
    if (Math.abs(y1 - y2) < 2) return `M ${x1} ${y1} H ${x2}`;
    if (Math.abs(x1 - x2) < 2) return `M ${x1} ${y1} V ${y2}`;
    const midY = y1 + 32;
    return `M ${x1} ${y1} V ${midY} H ${x2} V ${y2}`;
  }

  function routeFor(n) {
    if (!n || n.main) {
      const d = `M ${stages[0].x} ${MAIN_Y} H ${stages[stages.length - 1].x}`;
      const rev = `M ${stages[stages.length - 1].x} ${MAIN_Y} H ${stages[0].x}`;
      return { d, rev, label: 'MAIN BUS' };
    }
    const s = n.stage;
    const midY = MAIN_Y + 36;
    const d = `M ${stages[0].x} ${MAIN_Y} H ${s.x} V ${midY} H ${n.x} V ${n.y - 36}`;
    const rev = `M ${n.x} ${n.y - 36} V ${midY} H ${s.x} H ${stages[0].x} V ${MAIN_Y}`;
    return { d, rev, label: short(n.agent) };
  }

  /* ---------- render main mesh ---------- */
  function render(list, opts = {}) {
    agents = list || [];
    onOpen = opts.open || onOpen;
    world.textContent = '';
    nodes = {};
    stages = STAGES.map((s, i) => ({...s, i, x: PAD + i * COL, y: MAIN_Y, agents: []}));

    const others = agents.filter(a => !a.orchestrator);
    const orch = agents.find(a => a.orchestrator) || agents[0];
    if (orch) orch.orchestrator = true;

    agents.forEach(a => {
      if (a !== orch) stages[stageIndex(a, others.indexOf(a), others.length)].agents.push(a);
    });

    const rows = Math.max(1, ...stages.map(s => s.agents.length));
    width = PAD * 2 + COL * (stages.length - 1);
    height = ROW0 + rows * ROW + 30;

    // Architectural Column Grid & Header Rulers
    const grid = mk('g', {class: 'jr-grid'}, world);
    stages.forEach((s, i) => {
      if (i) mk('path', {d: `M ${s.x - COL / 2} 0 V ${height}`}, grid);
      // Persistent Column Status Header
      const colHeader = mk('text', {
        x: s.x, y: 34,
        'text-anchor': 'middle',
        fill: '#555',
        'font-family': "'JetBrains Mono',monospace",
        'font-size': '10',
        'letter-spacing': '0.08em'
      }, grid);
      colHeader.textContent = `COL ${String(i).padStart(2, '0')} // ${s.id.toUpperCase()}`;
    });
    mk('path', {class: 'jr-rule', d: `M 0 ${MAIN_Y} H ${width}`}, grid);
    for (let r = 0; r < rows; r++) {
      mk('path', {d: `M 0 ${ROW0 + r * ROW} H ${width}`, stroke: '#161616'}, grid);
    }

    const links = mk('g', {class: 'jr-links'}, world);

    // Main Orthogonal Stage Bus
    const mainBusD = `M ${stages[0].x} ${MAIN_Y} H ${stages[stages.length - 1].x}`;
    mk('path', {class: 'jr-main-bus', d: mainBusD}, links);
    mk('path', {class: 'jr-bus-flow', d: mainBusD}, links);

    // Stage Gate Breakers placed on orthogonal trunk between stages
    for (let i = 0; i < stages.length - 1; i++) {
      const s1 = stages[i], s2 = stages[i + 1];
      const gx = (s1.x + s2.x) / 2;
      const gateG = mk('g', {
        class: 'jr-gate-breaker' + (gates[s1.id] ? ' locked' : ''),
        transform: `translate(${gx} ${MAIN_Y})`,
        'data-gate': s1.id
      }, links);
      mk('polygon', {
        points: hexPoints(15, true),
        fill: '#0E0E0E',
        stroke: gates[s1.id] ? '#E60000' : '#333',
        'stroke-width': 1.5,
        class: 'jr-gate-box jr-honey-gate'
      }, gateG);
      const pin = mk('polygon', {
        points: hexPoints(7, true),
        fill: gates[s1.id] ? '#E60000' : '#444',
        class: 'jr-gate-pin'
      }, gateG);
      const lab = mk('text', {x: 0, y: 22, 'text-anchor': 'middle', fill: gates[s1.id] ? '#E60000' : '#666', 'font-family': "'JetBrains Mono',monospace", 'font-size': '8', 'font-weight': '700'}, gateG);
      lab.textContent = gates[s1.id] ? 'HOLD' : 'GATE';
      gateG.onclick = e => {
        e.stopPropagation();
        toggleGate(s1.id, gateG, pin, lab);
      };
    }

    // Regression Loop Track linking QA / Verify (Stage 75) to Build (Stage 60)
    const verifyStage = stages.find(s => s.id === 'verify') || stages[5];
    const buildStage = stages.find(s => s.id === 'build') || stages[4];
    if (verifyStage && buildStage) {
      const loopY = height - 20;
      const loopPath = `M ${verifyStage.x} ${MAIN_Y + 36} V ${loopY} H ${buildStage.x} V ${MAIN_Y + 36}`;
      const loopG = mk('g', {class: 'jr-loop-track', id: 'jrLoopTrack'}, links);
      mk('path', {d: loopPath, class: 'jr-loop-wire'}, loopG);
      const badgeG = mk('g', {transform: `translate(${(verifyStage.x + buildStage.x) / 2} ${loopY})`}, loopG);
      mk('rect', {x: -50, y: -9, width: 100, height: 18, fill: '#111', stroke: '#333', 'stroke-width': 1}, badgeG);
      const loopTxt = mk('text', {x: 0, y: 4, 'text-anchor': 'middle', fill: '#777', 'font-family': "'JetBrains Mono',monospace", 'font-size': '9', 'font-weight': '700'}, badgeG);
      loopTxt.textContent = 'FEEDBACK CIRCUIT';
      nodes._loopTrack = {el: loopG, txt: loopTxt, path: loopPath};
    }

    liveLayer = mk('g', {class: 'jr-live'}, world);
    hoverLayer = mk('g', {class: 'jr-hover'}, world);

    const planets = mk('g', {class: 'jr-planets'}, world);

    // Render Stage Nodes and Agent Instrument Clusters
    stages.forEach(s => {
      s.agents.forEach((a, r) => {
        const x = s.x;
        const y = ROW0 + r * ROW;
        const n = nodes[a.name] = {agent: a, stage: s, x, y};
        const p1 = [s.x, MAIN_Y];
        const p2 = [x, y - 36];
        n.linkD = manhattanLink(p1, p2);
        mk('path', {class: 'jr-sub-link jr-manhattan', d: n.linkD, 'data-agent': a.name}, links);
        mk('rect', {class: 'jr-junction', x: s.x - 2, y: MAIN_Y + 30, width: 4, height: 4}, links);
        drawAgent(planets, n);
      });
      drawStage(planets, s, orch);
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

  /* ---------- Stage Honeycomb Hub Drawing ---------- */
  function drawStage(parent, s, orch) {
    const r = R_MAIN + 6; // 42px radius for regular hexagon
    const g = mk('g', {
      class: 'jr-planet jr-stage' + (s.sun ? ' jr-sun' : ''),
      transform: `translate(${s.x} ${s.y})`,
      tabindex: 0,
      role: s.sun ? 'button' : 'img',
      'aria-label': s.sun && orch ? `${short(orch)}, start of the journey` : `${s.label}, ${s.pct} percent, ${s.agents.length} agents`,
      'data-stage': s.id
    }, parent);

    // Honeycomb Hexagonal Outer Chassis
    mk('polygon', {
      class: 'jr-stage-box jr-honey-stage-hex',
      points: hexPoints(r, true),
      fill: '#0C0C0C',
      stroke: s.sun ? '#E60000' : '#2A2A2A',
      'stroke-width': 2
    }, g);

    // Honeycomb Inner Concentric Ring
    mk('polygon', {
      class: 'jr-honey-inner-facet',
      points: hexPoints(r - 6, true),
      fill: 'none',
      stroke: s.sun ? 'rgba(230,0,0,0.4)' : 'rgba(255,255,255,0.08)',
      'stroke-width': 1
    }, g);

    // Center Stage Texture clipped to Hexagonal Honeycomb facet
    const defs = svg.querySelector('defs') || mk('defs', {}, svg);
    const clipId = `jr-stage-clip-${s.id}`;
    let cp = defs.querySelector('#' + clipId);
    if (!cp) {
      cp = mk('clipPath', {id: clipId}, defs);
      mk('polygon', {points: hexPoints(r - 8, true)}, cp);
    }

    mk('image', {
      href: planetTexture(s.id, s.pal, 72, s.sun),
      x: -r + 8, y: -r + 8,
      width: (r - 8) * 2, height: (r - 8) * 2,
      'clip-path': `url(#${clipId})`
    }, g);

    // Persistent Stage Header Rulers & Labels
    const t = mk('text', {
      class: 'jr-stage-name',
      x: 0, y: -(r + 14),
      'text-anchor': 'middle',
      fill: '#FFF',
      'font-family': "'Archivo', sans-serif",
      'font-size': '13',
      'font-weight': '800',
      'letter-spacing': '0.04em'
    }, g);
    t.textContent = `${String(s.i).padStart(2, '0')} // ${s.label.toUpperCase()}`;

    const pct = mk('text', {
      class: 'jr-stage-pct',
      x: 0, y: r + 18,
      'text-anchor': 'middle',
      fill: '#E60000',
      'font-family': "'JetBrains Mono', monospace",
      'font-size': '10',
      'font-weight': '700'
    }, g);
    pct.textContent = `[${s.pct}%]`;

    s.el = g;
    wire(g, () => ({stage: s, agent: s.sun ? orch : null}), s.sun && orch ? () => openAgentInspector(orch, nodes[orch.name]) : null);
  }

  /* ---------- Linear Honeycomb Agent Module Drawing ---------- */
  function drawAgent(parent, n) {
    const a = n.agent;
    const h = hash(a.name);
    const tier = a.orchestrator ? 'REASONING' : (h % 3 === 0 ? 'REASONING' : h % 3 === 1 ? 'FAST' : 'COMPACT');
    const codeIdx = String(n.stage.i).padStart(2, '0');
    const shortId = short(a).slice(0, 7).toUpperCase();

    const g = mk('g', {
      class: 'jr-planet jr-agent',
      transform: `translate(${n.x} ${n.y})`,
      tabindex: 0,
      role: 'button',
      'aria-label': `${short(a)}. Open inspector.`,
      'data-agent': a.name
    }, parent);

    // Precision Elongated Honeycomb Chassis
    // 196x76px with 18px horizontal apex chamfers
    const bg = mk('polygon', {
      class: 'jr-card-bg jr-honey-cell',
      points: elongatedHexPoints(196, 76, 18),
      fill: '#0C0C0C',
      stroke: '#262626',
      'stroke-width': 2
    }, g);

    // Subtle inner honeycomb border
    mk('polygon', {
      class: 'jr-honey-cell-inner',
      points: elongatedHexPoints(188, 68, 16),
      fill: 'none',
      stroke: 'rgba(255,255,255,0.04)',
      'stroke-width': 1
    }, g);

    // Left and Right Bus Docking Ports (Inbound / Outbound)
    const inPort = mk('polygon', {
      class: 'jr-honey-port jr-port-in',
      points: hexPoints(5, false),
      transform: 'translate(-98 0)',
      fill: '#181818',
      stroke: '#444',
      'stroke-width': 1
    }, g);
    const outPort = mk('polygon', {
      class: 'jr-honey-port jr-port-out',
      points: hexPoints(5, false),
      transform: 'translate(98 0)',
      fill: '#181818',
      stroke: '#444',
      'stroke-width': 1
    }, g);

    // Horizontal Section Divider: Separating Crown Apex from Core Nucleus
    mk('line', {x1: -80, y1: -14, x2: 80, y2: -14, class: 'jr-card-div'}, g);

    // PART 01 // CROWN APEX: Stage Code + Callsign + Model Tier + Hex LED
    const idText = mk('text', {class: 'jr-card-id', x: -74, y: -23}, g);
    idText.textContent = `${codeIdx} // ${shortId}`;

    const tierText = mk('text', {class: 'jr-card-tier', x: 20, y: -23}, g);
    tierText.textContent = tier;

    // Hexagonal Status LED (ال‌ای‌دی شش‌ضلعی)
    const ledG = mk('g', {transform: 'translate(68 -27)'}, g);
    const led = mk('polygon', {
      class: 'jr-card-led jr-honey-led',
      points: hexPoints(5, true),
      fill: '#333',
      stroke: '#222',
      'stroke-width': 1
    }, ledG);
    n.ledEl = led;

    // PART 02 // CORE NUCLEUS: Live Streaming Ticker & Agent Callsign
    const ticker = mk('text', {class: 'jr-card-ticker', x: -74, y: 6}, g);
    ticker.textContent = short(a);
    n.tickerEl = ticker;

    // PART 04 // TELEMETRY COMB: Step Budget Bar & Token Burn Rate
    mk('rect', {class: 'jr-bar-bg', x: -74, y: 16, width: 148, height: 4}, g);
    const bar = mk('rect', {class: 'jr-bar-fill', x: -74, y: 16, width: 28, height: 4}, g);
    n.barEl = bar;

    // PART 03 // FACET MATRIX: Tools & Skills Summary
    const tools = (a.tools || []).filter(t => t.kind !== 'agent').length;
    const skills = (a.skills || []).length;
    const subMeta = mk('text', {class: 'jr-card-sub', x: -74, y: 28}, g);
    subMeta.textContent = `${tools} tools · ${skills} skills`;
    n.callsEl = subMeta;

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
    const c = mk('rect', {class: cls, x: -4, y: -4, width: 8, height: 8, rx: 0}, parent);
    const anim = mk('animateMotion', {path: d, dur: dur + 's', begin, repeatCount: once ? 1 : 'indefinite', fill: 'remove'}, c);
    return {c, anim};
  }

  function packet(parent, d, cls, labelText) {
    const c = mk('g', {class: 'jr-packet'}, parent);
    mk('rect', {class: cls, x: -5, y: -5, width: 10, height: 10, rx: 0, fill: '#E60000', stroke: '#FFF', 'stroke-width': 1.5}, c);
    if (labelText) {
      const gLab = mk('g', {transform: 'translate(10 -6)'}, c);
      mk('rect', {x: 0, y: -9, width: labelText.length * 7 + 10, height: 16, fill: '#0A0A0A', stroke: '#E60000', 'stroke-width': 1}, gLab);
      const txt = mk('text', {x: 5, y: 3, fill: '#FFF', 'font-family': "'JetBrains Mono',monospace", 'font-size': '10', 'font-weight': '700'}, gLab);
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
      info.innerHTML = '<span><i class="jr-key jr-key-req"></i>Request</span><span><i class="jr-key jr-key-res"></i>Response</span><span>Linear Honeycomb Mesh // Click any agent node for Cell Anatomy</span>';
      return;
    }
    const orch = agents.find(a => a.orchestrator);
    const from = orch ? short(orch) : 'Orchestrator';
    let rows = '', title = '', sub = '';
    if (t.agent && !t.agent.orchestrator || (t.agent && t.node)) {
      const a = t.agent, next = stages[t.stage.i + 1];
      title = short(a);
      sub = `${t.stage.label} · ${t.stage.pct}%`;
      rows = `<tr><th class="jr-th-req">Request</th><td>${esc(from)} → ${esc(short(a))}</td></tr>
        <tr><th class="jr-th-res">Response</th><td>${esc(short(a))} → ${esc(from)}</td></tr>
        <tr><th>Cell Form</th><td><span class="jr-honey-tag">Linear Hexagon</span></td></tr>
        <tr><th>Stage Gate</th><td>${gates[t.stage.id] ? 'LOCKED (Pulsing hold)' : 'OPEN'}</td></tr>
        <tr><th>Tools</th><td>${(a.tools || []).map(x => esc(x.title || x.name)).join(', ') || '—'}</td></tr>
        <tr><th>Anatomy</th><td><div class="jr-honey-mini-parts"><span title="Part 1: Crown Apex">[01 Apex]</span><span title="Part 2: Core Nucleus">[02 Nucleus]</span><span title="Part 3: Facet Matrix">[03 Facets]</span><span title="Part 4: Telemetry Comb">[04 Comb]</span><span title="Part 5: Bus Ports">[05 Ports]</span></div></td></tr>`;
    } else {
      title = t.stage.label;
      sub = `${t.stage.pct}% of journey`;
      rows = `<tr><th class="jr-th-req">Gate</th><td>${gates[t.stage.id] ? 'LOCKED' : 'OPEN'}</td></tr>
        <tr><th>Hub Form</th><td><span class="jr-honey-tag">Honeycomb Hub</span></td></tr>
        <tr><th>Agents</th><td>${t.stage.agents.map(short).join(', ') || 'None'}</td></tr>`;
    }
    info.className = 'jr-info';
    info.innerHTML = `<div class="jr-info-head"><b>${esc(title)}</b><span>${esc(sub)}</span></div><table>${rows}</table>`;
  }

  /* ---------- Stage Gate Breakers ---------- */
  function toggleGate(stageId, gateG, pin, lab) {
    gates[stageId] = !gates[stageId];
    const isLocked = gates[stageId];
    gateG.classList.toggle('locked', isLocked);
    pin.setAttribute('fill', isLocked ? '#E60000' : '#444');
    lab.textContent = isLocked ? 'HOLD' : 'GATE';
    lab.setAttribute('fill', isLocked ? '#E60000' : '#666');

    window.dispatchEvent(new CustomEvent('kryzen:gate_toggle', {
      detail: { stage: stageId, locked: isLocked }
    }));

    if (window.toast) {
      window.toast(isLocked ? `⚠ Stage Gate [${stageId.toUpperCase()}] LOCKED. Pipeline will hold before entry.` : `✓ Stage Gate [${stageId.toUpperCase()}] RELEASED.`, isLocked ? 'warn' : 'ok');
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
    const tools = (a.tools || []).map(t => t.title || t.name);
    const skills = a.skills || [];
    const h = hash(a.name);
    const tier = a.orchestrator ? 'REASONING' : (h % 3 === 0 ? 'REASONING' : h % 3 === 1 ? 'FAST' : 'COMPACT');

    let currentTab = initialTab || 'config';

    function renderDrawerContent() {
      drawerEl.innerHTML = `
        <button type="button" class="jr-drawer-tab" id="jrDrawerTab" title="Collapse inspector panel" aria-label="Collapse inspector">›</button>
        <div class="jr-drawer-head">
          <div class="jr-drawer-title-wrap">
            <span class="jr-drawer-badge">LINEAR HONEYCOMB NODE</span>
            <h3>0${node?.stage?.i || 0} // ${esc(short(a)).toUpperCase()}</h3>
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
                ${tools.map(t => `<span style="background:#161616;border:1px solid #333;padding:2px 6px;font-size:10px">${esc(t)}</span>`).join('') || '<span style="color:#666">No direct tools</span>'}
              </div>
            </div>
            <div class="jr-drawer-field">
              <label>LOADED SKILLS (${skills.length})</label>
              <div style="display:flex;gap:4px;flex-wrap:wrap">
                ${skills.map(s => `<span style="background:#1a1414;border:1px solid #522;color:#ff8888;padding:2px 6px;font-size:10px">${esc(s)}</span>`).join('') || '<span style="color:#666">No custom skills</span>'}
              </div>
            </div>
            <div class="jr-honey-anatomy-teaser">
              <div class="jr-teaser-head">
                <i class="jr-hex-icon">⬢</i>
                <span>HONEYCOMB CELL STRUCTURE</span>
              </div>
              <p>این نود با قالب شش‌ضلعی پیوسته (Linear Honeycomb Cell) شامل ۵ بخش ساختاری (تاج، هسته، ماتریس، شانه و پورت‌ها) مهندسی شده است.</p>
              <button type="button" class="btn" id="jrViewAnatomyBtn" style="background:#181818;border:1px solid #333;color:#fff;font-size:10px;padding:4px 8px;cursor:pointer">مشاهده تشریح کامل ۵ بخش سلول →</button>
            </div>
            <div style="margin-top:auto;display:flex;gap:8px">
              <button type="button" class="btn primary" id="jrEditAgentBtn" style="background:#E60000;border:none;flex:1;font-size:11px;padding:6px">Open Editor</button>
            </div>
          ` : `
            <!-- Full Interactive Honeycomb Cell Anatomy Section -->
            <div class="jr-honey-anatomy-box">
              <div class="jr-honey-anatomy-header">
                <div class="jr-honey-title-wrap">
                  <span class="jr-honey-badge">HONEYCOMB SPECIFICATION</span>
                  <h4>ANATOMY OF CELL // 6-FACET SPEC</h4>
                </div>
                <span class="jr-honey-tag">LINEAR 6-FACET</span>
              </div>

              <!-- Interactive SVG Schematic of the Honeycomb Cell -->
              <div class="jr-honey-schematic-wrap">
                <svg viewBox="-115 -52 230 104" class="jr-honey-schematic" id="jrAnatomySvg">
                  <!-- Honeycomb Cell Base Polygon -->
                  <polygon points="-80,-38 80,-38 98,0 80,38 -80,38 -98,0" class="jr-anat-cell" />
                  <polygon points="-75,-34 75,-34 92,0 75,34 -75,34 -92,0" class="jr-anat-cell-inner" />

                  <!-- Part 5: Inbound & Outbound Bus Docking Ports -->
                  <polygon points="2.5,-4.3 5,0 2.5,4.3 -2.5,4.3 -5,0 -2.5,-4.3" transform="translate(-98 0)" class="jr-anat-port port-in" id="jrAnatPortIn" />
                  <polygon points="2.5,-4.3 5,0 2.5,4.3 -2.5,4.3 -5,0 -2.5,-4.3" transform="translate(98 0)" class="jr-anat-port port-out" id="jrAnatPortOut" />

                  <!-- Part 1 & 2 divider -->
                  <line x1="-75" y1="-14" x2="75" y2="-14" class="jr-anat-div" />

                  <!-- Part 1: Hexagonal LED -->
                  <polygon points="0,-4.5 3.9,-2.2 3.9,2.2 0,4.5 -3.9,2.2 -3.9,-2.2" transform="translate(68 -26)" class="jr-anat-led" />

                  <!-- Text annotations -->
                  <text x="-70" y="-22" class="jr-anat-txt-crown">0${node?.stage?.i || 0} // ${esc(short(a)).slice(0, 7).toUpperCase()}</text>
                  <text x="14" y="-22" class="jr-anat-txt-tier">${tier}</text>
                  <text x="-70" y="6" class="jr-anat-txt-core">${esc(short(a))}</text>
                  <rect x="-70" y="16" width="140" height="4" class="jr-anat-bar-bg" />
                  <rect x="-70" y="16" width="38" height="4" class="jr-anat-bar-fill" />
                  <text x="-70" y="28" class="jr-anat-txt-facets">${tools.length} tools · ${skills.length} skills</text>

                  <!-- Callout Pins pointing to the 5 compartments -->
                  <g class="jr-anat-pin" data-part="1" transform="translate(-40 -45)">
                    <rect x="-12" y="-7" width="24" height="14" class="jr-pin-box" />
                    <text x="0" y="3" text-anchor="middle" class="jr-pin-txt">[1]</text>
                    <line x1="0" y1="7" x2="0" y2="18" class="jr-pin-lead" />
                  </g>
                  <g class="jr-anat-pin" data-part="2" transform="translate(0 3)">
                    <rect x="-12" y="-7" width="24" height="14" class="jr-pin-box" />
                    <text x="0" y="3" text-anchor="middle" class="jr-pin-txt">[2]</text>
                  </g>
                  <g class="jr-anat-pin" data-part="3" transform="translate(20 45)">
                    <line x1="0" y1="-7" x2="0" y2="-16" class="jr-pin-lead" />
                    <rect x="-12" y="-7" width="24" height="14" class="jr-pin-box" />
                    <text x="0" y="3" text-anchor="middle" class="jr-pin-txt">[3]</text>
                  </g>
                  <g class="jr-anat-pin" data-part="4" transform="translate(-45 45)">
                    <line x1="0" y1="-7" x2="0" y2="-24" class="jr-pin-lead" />
                    <rect x="-12" y="-7" width="24" height="14" class="jr-pin-box" />
                    <text x="0" y="3" text-anchor="middle" class="jr-pin-txt">[4]</text>
                  </g>
                  <g class="jr-anat-pin" data-part="5" transform="translate(-102 -18)">
                    <rect x="-12" y="-7" width="24" height="14" class="jr-pin-box" />
                    <text x="0" y="3" text-anchor="middle" class="jr-pin-txt">[5]</text>
                    <line x1="0" y1="7" x2="4" y2="14" class="jr-pin-lead" />
                  </g>
                </svg>
              </div>

              <!-- 5 Structural Parts of the Honeycomb Module -->
              <div class="jr-honey-parts-list">
                <!-- Part 1 -->
                <div class="jr-honey-part-card" id="jrAnatPart1">
                  <div class="jr-part-head">
                    <span class="jr-part-num">[01]</span>
                    <div class="jr-part-title">
                      <b>CROWN APEX</b>
                      <span class="jr-part-fa">تاج فوقانی سلول</span>
                    </div>
                    <span class="jr-part-status">ACTIVE</span>
                  </div>
                  <p class="jr-part-desc">هدر ساختاری شامل مختصات مرحله (Stage Coordinate)، برچسب طبقه‌بندی مدل هوش مصنوعی (Reasoning / Fast / Compact) و نشانگر شش‌ضلعی وضعیت سلامت و پالس ایجنت (Hexagonal Status LED).</p>
                  <div class="jr-part-metrics">
                    <span><b>STAGE:</b> 0${node?.stage?.i || 0} // ${node?.stage?.label?.toUpperCase()}</span>
                    <span><b>TIER:</b> ${tier}</span>
                    <span><b>LED:</b> HEXAGONAL BEACON</span>
                  </div>
                </div>

                <!-- Part 2 -->
                <div class="jr-honey-part-card" id="jrAnatPart2">
                  <div class="jr-part-head">
                    <span class="jr-part-num">[02]</span>
                    <div class="jr-part-title">
                      <b>CORE NUCLEUS</b>
                      <span class="jr-part-fa">هسته‌ی پردازشی و هویت ایجنت</span>
                    </div>
                    <span class="jr-part-status">RUNNING</span>
                  </div>
                  <p class="jr-part-desc">مغز و هسته مرکزی پردازش؛ نمایشگر هویت تخصصی ایجنت، دستورالعمل‌های محول‌شده‌ی سیستم، و متن متحرک لحظه‌ای (Live Streaming Ticker) از اجرای تسک‌ها و ابزارها.</p>
                  <div class="jr-part-metrics">
                    <span><b>IDENTITY:</b> ${esc(short(a))}</span>
                    <span><b>ROLE:</b> AUTONOMOUS SPECIALIST</span>
                  </div>
                </div>

                <!-- Part 3 -->
                <div class="jr-honey-part-card" id="jrAnatPart3">
                  <div class="jr-part-head">
                    <span class="jr-part-num">[03]</span>
                    <div class="jr-part-title">
                      <b>FACET MATRIX</b>
                      <span class="jr-part-fa">ماتریس خانه‌های ابزار و مهارت</span>
                    </div>
                    <span class="jr-part-status">${tools.length}T / ${skills.length}S</span>
                  </div>
                  <p class="jr-part-desc">خانه‌های لانه‌زنبوری مهارت‌ها و ابزارهای سندباکس شده در محیط Bubblewrap؛ هر خانه شامل ابزارهای سیستمی و مهارت‌های بارگذاری شده برای انجام عملیات اجرایی است.</p>
                  <div class="jr-part-badges">
                    ${tools.slice(0, 8).map(t => `<span class="jr-facet-chip"><i class="jr-hex-dot"></i>${esc(t)}</span>`).join('') || '<span style="color:#666">No direct tools</span>'}
                    ${skills.slice(0, 6).map(s => `<span class="jr-facet-chip skill"><i class="jr-hex-dot"></i>${esc(s)}</span>`).join('')}
                  </div>
                </div>

                <!-- Part 4 -->
                <div class="jr-honey-part-card" id="jrAnatPart4">
                  <div class="jr-part-head">
                    <span class="jr-part-num">[04]</span>
                    <div class="jr-part-title">
                      <b>TELEMETRY COMB</b>
                      <span class="jr-part-fa">شانه تله‌متری و پایش مصرف توکن</span>
                    </div>
                    <span class="jr-part-status">LIVE GAUGES</span>
                  </div>
                  <p class="jr-part-desc">نوار تله‌متری دقیق 4 پیکسلی در کف سلول؛ پایش گام‌به‌گام مصرف توکن، آهنگ فراخوانی توابع، زمان پاسخ‌دهی و پایش مدارهای بازخورد خطایابی (Regression Circuit Monitoring).</p>
                  <div class="jr-part-metrics">
                    <span><b>GAUGE:</b> STEP CONSUMPTION BAR</span>
                    <span><b>TELEMETRY:</b> REAL-TIME SSE PACKETS</span>
                  </div>
                </div>

                <!-- Part 5 -->
                <div class="jr-honey-part-card" id="jrAnatPart5">
                  <div class="jr-part-head">
                    <span class="jr-part-num">[05]</span>
                    <div class="jr-part-title">
                      <b>BUS DOCKING PORTS</b>
                      <span class="jr-part-fa">پورت‌های کوپلینگ باس داده</span>
                    </div>
                    <span class="jr-part-status">MANHATTAN 90°</span>
                  </div>
                  <p class="jr-part-desc">رأس‌های شش‌ضلعی چپ و راست سلول جهت اتصال مستقیم به خطوط باس متعامد 90 درجه منهتن. رأس سمت چپ ورودی بسته‌های فرمان از ارکستریتور و رأس سمت راست خروجی دلیوری محصولات کار به مراحل بعدی است.</p>
                  <div class="jr-part-metrics">
                    <span><b>INBOUND:</b> LEFT APEX (-98, 0)</span>
                    <span><b>OUTBOUND:</b> RIGHT APEX (98, 0)</span>
                  </div>
                </div>
              </div>
            </div>
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
        pin.addEventListener('click', () => {
          const partNum = pin.dataset.part;
          const targetCard = drawerEl.querySelector(`#jrAnatPart${partNum}`);
          if (targetCard) {
            targetCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            targetCard.classList.add('highlight');
            setTimeout(() => targetCard.classList.remove('highlight'), 1500);
          }
        });
      });
    }

    renderDrawerContent();
  }

  /* ---------- Wireframe Minimap ---------- */
  function renderMinimap() {
    if (!minimapSvg) return;
    minimapSvg.innerHTML = '';
    const mw = 140, mh = 60;
    const sx = mw / (width || 1), sy = mh / (height || 1);

    stages.forEach(s => {
      // Hexagonal stage marker in minimap
      mk('polygon', {
        points: hexPoints(4, true),
        transform: `translate(${s.x * sx} ${s.y * sy})`,
        fill: s.sun ? '#E60000' : '#444'
      }, minimapSvg);
      s.agents.forEach((a, r) => {
        // Hexagonal agent card marker in minimap
        mk('polygon', {
          points: elongatedHexPoints(10, 5, 2),
          transform: `translate(${s.x * sx} ${(ROW0 + r * ROW) * sy})`,
          fill: '#222', stroke: '#444', 'stroke-width': 0.5
        }, minimapSvg);
      });
    });

    // Viewport Radar Frame
    const vx = Math.max(0, -view.x / view.z * sx);
    const vy = Math.max(0, -view.y / view.z * sy);
    const vw = Math.min(mw, (svg.clientWidth / view.z) * sx);
    const vh = Math.min(mh, (svg.clientHeight / view.z) * sy);

    mk('rect', {
      class: 'jr-minimap-viewport',
      x: vx, y: vy, width: vw, height: vh
    }, minimapSvg);
  }

  /* ---------- 0 to 100 ruler ---------- */
  function renderRuler() {
    ruler.innerHTML = `<div class="jr-fill" id="jrFill"></div>` +
      stages.map(s => `<button type="button" class="jr-cell" data-i="${s.i}" title="Go to ${esc(s.label)}"><b>${s.pct}</b><span>${esc(s.label)}</span></button>`).join('');
    fill = ruler.querySelector('#jrFill');
    ruler.querySelectorAll('.jr-cell').forEach(b => {
      const s = stages[+b.dataset.i];
      b.onclick = () => center(s.x);
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
    ruler.querySelectorAll('.jr-cell').forEach((b, i) => b.classList.toggle('reached', i <= top));
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
    view.z = whole ? Math.min(w / width, h / height, 1.4) : Math.max(.62, Math.min(h / height, 1.1));
    if (w / width > view.z) view.z = Math.min(w / width, 1.4);
    view.x = 0; view.y = 0;
    clampView();
  }

  function zoomTo(z, px, py) {
    const w = svg.clientWidth, h = svg.clientHeight, cx = px ?? w / 2, cy = py ?? h / 2;
    z = Math.max(.3, Math.min(2.2, z));
    const wx = (cx - view.x) / view.z, wy = (cy - view.y) / view.z;
    view.z = z; view.x = cx - wx * z; view.y = cy - wy * z; view.auto = false;
    clampView();
  }

  function center(wx) {
    view.x = svg.clientWidth / 2 - wx * view.z;
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
      if (n?.ledEl) n.ledEl.setAttribute('fill', '#E60000');
      if (!live.has(name) && n) live.set(name, drawRoutes(liveLayer, [routeFor(n)], 'live'));
    } else {
      live.get(name)?.remove();
      live.delete(name);
      n?.el?.classList.remove('active');
      n?.el?.classList.add('done');
      if (n?.ledEl) n.ledEl.setAttribute('fill', '#00E676');
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
    if (n?.callsEl) {
      const tools = (n.agent.tools || []).filter(t => t.kind !== 'agent').length;
      n.callsEl.textContent = `${tools} tools · ${count} calls`;
    }
  }

  function setStep(name, step, max) {
    steps[name] = {step, max};
    const n = nodes[name];
    if (n?.barEl && max > 0) {
      const pct = Math.min(168, Math.max(10, (step / max) * 168));
      n.barEl.setAttribute('width', String(pct));
    }
  }

  function setLiveTicker(name, text) {
    const n = nodes[name];
    if (n?.tickerEl) {
      n.tickerEl.textContent = text.slice(0, 22);
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
      if (n?.ledEl) n.ledEl.setAttribute('fill', '#333');
    });
    done.clear();
    if (nodes._loopTrack) {
      nodes._loopTrack.el.classList.remove('active');
      nodes._loopTrack.txt.textContent = 'FEEDBACK CIRCUIT';
    }
    updateFill();
  }

  /* ---------- initialization ---------- */
  function init(root) {
    host = root;
    host.innerHTML = `
      <div class="jr-ruler" id="jrRuler" role="group" aria-label="Journey from 0 to 100"></div>
      <svg class="jr-svg" id="jrSvg" aria-label="Agent mesh"><g id="jrWorld"></g></svg>
      <div class="jr-info" id="jrInfo" aria-live="polite"></div>
      <div class="jr-minimap-wrap" id="jrMinimapWrap">
        <div class="jr-minimap-modes">
          <button class="btn on" data-mode="macro">[1] Macro</button>
          <button class="btn" data-mode="telemetry">[2] Telemetry</button>
          <button class="btn" data-mode="diff">[3] Handoff</button>
        </div>
        <svg class="jr-minimap" id="jrMinimap"></svg>
      </div>
      <div class="jr-agent-drawer hidden" id="jrAgentDrawer" style="display:none" hidden></div>
    `;

    ruler = host.querySelector('#jrRuler');
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
        host.querySelectorAll('.jr-minimap-modes button').forEach(b => b.classList.remove('on'));
        btn.classList.add('on');
        activeViewMode = btn.dataset.mode;
        if (activeViewMode === 'macro') fit(true);
        else if (activeViewMode === 'telemetry') zoomTo(1.3);
        else if (activeViewMode === 'diff') {
          fit(true);
          if (nodes._loopTrack) nodes._loopTrack.el.classList.add('active');
        }
      };
    });

    document.querySelectorAll('.mesh-bar [data-layer]').forEach(b => b.onclick = () => {
      const on = b.classList.toggle('on');
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
        const r = minimapSvg.getBoundingClientRect();
        const mw = 140, mh = 60;
        const mx = (e.clientX - r.left) / mw;
        const my = (e.clientY - r.top) / mh;
        view.x = svg.clientWidth / 2 - mx * width * view.z;
        view.y = svg.clientHeight / 2 - my * height * view.z;
        view.auto = false;
        clampView();
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
