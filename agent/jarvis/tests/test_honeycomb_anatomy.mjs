import { spawn } from 'child_process';
import { writeFileSync, mkdirSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

const PORT = 9268;
const USER_DATA = join(tmpdir(), 'chrome_honeycomb_' + Date.now());
mkdirSync(USER_DATA, { recursive: true });

const chrome = spawn('/usr/bin/chromium', [
  '--headless=new',
  '--no-sandbox',
  '--disable-gpu',
  '--user-data-dir=' + USER_DATA,
  '--remote-debugging-port=' + PORT,
  '--window-size=1920,1080',
  'http://jarvis.local/'
]);

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function run() {
  await sleep(3000);

  const res = await fetch(`http://127.0.0.1:${PORT}/json`);
  const targets = await res.json();
  const pageTarget = targets.find(t => t.url.includes('jarvis.local') || t.title.includes('KRYZEN') || t.title.includes('DevPilot'));
  if (!pageTarget) {
    console.error('Target page not found:', targets);
    chrome.kill();
    process.exit(1);
  }

  const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);

  let idCounter = 1;
  const pending = new Map();

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(msg.error);
      else resolve(msg.result);
    }
  };

  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = idCounter++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });

  await new Promise(r => ws.onopen = r);
  await send('Page.enable');
  await send('Runtime.enable');
  await sleep(1500);

  // Switch to Mesh view
  await send('Runtime.evaluate', {
    expression: `(async () => {
      document.getElementById('meshBtn')?.click();
      for (let i = 0; i < 20; i++) {
        if (document.querySelector('.jr-planet.jr-agent')) break;
        await new Promise(r => setTimeout(r, 100));
      }
    })()`,
    awaitPromise: true
  });

  console.log('--- 1. Testing Honeycomb Mesh Geometry ---');
  const geomTest = await send('Runtime.evaluate', {
    expression: `
      (() => {
        const stageHexes = document.querySelectorAll('polygon.jr-honey-stage-hex');
        const agentCells = document.querySelectorAll('polygon.jr-honey-cell');
        const busPorts = document.querySelectorAll('polygon.jr-honey-port');
        const hexLeds = document.querySelectorAll('polygon.jr-honey-led');
        const gateBreakers = document.querySelectorAll('polygon.jr-honey-gate');
        const anatomyBtn = document.getElementById('meshAnatomyBtn');

        const firstStagePoints = stageHexes[0]?.getAttribute('points') || '';
        const firstAgentPoints = agentCells[0]?.getAttribute('points') || '';

        return {
          stageHexCount: stageHexes.length,
          agentCellCount: agentCells.length,
          busPortCount: busPorts.length,
          hexLedCount: hexLeds.length,
          gateBreakerCount: gateBreakers.length,
          hasAnatomyBtn: !!anatomyBtn,
          firstStagePoints,
          firstAgentPoints,
          isStageHexagonal: firstStagePoints.split(' ').length === 6,
          isAgentElongatedHex: firstAgentPoints.split(' ').length === 6
        };
      })()
    `,
    returnByValue: true
  });
  console.log('Geometry Test Result:', JSON.stringify(geomTest.result.value, null, 2));

  // Capture screenshot of honeycomb mesh
  const ss1 = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync('/home/kryazzy/.gemini/antigravity/brain/608cff75-adca-437b-8996-b6392df94573/honeycomb_mesh.png', Buffer.from(ss1.data, 'base64'));
  console.log('Saved honeycomb_mesh.png');

  console.log('--- 2. Testing Honeycomb Anatomy Drawer ---');
  const anatomyTest = await send('Runtime.evaluate', {
    expression: `(async () => {
      const anatomyBtn = document.getElementById('meshAnatomyBtn');
      if (!anatomyBtn) return { error: 'No #meshAnatomyBtn found' };
      
      anatomyBtn.click();
      await new Promise(r => setTimeout(r, 200));
      
      const drawer = document.getElementById('jrAgentDrawer');
      const isOpen = !drawer.hidden && drawer.style.display !== 'none';
      
      const anatomyBox = drawer.querySelector('.jr-honey-anatomy-box');
      const schematicSvg = drawer.querySelector('#jrAnatomySvg');
      const pins = drawer.querySelectorAll('.jr-anat-pin');
      const partCards = drawer.querySelectorAll('.jr-honey-part-card');

      // Test clicking pin 3
      const pin3 = drawer.querySelector('.jr-anat-pin[data-part="3"]');
      let pinClicked = false;
      if (pin3) {
        pin3.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        await new Promise(r => setTimeout(r, 50));
        const targetCard = drawer.querySelector('#jrAnatPart3');
        pinClicked = targetCard && targetCard.classList.contains('highlight');
      }

      const partsData = Array.from(partCards).map(c => ({
        id: c.id,
        num: c.querySelector('.jr-part-num')?.textContent?.trim(),
        title: c.querySelector('.jr-part-title b')?.textContent?.trim(),
        faTitle: c.querySelector('.jr-part-fa')?.textContent?.trim(),
        descLength: c.querySelector('.jr-part-desc')?.textContent?.length
      }));

      return {
        isOpen,
        hasAnatomyBox: !!anatomyBox,
        hasSchematicSvg: !!schematicSvg,
        pinCount: pins.length,
        partCardCount: partCards.length,
        pinClicked,
        partsData
      };
    })()`,
    awaitPromise: true,
    returnByValue: true
  });
  console.log('Anatomy Test Result:', JSON.stringify(anatomyTest.result.value, null, 2));

  // Capture screenshot of Honeycomb Anatomy drawer
  await sleep(400);
  const ss2 = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync('/home/kryazzy/.gemini/antigravity/brain/608cff75-adca-437b-8996-b6392df94573/honeycomb_anatomy_drawer.png', Buffer.from(ss2.data, 'base64'));
  console.log('Saved honeycomb_anatomy_drawer.png');

  console.log('--- 3. Testing Hover Tooltip Honeycomb Compartments ---');
  const hoverTest = await send('Runtime.evaluate', {
    expression: `
      (() => {
        const firstAgent = document.querySelector('.jr-planet.jr-agent');
        if (!firstAgent) return { error: 'No agent found' };
        
        firstAgent.dispatchEvent(new PointerEvent('pointerenter', { bubbles: true }));
        const info = document.getElementById('jrInfo');
        
        return {
          hasTag: !!info?.querySelector('.jr-honey-tag'),
          hasMiniParts: !!info?.querySelector('.jr-honey-mini-parts')
        };
      })()
    `,
    returnByValue: true
  });
  console.log('Hover Test Result:', JSON.stringify(hoverTest.result.value, null, 2));

  ws.close();
  chrome.kill();
  process.exit(0);
}

run().catch(e => {
  console.error(e);
  chrome.kill();
  process.exit(1);
});
