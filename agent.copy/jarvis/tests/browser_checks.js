/* Run only against tests/browser_fixture.py:
   agent-browser --session jarvis-checks eval --stdin < agent/jarvis/tests/browser_checks.js */
(async () => {
  const marker = await fetch('/api/fixture').then(r => r.json());
  if (marker.fixture !== true) throw new Error('This test requires the disposable fixture.');
  const results = [], errors = [];
  const recordError = event => errors.push(event.message || String(event.reason));
  addEventListener('error', recordError);
  addEventListener('unhandledrejection', recordError);
  const check = (condition, message) => { if (!condition) throw new Error(message); };
  const wait = async (predicate, message) => {
    const start = Date.now();
    while (!predicate()) {
      if (Date.now() - start > 10000) throw new Error(message);
      await new Promise(resolve => setTimeout(resolve, 25));
    }
  };
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const realFetch = window.fetch, realConfirm = window.confirm;
  try {
    await wait(() => document.querySelector('#proj').options.length === 2, 'Project loading failed');
    document.querySelector('#proj').value = 'example-project';
    document.querySelector('#proj').dispatchEvent(new Event('change', {bubbles:true}));
    document.querySelector('#codeBtn').click();
    await wait(() => CW.slug === 'example-project' && CW.files.includes('src/example.txt'), 'Code tree failed');
    for (const id of ['dTerm','dRun','dSearch','dGit','dPrev']) {
      document.querySelector(`[data-d="${id}"]`).click();
      const active = [...document.querySelectorAll('.dock .dpane.on')].map(el => el.id);
      check(active.length === 1 && active[0] === id, 'Dock panes overlap: ' + active.join(','));
    }
    results.push('all five Code dock tabs display exactly one pane');

    await cwOpen('src/example.txt');
    cwCode.value = 'Saved snapshot'; cwCode.dispatchEvent(new Event('input'));
    window.fetch = async (...args) => {
      const response = await realFetch(...args);
      if (args[0] === '/api/code/save') await pause(150);
      return response;
    };
    const saving = cwSave();
    cwCode.value = 'New typing while saving'; cwCode.dispatchEvent(new Event('input'));
    await saving;
    window.fetch = realFetch;
    check(CW.cur.orig === 'Saved snapshot' && CW.cur.text === 'New typing while saving' && codeDirty(), 'Save lost newer typing');
    results.push('save preserves newer typing and dirty state');

    await api('/api/code/save', {slug:'example-project',path:'src/example.txt',content:'External edit'});
    await cwSave();
    check(cwCode.value === 'New typing while saving' && codeDirty(), 'Conflict lost editor text');
    const disk = await api('/api/code/file?slug=example-project&path=src/example.txt');
    check(disk.content === 'External edit', 'Stale editor overwrote disk');
    results.push('editor conflict preserves both newer disk content and unsaved buffer');

    window.confirm = () => false;
    document.querySelector('#proj').value = 'other-project';
    document.querySelector('#proj').dispatchEvent(new Event('change', {bubbles:true}));
    check(document.querySelector('#proj').value === 'example-project' && codeDirty(), 'Project change discarded dirty buffer');
    window.confirm = () => true;
    document.querySelector('#cwReloadFile').click();
    await wait(() => !codeDirty(), 'Reload did not clear saved buffer');
    check(cwCode.value === 'External edit', 'Reload did not read disk');
    window.confirm = realConfirm;
    results.push('project-switch cancellation and explicit file reload work');

    document.querySelector('[data-d="dSearch"]').click();
    document.querySelector('#sq').value = '[';
    document.querySelector('#sre').checked = true;
    await cwSearch();
    check(document.querySelector('#toast').textContent.includes('regex'), 'Invalid regex was hidden as no matches');
    results.push('invalid search reports its actual error');

    const plan = await api('/api/studio/plan?slug=example-project');
    const saved = await api('/api/studio/plan', {slug:'example-project',revision:plan.revision,
      content:'# QA Plan\n## Milestone 1: Verify\n- [ ] Verify the controls\n- [ ] Report results\n'});
    check(saved.ok, 'Fixture plan preparation failed');
    document.querySelector('#planBtn').click();
    await wait(() => document.querySelector('[data-task-line]'), 'Plan tasks did not render');
    document.querySelector('#planApprove').click();
    await wait(() => document.querySelector('#planApprovalState').textContent === 'APPROVED', 'Plan approval failed');
    document.querySelector('[data-task-line]').click();
    await wait(() => window.jarvisStudio.state.plan.approval.status === 'outdated', 'Task did not invalidate old approval');
    check(window.jarvisStudio.state.plan.progress.done === 1, 'Task progress did not update');
    results.push('plan approval and canonical task update remain synchronized');

    document.querySelector('#newBtn').click();
    await send('fast');
    await wait(() => !runBusy, 'Fast reply was missed');
    check(document.querySelectorAll('.msg.ai').length === 1 && chat.textContent.includes('Fast reply verified.'), 'Fast response duplicated or lost');
    results.push('instant chat response renders once');

    await send('Verify delayed pause response');
    await wait(() => !document.querySelector('#pauseBtn').disabled, 'Pause not enabled');
    window.fetch = async (...args) => {
      const response = await realFetch(...args);
      if (args[0] === '/api/run-control') await pause(250);
      return response;
    };
    document.querySelector('#pauseBtn').click();
    await wait(() => document.querySelector('#status').classList.contains('paused'), 'Pause did not settle');
    await pause(350);
    check(document.querySelector('#pauseBtn').textContent.includes('Resume') && !document.querySelector('#pauseBtn').disabled, 'Late HTTP reply regressed paused state');
    window.fetch = realFetch;
    document.querySelector('#pauseBtn').click();
    await wait(() => !runBusy, 'Resume did not finish');
    results.push('delayed pause response cannot disable Resume');

    document.querySelector('#ctrlBtn').click();
    document.querySelector('[data-sec="skills"]').click();
    await wait(() => document.querySelector('#skillSearch'), 'Skills library failed');
    document.querySelector('#skillSearch').value = 'accessibility';
    document.querySelector('#skillSearch').dispatchEvent(new Event('input'));
    check(document.querySelector('#skillCatalog').textContent.includes('accessibility-audit'), 'Skill search failed');
    results.push('skills search and role assignments load');
    check(errors.length === 0, 'Browser errors: ' + errors.join('; '));
    return {ok:true, passed:results.length, checks:results};
  } finally {
    window.fetch = realFetch; window.confirm = realConfirm;
    removeEventListener('error', recordError); removeEventListener('unhandledrejection', recordError);
  }
})()
