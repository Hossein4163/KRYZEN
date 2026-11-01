/* VS Code-inspired workbench checks: disposable browser_fixture.py only. */
(async()=>{
  if(!(await fetch('/api/fixture').then(r=>r.json())).fixture)throw new Error('Fixture required');
  const q=s=>document.querySelector(s),checks=[],pause=ms=>new Promise(r=>setTimeout(r,ms));
  const check=(v,m)=>{if(!v)throw new Error(m);};
  async function wait(fn,m){for(let i=0;i<300;i++){if(fn())return;await pause(25);}throw new Error(m);}
  await wait(()=>window.jarvisStudio&&q('#proj').options.length,'Startup did not finish');
  switchProject('example-project');jarvisStudio.setMode('code',false);
  await wait(()=>CW.slug==='example-project'&&CW.files.includes('assets/sample.png'),'Explorer failed to load');
  const rows=()=>[...q('#cwTree').querySelectorAll('[data-p]')];
  const paths=rows().map(row=>row.dataset.p);
  check(paths.indexOf('src/')<paths.indexOf('src/components/'),'Explorer places a child before its parent');
  const sourceFolder=rows().find(row=>row.dataset.p==='src/');sourceFolder.focus();
  sourceFolder.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));
  check(!rows().some(row=>row.dataset.p==='src/components/'),'Explorer folder did not collapse by keyboard');
  q('#cwTree [data-p="src/"]').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
  check(rows().some(row=>row.dataset.p==='src/components/'),'Explorer folder did not expand by keyboard');
  q('#cwExplorerToggle').click();check(q('#codews').classList.contains('cw-explorer-collapsed'),'Explorer toggle did not collapse');
  q('#cwExplorerToggle').click();check(!q('#codews').classList.contains('cw-explorer-collapsed'),'Explorer toggle did not restore');
  checks.push('Explorer sorts parents first and supports keyboard collapse and the sidebar toggle');
  await cwOpen('src/components/app.js');
  await wait(()=>q('#cwHighlight')?.querySelector('.hljs-keyword'),'JavaScript syntax colors did not render');
  check(cwCode.value.includes('export function greet'),'Syntax coloring changed source content');
  check(!window.__codeExecuted&&!q('#cwHighlight script'),'Source HTML executed or was inserted as markup');
  check(q('#cwLanguage')&&q('#cwCursor'),'Editor language/cursor status is missing');
  checks.push('local JavaScript syntax coloring preserves source and escapes embedded HTML');

  cwCode.focus();cwCode.setSelectionRange(7,7);cwCode.dispatchEvent(new Event('click'));
  check(q('#cwCursor').textContent.includes('1'),'Cursor status did not expose line information');
  cwCode.value+='\n// Keep my unsaved draft\n';cwCode.dispatchEvent(new Event('input'));
  const draft=cwCode.value;
  await cwOpen('config.json');await wait(()=>q('#cwHighlight')?.querySelector('.hljs-attr'),'JSON syntax colors did not render');
  await cwOpen('src/components/app.js');check(cwCode.value===draft&&codeDirty(),'Tab switch lost dirty source');
  checks.push('language changes and text tab switching preserve unsaved drafts');

  q('#cwQuickOpen').click();await wait(()=>q('#cwQuickDialog')?.open,'Quick Open did not open');
  q('#cwQuickInput').value='styles.css';q('#cwQuickInput').dispatchEvent(new Event('input'));
  await wait(()=>q('#cwQuickList').textContent.includes('styles.css'),'Quick Open did not filter paths');
  q('#cwQuickInput').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
  await wait(()=>CW.cur?.path==='src/styles.css'&&!q('#cwQuickDialog')?.open,'Quick Open selection did not open the file');
  checks.push('Quick Open filters paths and opens the keyboard-selected file');

  await cwOpen('assets/sample.png');
  await wait(()=>q('#cwImage')?.complete&&q('#cwImage').naturalWidth===256&&!q('#cwImage').hidden&&q('#cwImageMeta').textContent.includes('256'),'PNG did not decode');
  check(CW.cur.kind==='image'&&q('#cwSave').disabled,'Image is editable through the text save action');
  check(q('#cwImage').naturalHeight===160&&q('#cwImageMeta').textContent.includes('256'),'Image dimensions are missing');
  check(!q('#cwImageView').hidden,'Image viewer is hidden');
  q('#cwImageActual').click();check(q('#cwImageZoom').textContent==='100%'&&q('#cwImage').style.width==='256px','Actual-size image control failed');
  q('#cwImagePlus').click();check(q('#cwImageZoom').textContent==='125%'&&q('#cwImage').style.width==='320px','Image zoom-in control failed');
  q('#cwImageMinus').click();check(q('#cwImageZoom').textContent==='100%','Image zoom-out control failed');
  q('#cwImageFit').click();check(q('#cwImageZoom').textContent==='Fit'&&q('#cwImage').classList.contains('fit'),'Fit image control failed');
  const originalFetch=window.fetch;let savedImage=false;
  window.fetch=async(...args)=>{if(args[0]==='/api/code/save')savedImage=true;return originalFetch(...args);};
  try{await cwSave();}finally{window.fetch=originalFetch;}
  check(!savedImage,'Image Save invoked the text save endpoint');
  await cwOpen('src/components/app.js');check(cwCode.value===draft&&codeDirty(),'Image navigation lost dirty code');
  checks.push('PNG preview shows dimensions and cannot overwrite binary files or dirty code');

  await cwOpen('assets/large.png');
  await wait(()=>q('#cwImage')?.complete&&q('#cwImage').naturalWidth===512,'Multi-chunk image failed');
  check(q('#cwImage').naturalHeight===512,'Large image dimensions are wrong');
  checks.push('binary preview assembles images larger than a single API/cache chunk');

  await cwOpen("assets/it's a test $(touch INJECTED).png");
  await wait(()=>q('#cwImage')?.complete&&q('#cwImage').naturalWidth===256,'Quoted filename did not preview');
  checks.push('quoted filenames and shell-like text are treated as literal image paths');

  await cwOpen('assets/vector.svg');
  await wait(()=>q('#cwImage')?.complete&&q('#cwImage').naturalWidth===240,'SVG did not preview');
  check(!window.__svgExecuted&&!q('#cwImageView script')&&!q('#cwImageView iframe')&&!q('#cwImageView object'),'SVG escaped image-only rendering');
  check(q('#cwImage').src.startsWith('blob:'),'Image preview is not isolated in a Blob URL');
  checks.push('SVG renders as an inert image without inline script execution');

  const released=CW.cur,blob=released.url,realRevoke=URL.revokeObjectURL;let revoked=false;
  URL.revokeObjectURL=url=>{if(url===blob)revoked=true;return realRevoke.call(URL,url);};
  try{q(`#cwTabs i[data-x="${CW.open.indexOf(released)}"]`).click();}finally{URL.revokeObjectURL=realRevoke;}
  check(revoked&&!released.url&&!CW.open.includes(released),'Closing an image did not release its Blob URL');
  checks.push('closing an image releases its Blob URL');

  await cwOpen('assets/corrupt.png');
  await wait(()=>q('#cwImageStatus').textContent.toLowerCase().match(/error|cannot|could not|failed|invalid|unable|unsupported|corrupt/),'Corrupt image failure is hidden');
  await cwOpen('assets/oversize.png');
  await wait(()=>q('#cwImageStatus').textContent.toLowerCase().match(/large|limit|8\s*m/),'Oversized image limit is not visible');
  await cwOpen('assets/outside.png');
  await wait(()=>q('#cwImageStatus').textContent.toLowerCase().match(/outside|escape|invalid|project|denied/),'Cross-project symlink was not rejected');
  checks.push('corrupt, oversized and cross-project images fail with useful feedback');

  const realFetch=window.fetch,realConfirm=window.confirm;
  let release;const gate=new Promise(r=>release=r);let waiting=false;
  window.fetch=async(...args)=>{const response=await realFetch(...args);if(String(args[0]).includes('/api/code/file')&&String(args[0]).includes('.jarvis-image-preview')){waiting=true;await gate;}return response;};
  try{
    const loading=cwOpen('assets/race.png');const image=CW.cur;
    await wait(()=>waiting,'Preview did not use temporary chunks');
    window.confirm=()=>true;
    switchProject('other-project');await cwInit();release();await loading;
    await wait(()=>!image.pending,'Stale image did not finish cleanup');
    check(CW.slug==='other-project'&&(!CW.cur||CW.cur.path!=='assets/race.png'),'Stale image response crossed projects');
  }finally{release?.();window.fetch=realFetch;window.confirm=realConfirm;}
  checks.push('project changes cannot install a stale image into the new editor');
  return{ok:true,passed:checks.length,checks};
})()
