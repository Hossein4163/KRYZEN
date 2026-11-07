/* Persistent, bounded panel resizing with pointer and keyboard input. */
(() => {
  'use strict';
  const main=document.querySelector('.main');
  const panels={chat:document.getElementById('chatPanel'),side:document.getElementById('sidePanel')};
  const storageKey='kryzen.panel-sizes.v1';
  const defaults={desktop:{chat:320,side:300},tablet:{chat:240,side:0},phone:{chat:400,side:360}};
  let sizes=JSON.parse(JSON.stringify(defaults));
  try {
    const saved=JSON.parse(localStorage.getItem(storageKey)||'{}');
    for(const mode of Object.keys(defaults)) for(const name of Object.keys(panels)) {
      const n=saved?.[mode]?.[name];if(Number.isFinite(n)&&n>=0&&n<=1200)sizes[mode][name]=n;
    }
  } catch (_) {}
  const handles={};
  let drag=null,frame=0;
  const mode=()=>innerWidth>=1200?'desktop':innerWidth>760?'tablet':'phone';
  const clamp=(n,min,max)=>Math.max(min,Math.min(max,n));
  const visible=el=>!!el.getClientRects().length&&el.getBoundingClientRect().height>0;
  const persist=()=>{try{localStorage.setItem(storageKey,JSON.stringify(sizes));}catch(_) {}};
  function bounds(name) {
    const layout=mode(),style=getComputedStyle(main),padding=parseFloat(style.paddingLeft)+parseFloat(style.paddingRight),gap=parseFloat(style.columnGap)||0;
    if(layout==='phone')return {min:240,max:Math.max(800,innerHeight*1.3),axis:'y'};
    if(layout==='tablet'&&name==='side')return {min:100,max:Math.max(100,main.clientHeight-padding-gap-180),axis:'y'};
    const other=name==='chat'?'side':'chat';
    const reserved=layout==='desktop'&&visible(panels[other])?panels[other].getBoundingClientRect().width:0;
    return {min:200,max:Math.max(200,Math.min(520,main.clientWidth-padding-gap*(layout==='desktop'?2:1)-reserved-320)),axis:'x'};
  }
  function update() {
    const layout=mode(),style=getComputedStyle(main),gap=parseFloat(style.columnGap)||0;
    const available=main.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight);
    if(layout==='desktop') {
      let chat=clamp(sizes.desktop.chat,200,520),side=clamp(sizes.desktop.side,200,520);
      const chatOn=!main.classList.contains('chat-collapsed'),sideOn=!main.classList.contains('side-collapsed')&&visible(panels.side);
      const budget=available-gap*2-320-(chatOn?0:44)-(sideOn?0:44);
      const total=(chatOn?chat:0)+(sideOn?side:0);
      if(total>budget){const shrink=(total-budget)/((chatOn?1:0)+(sideOn?1:0));if(chatOn)chat=Math.max(200,chat-shrink);if(sideOn)side=Math.max(200,side-shrink);}
      main.style.setProperty('--chat-size',chat+'px');main.style.setProperty('--side-size',side+'px');
    } else if(layout==='tablet') {
      main.style.setProperty('--chat-size',clamp(sizes.tablet.chat,200,Math.min(520,available-gap-320))+'px');
      const b=bounds('side');main.style.setProperty('--side-height',clamp(sizes.tablet.side||main.clientHeight*.34,b.min,b.max)+'px');
    } else {
      main.style.setProperty('--chat-height',clamp(sizes.phone.chat,240,Math.max(800,innerHeight*1.3))+'px');
      main.style.setProperty('--side-height',clamp(sizes.phone.side,240,Math.max(800,innerHeight*1.3))+'px');
    }
    position();
  }
  function position() {
    const layout=mode(),root=main.getBoundingClientRect();
    for(const [name,handle] of Object.entries(handles)) {
      const panel=panels[name],collapsed=main.classList.contains(name==='chat'?'chat-collapsed':'side-collapsed');
      handle.hidden=collapsed||!visible(panel);
      if(handle.hidden)continue;
      const r=panel.getBoundingClientRect(),b=bounds(name),vertical=b.axis==='x';
      const x=layout==='desktop'&&name==='side'?r.left-root.left-6:r.right-root.left-6;
      if(vertical)Object.assign(handle.style,{left:(x-1)+'px',top:(r.top-root.top+12)+'px',width:'14px',height:Math.max(44,r.height-24)+'px'});
      else Object.assign(handle.style,{left:(r.left-root.left+12)+'px',top:(layout==='tablet'?r.top-root.top-12:r.bottom-root.top-1)+'px',width:Math.max(44,r.width-24)+'px',height:'14px'});
      handle.setAttribute('aria-orientation',vertical?'vertical':'horizontal');
      handle.setAttribute('aria-valuemin',String(Math.round(b.min)));handle.setAttribute('aria-valuemax',String(Math.round(b.max)));
      handle.setAttribute('aria-valuenow',String(Math.round(vertical?r.width:r.height)));
      handle.setAttribute('aria-valuetext',Math.round(vertical?r.width:r.height)+' pixels '+(vertical?'wide':'high'));
      handle.title='Drag to resize '+(name==='chat'?'chat':'logs and files')+'. Arrow keys to resize; Home/End for limits; double-click to reset.';
    }
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;update();});}
  function setSize(name,value){const b=bounds(name);sizes[mode()][name]=clamp(value,b.min,b.max);update();}
  function end(event,cancel=false) {
    if(!drag)return;
    const current=drag;drag=null;
    if(cancel){sizes[current.mode][current.name]=current.saved;update();}else persist();
    current.handle.classList.remove('dragging');document.body.classList.remove('resizing-panels','resize-rows');
    if(current.handle.hasPointerCapture(current.pointer))current.handle.releasePointerCapture(current.pointer);
  }
  for(const name of Object.keys(panels)) {
    const handle=document.createElement('div');handle.id=name+'PanelResize';handle.className='panel-resizer';handle.tabIndex=0;handle.setAttribute('role','separator');handle.setAttribute('aria-label','Resize '+(name==='chat'?'chat panel':'logs and files panel'));handle.setAttribute('aria-controls',panels[name].id);main.appendChild(handle);handles[name]=handle;
    handle.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;event.preventDefault();
      const b=bounds(name),r=panels[name].getBoundingClientRect();
      drag={name,handle,mode:mode(),axis:b.axis,start:b.axis==='x'?event.clientX:event.clientY,size:b.axis==='x'?r.width:r.height,saved:sizes[mode()][name],pointer:event.pointerId};
      handle.setPointerCapture(event.pointerId);handle.focus({preventScroll:true});handle.classList.add('dragging');document.body.classList.add('resizing-panels');document.body.classList.toggle('resize-rows',b.axis==='y');
    });
    handle.addEventListener('pointermove',event=>{if(!drag||drag.handle!==handle||event.pointerId!==drag.pointer)return;if(mode()!==drag.mode){end(event,true);return;}const coordinate=drag.axis==='x'?event.clientX:event.clientY;const reverse=name==='side'&&mode()!=='phone'?-1:1;setSize(name,drag.size+(coordinate-drag.start)*reverse);});
    handle.addEventListener('pointerup',event=>end(event));handle.addEventListener('pointercancel',event=>end(event,true));handle.addEventListener('lostpointercapture',event=>end(event));
    handle.addEventListener('dblclick',()=>{sizes[mode()][name]=defaults[mode()][name];persist();update();});
    handle.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&drag){event.preventDefault();end(event,true);return;}
      const b=bounds(name),keys=b.axis==='x'?['ArrowLeft','ArrowRight']:['ArrowUp','ArrowDown'];
      if(![...keys,'Home','End'].includes(event.key))return;event.preventDefault();
      const r=panels[name].getBoundingClientRect(),size=b.axis==='x'?r.width:r.height;
      const reverse=name==='side'&&mode()!=='phone'?-1:1,delta=(event.key===keys[0]?-1:1)*(event.shiftKey?40:10)*reverse;
      setSize(name,event.key==='Home'?b.min:event.key==='End'?b.max:size+delta);persist();
    });
  }
  new ResizeObserver(schedule).observe(main);
  for(const panel of Object.values(panels))new ResizeObserver(()=>{if(!drag)schedule();else position();}).observe(panel);
  new MutationObserver(()=>{if(!drag)schedule();}).observe(main,{attributes:true,attributeFilter:['class']});
  new MutationObserver(schedule).observe(document.body,{attributes:true,attributeFilter:['class']});
  addEventListener('resize',()=>{if(drag)end(null,true);schedule();});
  update();
})();
