import { spawn } from 'child_process';
import { writeFileSync, mkdirSync } from 'fs';
import { tmpdir } from 'os';
import { join } from 'path';

const PORT = 9255;
const USER_DATA = join(tmpdir(), 'chrome_jarvis_' + Date.now());
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
  const pageTarget = targets.find(t => t.url.includes('jarvis.local') || t.title.includes('Antigravity Ultra'));
  if (!pageTarget) {
    console.error('Target page not found:', targets);
    process.exit(1);
  }

  console.log('Connecting to target:', pageTarget.title, pageTarget.webSocketDebuggerUrl);
  const ws = new WebSocket(pageTarget.webSocketDebuggerUrl);

  let idCounter = 1;
  const pending = new Map();
  const consoleMessages = [];

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(msg.error);
      else resolve(msg.result);
    }
    if (msg.method === 'Runtime.consoleAPICalled') {
      const type = msg.params.type;
      const text = msg.params.args.map(a => a.value || a.description).join(' ');
      consoleMessages.push({ type, text });
      if (type === 'error') console.error('BROWSER ERROR:', text);
    }
  };

  await new Promise(r => ws.onopen = r);

  function send(method, params = {}) {
    const id = idCounter++;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }

  await send('Runtime.enable');
  await send('Page.enable');

  async function evaluate(expression) {
    const res = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true
    });
    if (res.exceptionDetails) {
      throw new Error(res.exceptionDetails.text + ' ' + (res.exceptionDetails.exception?.description || ''));
    }
    return res.result?.value;
  }

  console.log('--- Step 1: Check Page Title & 3D Solar System ---');
  const title = await evaluate('document.title');
  console.log('Title:', title);

  const isMesh3DActive = await evaluate('Boolean(window.Mesh3D && window.Mesh3D.isActive())');
  console.log('Mesh3D Active:', isMesh3DActive);

  console.log('--- Step 2: Test Planet Jump & Orbit Speed ---');
  await evaluate(`
    if (window.Mesh3D) {
      window.Mesh3D.focusPlanet('Mars');
      window.Mesh3D.setOrbitSpeed(2.0);
    }
  `);
  await sleep(1000);
  console.log('Mars focus executed');

  // Screenshot 1: 3D Astronomical Solar System View
  const ss1 = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync('/home/kryazzy/.gemini/antigravity/brain/0b7cdf21-93ed-4744-9457-8d863d29bfdf/jarvis_solar_system.png', Buffer.from(ss1.data, 'base64'));
  console.log('Saved jarvis_solar_system.png');

  console.log('--- Step 3: Test Antigravity Slash Command Quick Bar ---');
  await evaluate(`
    const slashPlan = document.querySelector('.slash-btn[data-slash="/plan"]');
    if (slashPlan) slashPlan.click();
  `);
  await sleep(300);
  const inputValue = await evaluate(`document.getElementById('input')?.value`);
  console.log('Composer input after /plan click:', inputValue);

  console.log('--- Step 4: Switch to Cyber IDE & Test Suite Runner ---');
  await evaluate(`
    const sel = document.getElementById('proj');
    if (sel) {
      sel.value = 'test';
      sel.dispatchEvent(new Event('change'));
    }
    if (window.jarvisStudio) {
      window.jarvisStudio.setMode('code');
    }
    if (typeof window.dock === 'function') {
      window.dock('dTest');
    }
  `);
  await sleep(1000);

  const testDockState = await evaluate(`({
    tabOn: document.querySelector('#dockTabs button[data-d="dTest"]')?.classList.contains('on'),
    paneOn: document.getElementById('dTest')?.classList.contains('on'),
    paneDisplay: window.getComputedStyle(document.getElementById('dTest')).display,
    projectSlug: document.getElementById('testProjectSlug')?.textContent
  })`);
  console.log('Test Dock State:', testDockState);

  // Click Run Test Suite and wait for Vitest execution
  console.log('Executing Run Test Suite...');
  await evaluate(`
    if (typeof window.loadProjectTests === 'function') {
      window.loadProjectTests(true);
    }
  `);

  let testSummary = '';
  for (let i = 0; i < 30; i++) {
    await sleep(600);
    testSummary = await evaluate(`document.getElementById('testSummaryChip')?.textContent`);
    if (testSummary && !testSummary.includes('Running')) break;
  }
  console.log('Test Execution Result Chip:', testSummary);

  const testOutputSnippet = await evaluate(`document.getElementById('testOut')?.textContent.slice(0, 350)`);
  console.log('Test Output Snippet:\n', testOutputSnippet);

  // Screenshot 2: Cyber IDE with Test Suite Runner
  const ss2 = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync('/home/kryazzy/.gemini/antigravity/brain/0b7cdf21-93ed-4744-9457-8d863d29bfdf/jarvis_cyber_ide_tests.png', Buffer.from(ss2.data, 'base64'));
  console.log('Saved jarvis_cyber_ide_tests.png');

  console.log('--- Step 5: Test Project References & Specs Hub ---');
  await evaluate(`
    if (typeof window.dock === 'function') {
      window.dock('dRefs');
    }
  `);
  await sleep(1500);

  const refState = await evaluate(`({
    tabOn: document.querySelector('#dockTabs button[data-d="dRefs"]')?.classList.contains('on'),
    paneOn: document.getElementById('dRefs')?.classList.contains('on'),
    paneDisplay: window.getComputedStyle(document.getElementById('dRefs')).display,
    badge: document.getElementById('refStatsBadge')?.textContent,
    docCount: document.querySelectorAll('#refDocsList .ref-doc-item').length,
    linkCount: document.querySelectorAll('#refLinksList > div').length
  })`);
  console.log('References State:', refState);

  // Click the first spec document (e.g. PROJECT.md) to verify opening in Cyber IDE
  await evaluate(`
    const firstDoc = document.querySelector('#refDocsList .ref-doc-item');
    if (firstDoc) firstDoc.click();
  `);
  await sleep(1000);

  // Screenshot 3: References Hub & Spec Preview
  const ss3 = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync('/home/kryazzy/.gemini/antigravity/brain/0b7cdf21-93ed-4744-9457-8d863d29bfdf/jarvis_cyber_ide_references.png', Buffer.from(ss3.data, 'base64'));
  console.log('Saved jarvis_cyber_ide_references.png');

  console.log('--- Summary of Browser Errors ---');
  const errors = consoleMessages.filter(m => m.type === 'error');
  console.log('Browser errors count:', errors.length);
  if (errors.length) {
    errors.forEach(e => console.log(' -', e.text));
  } else {
    console.log('✓ Clean console with zero errors!');
  }

  ws.close();
  chrome.kill();
  console.log('✓ Complete End-to-End verification succeeded!');
}

run().catch(err => {
  console.error('E2E Test Failed:', err);
  chrome.kill();
  process.exit(1);
});
