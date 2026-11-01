/* Disposable fixture only: real scheduler + fake streams, no provider calls. */
(async()=>{
  if(!(await fetch('/api/fixture').then(r=>r.json())).fixture)throw Error('Fixture required');
  const q=s=>document.querySelector(s),pause=ms=>new Promise(r=>setTimeout(r,ms)),check=(v,m)=>{if(!v)throw Error(m);};
  async function wait(fn,message){for(let i=0;i<400;i++){if(fn())return;await pause(25);}throw Error(message);}
  await wait(()=>q('#proj').options.length,'Project list failed');
  switchProject('example-project');jarvisStudio.setMode('mesh',false);await pause(100);
  q('#newBtn').click();await send('parallel demo',{project:'example-project'});
  await wait(()=>!runBusy&&!sending,'Parallel fixture did not finish');
  await jarvisExecution.refresh();
  check(jarvisExecution.state.nodes.length===3,'Saved graph lost task nodes');
  check(jarvisExecution.state.nodes.every(n=>['completed','reused'].includes(n.state)),'Task graph did not complete');
  check(q('#pExecution').classList.contains('on'),'Live graph did not open the Tasks pane');
  const first=await api('/api/execution?slug=example-project');
  const records=Object.values(first.tasks);
  check(records.length===3&&records.every(n=>n.checkpoint?.path),'Per-task history checkpoints missing');
  const run=first.runs.at(-1),a=first.tasks[run.nodes.find(n=>n.id==='A').key],b=first.tasks[run.nodes.find(n=>n.id==='B').key],c=first.tasks[run.nodes.find(n=>n.id==='C').key];
  check(c.started>=Math.max(a.finished,b.finished),'Dependent task started before both parents joined');
  check(a.started<b.finished&&b.started<a.finished,'Independent tasks did not overlap');
  jarvisExecution.open();await pause(100);
  check(q('.execution-dialog').open,'Full dependency view did not open');
  await wait(()=>q('.execution-dialog .execution-edges path')&&q('.execution-dialog').textContent.includes('After A + B'),'Dependency edges or labels are absent');
  q('.execution-dialog').close();
  const starts=records.map(n=>n.started);
  await send('parallel demo',{project:'example-project'});await wait(()=>!runBusy&&!sending,'Saved continuation did not finish');await jarvisExecution.refresh();
  check(jarvisExecution.state.nodes.every(n=>n.state==='reused'),'Continue repeated completed tasks instead of using saved results');
  const second=await api('/api/execution?slug=example-project');
  check(Object.values(second.tasks).every((n,i)=>n.started===starts[i]),'Saved completed tasks were re-started');
  check(document.documentElement.scrollWidth<=innerWidth+1,'Task graph overflows the page');
  return{ok:true,passed:6,checks:['independent lanes overlap','dependent source task waits for parents','each agent has a durable tool checkpoint','full dependency graph shows edges and ownership','repeat uses saved results without new work','task pane fits the viewport']};
})()
