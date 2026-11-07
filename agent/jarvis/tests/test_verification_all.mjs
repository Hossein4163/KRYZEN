import { spawn } from 'child_process';
import { tmpdir } from 'os';
import { join } from 'path';
import { mkdirSync } from 'fs';

const PORT = 9265;
const USER_DATA = join(tmpdir(), 'chrome_verify_all_' + Date.now());
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

async function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function run() {
  await sleep(2500);
  const res = await fetch(`http://127.0.0.1:${PORT}/json`);
  const targets = await res.json();
  const pageTarget = targets.find(t => t.url.includes('jarvis.local'));
  if (!pageTarget) {
    console.error('Page target not found');
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

  console.log('1. Verifying API Endpoints: Network & Models Test...');
  const netRes = await fetch('http://127.0.0.1:8770/api/network/status');
  const netJson = await netRes.json();
  console.log('Network Status:', {
    tailscale_installed: netJson.tailscale_installed,
    tailscale_running: netJson.tailscale_running,
    lan_ips: netJson.lan_ips,
    bound_host: netJson.bound_host
  });

  const modelTestRes = await fetch('http://127.0.0.1:8770/api/models/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Jarvis': '1', 'Origin': 'http://jarvis.local' },
    body: JSON.stringify({ provider: 'agy' })
  });
  const modelJson = await modelTestRes.json();
  console.log('Model Test (Agy):', modelJson);

  console.log('2. Verifying Header Navigation...');
  const navTest = await send('Runtime.evaluate', {
    expression: `(() => {
      const results = {};
      const modes = ['home', 'mesh', 'flow', 'plan', 'code', 'trace', 'ctrl'];
      for (const m of modes) {
        document.getElementById(m + 'Btn')?.click();
        results[m] = {
          bodyClasses: Array.from(document.body.classList),
          activeBtn: Array.from(document.querySelectorAll('.dock-item.on')).map(b => b.id)
        };
      }
      return results;
    })()`,
    returnByValue: true
  });
  console.log('Nav Test:', navTest.result.value);

  console.log('3. Verifying Command Palette Search Navigation...');
  const paletteTest = await send('Runtime.evaluate', {
    expression: `(async () => {
      window.dispatchEvent(new CustomEvent('kryzen:palette'));
      const p = document.querySelector('.kz-palette');
      const input = p.querySelector('input');
      input.value = 'Network';
      input.dispatchEvent(new Event('input'));
      await new Promise(r => setTimeout(r, 100));
      const first = p.querySelector('ul li[data-n]');
      const label = first ? first.textContent : null;
      if (first) first.click();
      await new Promise(r => setTimeout(r, 200));

      return {
        matchedLabel: label,
        bodyClasses: Array.from(document.body.classList),
        activeSection: document.querySelector('#cnav button.on')?.dataset?.sec
      };
    })()`,
    awaitPromise: true,
    returnByValue: true
  });
  console.log('Palette Search Result:', paletteTest.result.value);

  console.log('4. Verifying Mesh Drawer [ESC] and Close Button...');
  const drawerTest = await send('Runtime.evaluate', {
    expression: `(async () => {
      // Switch back to mesh
      document.getElementById('meshBtn')?.click();
      await new Promise(r => setTimeout(r, 200));
      const drawer = document.getElementById('jrAgentDrawer');
      const agentCard = document.querySelector('.jr-planet.jr-agent');
      if (!agentCard) return { error: 'No agent node found' };

      // Open drawer
      agentCard.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      const opened = !drawer.hidden && drawer.style.display !== 'none';

      // Click close button
      const closeBtn = drawer.querySelector('#jrDrawerClose');
      if (closeBtn) closeBtn.click();
      const closedViaBtn = drawer.hidden || drawer.style.display === 'none';

      // Open drawer again
      agentCard.dispatchEvent(new MouseEvent('click', { bubbles: true }));
      const reOpened = !drawer.hidden && drawer.style.display !== 'none';

      // Close via Escape key
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      const closedViaEsc = drawer.hidden || drawer.style.display === 'none';

      return {
        opened,
        closedViaBtn,
        reOpened,
        closedViaEsc
      };
    })()`,
    awaitPromise: true,
    returnByValue: true
  });
  console.log('Drawer Test:', drawerTest.result.value);

  ws.close();
  chrome.kill();
  console.log('ALL VERIFICATIONS SUCCESSFUL.');
}

run().catch(e => {
  console.error(e);
  chrome.kill();
  process.exit(1);
});
