import { spawn } from 'child_process';
import { writeFileSync, mkdirSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

const PORT = 9256;
const USER_DATA = join(tmpdir(), 'chrome_mesh_' + Date.now());
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

  console.log('Testing Mesh Scrolling...');
  const scrollTest = await send('Runtime.evaluate', {
    expression: `
      (() => {
        const svg = document.getElementById('jrSvg');
        if (!svg) return { error: 'No jrSvg found' };
        const initialTransform = document.getElementById('jrWorld')?.getAttribute('transform');
        
        // Dispatch wheel event
        const wheelEv = new WheelEvent('wheel', {
          deltaY: 200,
          deltaX: 0,
          clientX: 500,
          clientY: 500,
          bubbles: true,
          cancelable: true
        });
        svg.dispatchEvent(wheelEv);
        
        const afterWheelTransform = document.getElementById('jrWorld')?.getAttribute('transform');
        return {
          initialTransform,
          afterWheelTransform,
          changed: initialTransform !== afterWheelTransform
        };
      })()
    `,
    returnByValue: true
  });
  console.log('Scroll Test Result:', scrollTest.result.value);

  console.log('Testing Agent Inspector Drawer Opening and Hiding...');
  const drawerTest = await send('Runtime.evaluate', {
    expression: `
      (() => {
        const drawer = document.getElementById('jrAgentDrawer');
        if (!drawer) return { error: 'No jrAgentDrawer found' };
        
        // Find an agent card and click it
        const agentCard = document.querySelector('.jr-planet.jr-agent');
        if (!agentCard) return { error: 'No agent node found' };
        agentCard.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        
        const openedState = {
          hidden: drawer.hidden,
          classList: Array.from(drawer.classList),
          agent: drawer.dataset.agent,
          hasCloseBtn: !!drawer.querySelector('#jrDrawerClose'),
          hasTabBtn: !!drawer.querySelector('#jrDrawerTab')
        };
        
        // Now test closing via Escape key
        window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        const afterEscapeState = {
          hidden: drawer.hidden,
          classList: Array.from(drawer.classList)
        };
        
        // Open again
        agentCard.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const reOpened = !drawer.hidden;
        
        // Close via close button click
        drawer.querySelector('#jrDrawerClose')?.click();
        const afterBtnClickState = {
          hidden: drawer.hidden,
          classList: Array.from(drawer.classList)
        };

        // Open again
        agentCard.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        
        // Close via tab edge button
        drawer.querySelector('#jrDrawerTab')?.click();
        const afterTabClickState = {
          hidden: drawer.hidden,
          classList: Array.from(drawer.classList)
        };
        
        // Open again, then click the same agent node to toggle off
        agentCard.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const openedForToggle = !drawer.hidden;
        agentCard.dispatchEvent(new MouseEvent('click', { bubbles: true }));
        const afterToggleClickState = {
          hidden: drawer.hidden
        };

        return {
          openedState,
          afterEscapeState,
          reOpened,
          afterBtnClickState,
          afterTabClickState,
          openedForToggle,
          afterToggleClickState
        };
      })()
    `,
    returnByValue: true
  });
  console.log('Drawer Test Result:', JSON.stringify(drawerTest.result.value, null, 2));

  // Screenshot
  const ss = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync('/home/kryazzy/Space/K.R.Y.Z.E.N/mesh_verified.png', Buffer.from(ss.data, 'base64'));
  console.log('Saved mesh_verified.png');

  ws.close();
  chrome.kill();
  process.exit(0);
}

run().catch(e => {
  console.error(e);
  chrome.kill();
  process.exit(1);
});
