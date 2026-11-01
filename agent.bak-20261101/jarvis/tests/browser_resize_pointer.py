"""Verify native browser pointer dragging and persisted panel sizes on an open fixture page.
Usage: python3 browser_resize_pointer.py <agent-browser-session>
"""
import json
import subprocess
import sys

session=sys.argv[1]
def run(*args):
    value=json.loads(subprocess.check_output(['agent-browser','--session',session,'--json',*args],text=True))
    if not value['success']: raise RuntimeError(value)
    return value.get('data',{})
def evaluate(script):return run('eval',script).get('result')
assert evaluate("fetch('/api/fixture').then(r=>r.json()).then(d=>d.fixture)") is True
run('set','viewport','1440','1000')
evaluate("chatCollapsed=sideCollapsed=false;applyLayoutCollapses();jarvisStudio.setMode('mesh',false);new Promise(r=>setTimeout(r,200))")
results={}
for name,delta in [('chat',50),('side',-40)]:
    initial=evaluate("(()=>{const h=document.getElementById('"+name+"PanelResize'),r=h.getBoundingClientRect(),p=document.getElementById('"+('chatPanel' if name=='chat' else 'sidePanel')+"').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+100,width:p.width}})()")
    run('mouse','move',str(round(initial['x'])),str(round(initial['y'])))
    run('mouse','down')
    run('mouse','move',str(round(initial['x']+delta)),str(round(initial['y'])),'--steps','10')
    run('mouse','up')
    width=evaluate("document.getElementById('"+('chatPanel' if name=='chat' else 'sidePanel')+"').getBoundingClientRect().width")
    assert abs(width-initial['width']-abs(delta))<2,(name,initial,width)
    results[name]=width
run('reload')
evaluate("new Promise(r=>setTimeout(r,250))")
for name,expected in results.items():
    actual=evaluate("document.getElementById('"+('chatPanel' if name=='chat' else 'sidePanel')+"').getBoundingClientRect().width")
    assert abs(actual-expected)<2,(name,actual,expected)
print(json.dumps({'ok':True,'checks':['pointer drag resizes both side panels','both panel widths survive reload'],'widths':results}))
