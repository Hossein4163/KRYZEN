(async () => {
  const fixture = await fetch('/api/fixture').then(r=>r.json());
  if (!fixture.fixture) throw new Error('Refusing to mutate a non-fixture workspace');
  const checks = [], q = s=>document.querySelector(s), pause=ms=>new Promise(r=>setTimeout(r,ms));
  const check=(v,m)=>{if(!v)throw new Error(m);};
  async function wait(fn,message){for(let i=0;i<100;i++){if(fn())return;await pause(50);}throw new Error(message);}
  const originalConfirm=window.confirm, originalFetch=window.fetch;
  const requests=[];
  window.fetch=async (...args)=>{if(args[1]?.method==='POST')requests.push({url:args[0],body:JSON.parse(args[1].body)});return originalFetch(...args);};
  const type=(id,text)=>{q(id).value=text;q(id).dispatchEvent(new Event('input',{bubbles:true}));};
  try {
    await wait(()=>!runBusy&&!sending,'Previous run did not stop');
    jarvisStudio.setMode('mesh',false);
    q('#newProjectBtn').click();
    check(q('#newProjectDialog').open&&document.activeElement.id==='npTitle','Project dialog did not take focus');
    check(!q('#npStart').checked,'Creation must not start a model run by default');
    q('#newProjectForm').requestSubmit();await pause(70);
    check(!requests.some(r=>r.url==='/api/form/project'),'Invalid form sent a create request');
    type('#npTitle','Growth Project');check(q('#npSlug').value==='growth-project','Title did not fill slug');
    type('#npSlug','custom-project');type('#npTitle','New title');check(q('#npSlug').value==='custom-project','Edited slug was overwritten');
    q('#npCancel').click();await wait(()=>!q('#newProjectDialog'),'Cancel did not close dialog');check(document.activeElement.id==='newProjectBtn','Dialog did not restore focus');
    checks.push('new project dialog validates inputs, preserves custom slug and restores focus');

    q('#newProjectBtn').click();type('#npTitle','Existing');type('#npSlug','example-project');type('#npGoal','Keep this input');
    q('#newProjectForm').requestSubmit();await wait(()=>q('#npError').textContent,'Duplicate project was not rejected');
    check(q('#npGoal').value==='Keep this input'&&q('#newProjectDialog').open,'Create failure lost form input');
    q('#npCancel').click();await wait(()=>!q('#newProjectDialog'),'Cancel did not close dialog');checks.push('duplicate project creation preserves existing project and user input');

    switchProject('example-project');jarvisStudio.setMode('code',false);
    await wait(()=>CW.files.includes('src/example.txt'),'Code did not load');await cwOpen('src/example.txt');
    cwCode.value='Unsaved before creation';cwCode.dispatchEvent(new Event('input'));
    q('#newProjectBtn').click();type('#npTitle','Growth Project');
    const before=requests.length;window.confirm=()=>false;q('#newProjectForm').requestSubmit();await pause(80);
    check(requests.length===before&&codeDirty(),'Cancelled discard still created a project or lost code');
    window.confirm=()=>true;
    const priorSessions=(await api('/api/sessions')).sessions.length;
    q('#newProjectForm').requestSubmit();q('#newProjectForm').requestSubmit();
    await wait(()=>!q('#newProjectDialog'),'Project creation did not finish');
    check(q('#proj').value==='growth-project'&&!codeDirty(),'Created project was not selected or dirty buffers remain');
    check((await api('/api/sessions')).sessions.length===priorSessions,'Create-only unexpectedly started a model run');
    check(requests.filter(r=>r.url==='/api/form/project'&&r.body.slug==='growth-project').length===1,'Duplicate submit created multiple requests');
    checks.push('dirty code cancellation, duplicate submission guard and create-only project selection work');

    const created=await api('/api/project?slug=growth-project');
    check(created.project==='growth-project'&&created.continuation?.action,'New project has no resume context');
    check((await api('/api/projects')).folders.includes('growth-project'),'New project was not registered');
    checks.push('created workspace is registered and exposes structured continuation');

    q('#newProjectBtn').click();type('#npTitle','Started Project');type('#npGoal','Build a disposable app');q('#npStart').checked=true;
    q('#newProjectForm').requestSubmit();await wait(()=>requests.some(r=>r.url==='/api/chat'&&r.body.project==='started-project'),'Intake did not target newly created project');
    await wait(()=>!runBusy&&!sending,'Intake did not finish');
    const current=await api('/api/session?id='+sessionId);
    check(current.project==='started-project'&&q('#proj').value==='started-project','Intake leaked into old project');
    await wait(()=>q('.user-avatar')?.complete&&q('.user-avatar').naturalWidth>0,'Local Blobatar did not render');
    checks.push('optional intake runs in the new project and local Blobatar renders');

    switchProject('growth-project');
    const resumed=await continueProject('growth-project');check(!resumed.error&&resumed.project==='growth-project','Continue was not scoped to requested project');
    check(requests.some(r=>r.url==='/api/continue'&&r.body.project==='growth-project'),'Continue did not use dedicated endpoint');
    await wait(()=>!runBusy&&!sending,'Continuation did not finish');
    check((await api('/api/session?id='+sessionId)).project==='growth-project','Continuation session used the wrong project');
    checks.push('continuation starts a project-scoped chat through the resume endpoint');

    jarvisStudio.setMode('plan',false);
    await wait(()=>q('#planContinue')&&!q('#planContinue').disabled,'Plan controls did not load');
    const count=requests.filter(r=>r.url==='/api/continue').length;q('#planContinue').click();
    await wait(()=>requests.filter(r=>r.url==='/api/continue').length>count,'Plan Continue bypassed resume endpoint');
    await wait(()=>!runBusy&&!sending,'Plan continuation did not finish');
    checks.push('Plan Continue uses the same resumable project workflow');

    const mesh=await api('/api/mesh');
    check(['Marketing','Product','Content','SEO','Operations'].every(label=>mesh.agents.some(a=>a.label===label)),'Specialists are missing');
    checks.push('all five project specialists are available in agent controls');
    return {ok:true,passed:checks.length,checks};
  } finally {window.confirm=originalConfirm;window.fetch=originalFetch;}
})()
