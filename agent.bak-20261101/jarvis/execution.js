/* Saved task dependencies and paced request progress; rendering never starts a run. */
(() => {
  'use strict';
  const panel=document.getElementById('executionPanel');
  const state={slug:'',run:null,nodes:[],requests:{active:0,queued:0,limit:2},error:'',loading:false};
  const labels={waiting:'Waiting',running:'Running',completed:'Completed',reused:'Saved result',blocked:'Blocked',failed:'Failed',review_required:'Source review',interrupted:'Interrupted'};
  let sequence=0,dialog=null,timer=null;
  const selected=()=>document.getElementById('proj').value;
  function graphMarkup(expanded=false){
    const nodes=state.nodes;
    const count=name=>nodes.filter(n=>n.state===name).length;
    const header=`<div class="execution-heading"><div><span class="studio-eyebrow">PROJECT EXECUTION</span><h3>Parallel work</h3></div><button class="btn" data-execution-open>${expanded?'Close':'Expand'}</button></div>`;
    const queue=`<div class="request-meter" role="status"><span><i></i>${state.requests.active||0} / ${state.requests.limit||2} model requests</span><span>${state.requests.queued||0} queued${state.requests.cooldown_seconds?' · retry cooldown '+state.requests.cooldown_seconds+'s':''}</span></div>`;
    if(state.error)return header+queue+`<div class="execution-empty" role="alert">${esc(state.error)}<button class="btn" data-execution-refresh>Try again</button></div>`;
    if(!nodes.length)return header+queue+`<div class="execution-empty"><strong>${state.loading?'Opening saved work…':'A clear path through your project.'}</strong><p>Independent tasks run in parallel. Dependencies join before the next step. Completed results and source checkpoints stay with the project.</p><span>${state.slug?'No task graph has been scheduled in this project yet.':'Select a project to see its saved work.'}</span></div>`;
    const summary=`<div class="execution-counts"><span>${count('running')} running</span><span>${count('waiting')} waiting</span><span>${count('completed')+count('reused')} complete</span></div>`;
    const byId=new Map(nodes.map(n=>[n.id,n]));
    function level(node,seen=new Set()){
      if(seen.has(node.id))return 0;seen.add(node.id);
      return Math.min(12,Math.max(-1,...(node.depends_on||[]).map(id=>byId.has(id)?level(byId.get(id),new Set(seen)): -1))+1);
    }
    const levels=nodes.map(n=>level(n)),columns=Array.from({length:Math.max(...levels)+1},(_,i)=>nodes.filter((n,k)=>levels[k]===i));
    const cards=columns.map((group,i)=>`<div class="execution-column"><div class="execution-phase">${i===0?'Independent branches':'After dependencies'}</div>${group.map(n=>{
      const elapsed=n.started?Math.max(0,Math.round(((n.finished||Date.now()/1000)-n.started))):0;
      return `<article class="execution-node state-${esc(n.state)}" data-execution-node="${esc(n.id)}"><header><strong>${esc(n.id)}</strong><span class="execution-badge">${esc(labels[n.state]||n.state)}</span></header><h4>${esc(short(n.agent||''))}</h4><p>${esc(n.task||'')}</p>${n.depends_on?.length?`<div class="execution-dependencies">After ${n.depends_on.map(id=>esc(id)).join(' + ')}</div>`:''}<div class="execution-sources">${(n.files||[]).map(f=>`<code>${esc(f)}</code>`).join('')||'<span>Read-only / research</span>'}</div>${n.started?`<small>${elapsed}s · ${n.finished?'finished':'elapsed'}</small>`:''}${n.error?`<p class="execution-error">${esc(n.error)}</p>`:''}${n.result?`<details><summary>Saved handoff</summary><pre>${esc(n.result)}</pre></details>`:''}${n.checkpoint?.path?'<small>Tool history checkpoint saved</small>':''}</article>`;
    }).join('')}</div>`).join('');
    return header+queue+summary+`<div class="execution-run-label">Run ${esc(state.run?.id||'')} · ${esc(state.run?.state||'')}</div><div class="execution-scroll" tabindex="0" aria-label="Task dependency graph; scroll horizontally to follow dependencies"><svg class="execution-edges" aria-hidden="true"></svg><div class="execution-columns">${cards}</div></div><div class="execution-note">3 task lanes · 2 model streams · paced request starts<br>Source conflicts wait. Build and QA verification follow the join.</div>`;
  }
  function draw(root){
    const scroll=root.querySelector('.execution-scroll'),svg=root.querySelector('.execution-edges');if(!scroll||!svg)return;
    const columns=root.querySelector('.execution-columns'),base=columns.getBoundingClientRect();
    svg.setAttribute('width',String(columns.scrollWidth));svg.setAttribute('height',String(columns.scrollHeight));
    const elements=new Map([...root.querySelectorAll('[data-execution-node]')].map(el=>[el.dataset.executionNode,el]));
    svg.innerHTML=state.nodes.flatMap(n=>(n.depends_on||[]).map(id=>{
      const from=elements.get(id),to=elements.get(n.id);if(!from||!to)return '';
      const a=from.getBoundingClientRect(),b=to.getBoundingClientRect(),x1=a.right-base.left,y1=a.top+a.height/2-base.top,x2=b.left-base.left,y2=b.top+b.height/2-base.top;
      return `<path d="M${x1},${y1} C${(x1+x2)/2},${y1} ${(x1+x2)/2},${y2} ${x2},${y2}"/><circle cx="${x2}" cy="${y2}" r="3"/>`;
    })).join('');
  }
  function render(){
    const active=state.nodes.filter(n=>n.state==='running').length;document.getElementById('executionBtn').textContent='Tasks'+(active?' · '+active:'');
    const roots=[panel,...(dialog?[dialog.querySelector('.execution-dialog-body')]:[])];
    for(const root of roots){if(!root)continue;const scroll=root.querySelector('.execution-scroll'),x=scroll?.scrollLeft||0,y=scroll?.scrollTop||0,opened=new Set([...root.querySelectorAll('.execution-node:has(details[open])')].map(n=>n.dataset.executionNode));root.innerHTML=graphMarkup(root!==panel);
      root.querySelector('[data-execution-open]')?.addEventListener('click',()=>root===panel?openDialog():dialog.close());
      root.querySelector('[data-execution-refresh]')?.addEventListener('click',refresh);
      if(root.querySelector('.execution-scroll')){root.querySelector('.execution-scroll').scrollLeft=x;root.querySelector('.execution-scroll').scrollTop=y;}root.querySelectorAll('.execution-node').forEach(n=>{if(opened.has(n.dataset.executionNode)&&n.querySelector('details'))n.querySelector('details').open=true;});
      requestAnimationFrame(()=>draw(root));}
  }
  function openDialog(){
    if(dialog){dialog.focus();return;}
    dialog=document.createElement('dialog');dialog.className='execution-dialog';dialog.setAttribute('aria-label','Parallel task dependencies and saved progress');
    dialog.innerHTML='<div class="execution-dialog-body"></div>';document.body.appendChild(dialog);
    dialog.addEventListener('close',()=>{dialog.remove();dialog=null;document.getElementById('executionTab').focus();},{once:true});dialog.showModal();render();refresh();
  }
  async function refresh(){
    const slug=selected(),request=++sequence;
    if(slug!==state.slug){state.slug=slug;state.run=null;state.nodes=[];state.error='';}
    if(!slug){render();return;}
    state.loading=true;render();
    try{
      const response=await fetch('/api/execution?slug='+encodeURIComponent(slug));const data=await response.json();
      if(request!==sequence||slug!==selected())return;
      if(!response.ok||data.error)throw Error(data.error||'Saved execution could not load');
      state.run=(data.runs||[]).at(-1)||null;state.requests=data.requests||state.requests;
      state.nodes=(state.run?.nodes||[]).map(n=>({...data.tasks[n.key],...n,state:n.state||data.tasks[n.key]?.state||'waiting'}));state.error='';
    }catch(e){if(request===sequence)state.error=e.message;}
    finally{if(request===sequence){state.loading=false;render();}}
  }
  window.addEventListener('jarvis:execution',event=>{
    const ev=event.detail;if(selected()!==state.slug){refresh();return;}
    if(ev.type==='request_state'){state.requests={...state.requests,...ev};render();return;}
    if(ev.type==='parallel_run'){
      state.run={id:ev.run_id,state:ev.state};if(ev.nodes){state.nodes=ev.nodes;if(!document.body.matches('.studio-mode,.code-mode,.control-mode'))document.getElementById('executionTab').click();}
      if(ev.state!=='running')refresh();else render();
    }else if(ev.type==='task_state'){
      if(state.run?.id!==ev.run_id){refresh();return;}
      const node=state.nodes.find(n=>n.id===ev.id);if(node)Object.assign(node,ev);else refresh();render();
    }
  });
  document.getElementById('executionTab').addEventListener('click',refresh);
  document.getElementById('executionBtn').addEventListener('click',openDialog);
  document.getElementById('proj').addEventListener('change',refresh);
  window.addEventListener('jarvis:projects-ready',refresh);
  addEventListener('resize',()=>{draw(panel);if(dialog)draw(dialog);});
  timer=setInterval(()=>{if(!document.hidden&&(dialog||document.getElementById('pExecution').classList.contains('on')))refresh();},4000);
  addEventListener('pagehide',()=>clearInterval(timer));
  window.jarvisExecution={refresh,open:openDialog,state};render();if(selected())refresh();
})();
