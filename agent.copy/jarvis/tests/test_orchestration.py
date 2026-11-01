"""Real threads, fake provider/bridge, and disposable durable task graphs."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import engine
from orchestration import RequestGate,TaskLedger

class Bridge:
    def __init__(self,root):self.root=Path(root);self.lock=threading.Lock()
    def __call__(self,path,args):
        p=Path(args['path'])
        with self.lock:
            if path=='/fs/read':
                if not p.exists():return {'error':'FileNotFoundError: No such file'}
                text=p.read_text();return {'content':text,'revision':hashlib.sha256(text.encode()).hexdigest()}
            old=p.read_text() if p.exists() else ''
            if args.get('create_only') and p.exists():return {'error':'conflict'}
            if args.get('expected_revision') and args['expected_revision']!=hashlib.sha256(old.encode()).hexdigest():return {'error':'conflict'}
            content=old+args['content'] if args.get('append') else args['content']
            p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
            return {'revision':hashlib.sha256(content.encode()).hexdigest()}

def node(name,files=None,deps=None):return {'id':name,'agent':'Build','task':'Implement '+name,'depends_on':deps or [],'files':files or [],'reads':[],'revision':'1'}

class GraphTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.bridge=Bridge(self.temp.name);self.ledger=TaskLedger(self.bridge,self.temp.name);self.events=[]
    def run_graph(self,nodes,work):return self.ledger.run(nodes,{'Build'},work,lambda:None,self.events.append)
    def test_independent_branches_really_overlap_and_join_dependencies(self):
        barrier=threading.Barrier(2);finished=set();lock=threading.Lock()
        def work(task,*args):
            if task['id'] in ('A','B'):barrier.wait(2)
            else:self.assertEqual(finished,{'A','B'});self.assertEqual(set(args[2]),{'A','B'})
            with lock:finished.add(task['id'])
            return 'done '+task['id']
        result=self.run_graph([node('A'),node('B'),node('C',deps=['A','B'])],work)
        self.assertEqual(result['state'],'completed')
        self.assertEqual(finished,{'A','B','C'})
    def test_same_source_writes_serialize(self):
        active=0;peak=0;lock=threading.Lock()
        def work(task,*args):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            time.sleep(.04);(Path(self.temp.name)/'shared.py').write_text(task['id'])
            with lock:active-=1
            return 'done'
        self.run_graph([node('A',['shared.py']),node('B',['shared.py'])],work)
        self.assertEqual(peak,1)
        result=self.run_graph([node('A',['shared.py']),node('B',['shared.py'])],lambda *a:self.fail('verified downstream writes should be reusable'))
        self.assertTrue(all(t['state']=='reused' for t in result['tasks']))
    def test_user_edit_during_another_branch_is_not_adopted_as_verified_work(self):
        p=Path(self.temp.name)/'app.py'
        def work(task,*args):
            if task['id']=='A':p.write_text('verified output')
            else:p.write_text('user edit while another task runs')
            return 'done'
        result=self.run_graph([node('A',['app.py']),node('B',deps=['A'])],work)
        self.assertEqual(result['tasks'][0]['state'],'review_required')
        self.assertEqual(p.read_text(),'user edit while another task runs')
    def test_completed_results_survive_reload_without_reexecution(self):
        called=[]
        def work(task,*args):called.append(task['id']);return 'saved result'
        self.run_graph([node('A')],work)
        self.ledger=TaskLedger(self.bridge,self.temp.name)
        result=self.run_graph([node('A')],work)
        self.assertEqual(called,['A']);self.assertEqual(result['tasks'][0]['state'],'reused')
        self.assertEqual(result['tasks'][0]['result'],'saved result')
    def test_source_edits_require_reconciliation_without_overwriting(self):
        def work(task,*args):(Path(self.temp.name)/'app.py').write_text('original');return 'done'
        self.run_graph([node('A',['app.py'])],work)
        (Path(self.temp.name)/'app.py').write_text('user edit')
        result=self.run_graph([node('A',['app.py'])],lambda *a:self.fail('must not repeat edits'))
        self.assertEqual(result['tasks'][0]['state'],'review_required')
        self.assertEqual((Path(self.temp.name)/'app.py').read_text(),'user edit')
    def test_failure_blocks_dependents_and_saves_inflight_checkpoint(self):
        def work(task,key,task_id,parents,ledger):
            ledger.checkpoint(key,[{'role':'tool','tool_call_id':'written','content':'saved'}],1,['unknown-effect'])
            raise RuntimeError('interrupted effect')
        result=self.run_graph([node('A'),node('B',deps=['A'])],work)
        self.assertEqual([t['state'] for t in result['tasks']],['failed','blocked'])
        memory=self.ledger.memory();checkpoint=memory[0]['checkpoint']
        raw=json.loads(Path(checkpoint['path']).read_text())
        self.assertEqual(raw['messages'][0]['tool_call_id'],'written')
        self.assertEqual(raw['pending'],['unknown-effect'])
    def test_invalid_cycles_unknown_agents_and_traversal_do_not_execute(self):
        for graph in ([node('A',deps=['A'])],[{**node('A'),'agent':'unauthorized'}],[node('A',['../outside'])]):
            with self.assertRaises(ValueError):self.run_graph(graph,lambda *a:self.fail('invalid execution'))

class EngineGraphTests(unittest.TestCase):
    def test_real_agent_file_writes_checkpoint_and_reuse(self):
        with tempfile.TemporaryDirectory() as root:
            e=engine.Engine.__new__(engine.Engine)
            e.project_root=root;e.project='example';e.ledger=None;e._context=threading.local()
            e.stop,e.pause_requested,e.paused=threading.Event(),threading.Event(),threading.Event()
            events=[]
            e.emit=lambda ev:events.append({**({'task_id':e._context.task_id} if getattr(e._context,'task_id',None) else {}),**ev})
            bridge=Bridge(root);e.bridge=lambda path,args:json.dumps(bridge(path,args))
            write=engine.Tool('write','Write','','bridge',path='/fs/write')
            delegate=engine.Tool('delegate','Build','','agent',agent='Build')
            e.agents={engine.ORCHESTRATOR:engine.AgentSpec(engine.ORCHESTRATOR,'test','system',3,[delegate]),'Build':engine.AgentSpec('Build','test','system',3,[write])}
            called=[]
            def chat(agent,messages,tools):
                called.append(e._context.node['id'])
                if any(m['role']=='tool' for m in messages):return 'Source saved; coordinator must run QA.',[]
                name=e._context.node['files'][0]
                return '',[{'id':'write-'+name,'name':'write','args':json.dumps({'path':root+'/'+name,'content':'source '+name})}]
            e.chat=chat
            tasks=[node('A',['a.py']),node('B',['b.py'])]
            result=e.parallel_tasks(tasks)
            self.assertEqual(result['state'],'completed');self.assertEqual(len(called),4)
            self.assertEqual((Path(root)/'a.py').read_text(),'source a.py')
            self.assertEqual(len({ev['task_id'] for ev in events if ev['type']=='agent_start'}),2)
            for record in e.ledger.data['tasks'].values():
                history=json.loads(Path(record['checkpoint']['path']).read_text())
                self.assertEqual(history['pending'],[])
                self.assertTrue(any(m['role']=='tool' for m in history['messages']))
            e.ledger=None
            result=e.parallel_tasks(tasks)
            self.assertEqual([t['state'] for t in result['tasks']],['reused','reused'])
            self.assertEqual(len(called),4)

class CoordinatorHistoryTests(unittest.TestCase):
    def test_coordinator_trace_survives_new_engine_without_replay(self):
        with tempfile.TemporaryDirectory() as root:
            bridge=Bridge(root)
            def runner():
                e=engine.Engine.__new__(engine.Engine);e.project='example';e.project_root=root;e.ledger=None;e._context=threading.local()
                e.stop,e.pause_requested,e.paused=threading.Event(),threading.Event(),threading.Event();e.emit=lambda ev:None
                e.bridge=lambda path,args:json.dumps(bridge(path,args))
                e.agents={engine.ORCHESTRATOR:engine.AgentSpec(engine.ORCHESTRATOR,'test','system',3,[engine.Tool('think','Think','','think')])}
                e.chat=lambda a,m,t:('Saved outcome',[]) if any(x['role']=='tool' for x in m) else ('',[{'id':'one','name':'think','args':'{}'}])
                return e
            first=runner();self.assertEqual(first.respond('Implement source',[]),'Saved outcome')
            record=first.ledger.data['coordinators'][0]
            journal=Path(record['checkpoint']['journal']).read_text().splitlines()
            self.assertEqual(sum(json.loads(line)['role']=='tool' for line in journal),1)
            second=runner();second.chat=lambda a,m,t:('Continue from saved source',[])
            second.respond('continue',[])
            self.assertIn('Saved outcome',second.agents[engine.ORCHESTRATOR].system)
            self.assertIn(record['checkpoint']['path'],second.agents[engine.ORCHESTRATOR].system)
            self.assertIn('.devpilot/task-history/',(Path(root)/'.gitignore').read_text())
    def test_restart_marks_inflight_work_interrupted(self):
        with tempfile.TemporaryDirectory() as root:
            bridge=Bridge(root);ledger=TaskLedger(bridge,root)
            ledger.data['tasks']['key']={**node('A'),'state':'running'};ledger.save()
            recovered=TaskLedger(bridge,root)
            self.assertEqual(recovered.data['tasks']['key']['state'],'interrupted')
            self.assertIn('inspect saved history',recovered.data['tasks']['key']['error'])

class AdmissionTests(unittest.TestCase):
    def test_concurrency_and_start_spacing(self):
        gate=RequestGate(2,.025);starts=[];lock=threading.Lock();active=0;peak=0
        def work():
            nonlocal active,peak
            with gate.slot(lambda e:None,'A',lambda:None):
                with lock:starts.append(time.monotonic());active+=1;peak=max(peak,active)
                time.sleep(.08)
                with lock:active-=1
        threads=[threading.Thread(target=work) for _ in range(5)]
        for t in threads:t.start()
        for t in threads:t.join(2);self.assertFalse(t.is_alive())
        self.assertEqual(peak,2)
        self.assertTrue(all(b-a>=.02 for a,b in zip(starts,starts[1:])))
    def test_cancelled_waiter_is_removed_and_shared_cooldown_delays_new_request(self):
        gate=RequestGate(1,0);gate.defer(.09);events=[];start=time.monotonic()
        with gate.slot(events.append,'A',lambda:None):self.assertGreaterEqual(time.monotonic()-start,.075)
        def stop():raise engine.Stopped()
        with self.assertRaises(engine.Stopped):
            with gate.slot(events.append,'B',stop):self.fail('cancelled request admitted')
        self.assertEqual(gate.snapshot()['queued'],0)
        self.assertEqual(events[-1]['state'],'cancelled')

class OwnershipTests(unittest.TestCase):
    def test_lane_cannot_write_undeclared_file_or_use_shell(self):
        e=engine.Engine.__new__(engine.Engine);e.stop=threading.Event();e.pause_requested=threading.Event();e.paused=threading.Event();e._context=threading.local()
        with tempfile.TemporaryDirectory() as root:
            e.project_root=root;e._context.node={'files':['own.py'],'reads':[]};e._context.revisions={'own.py':'missing'}
            with patch.object(e,'bridge') as bridge:
                with self.assertRaisesRegex(ValueError,'ownership'):e.run_tool(None,engine.Tool('write','Write','','bridge',path='/fs/write'),{'path':root+'/other.py','content':'bad'},1)
                with self.assertRaisesRegex(ValueError,'coordinator'):e.run_tool(None,engine.Tool('shell','Shell','','bridge',path='/shell'),{'cmd':'touch other.py'},1)
                bridge.assert_not_called()
    def test_lane_revision_check_preserves_concurrent_user_edit(self):
        e=engine.Engine.__new__(engine.Engine);e.stop=threading.Event();e.pause_requested=threading.Event();e.paused=threading.Event();e._context=threading.local()
        with tempfile.TemporaryDirectory() as root:
            e.project_root=root;e._context.node={'files':['own.py'],'reads':[]};e._context.revisions={'own.py':hashlib.sha256(b'old').hexdigest()}
            p=Path(root)/'own.py';p.write_text('user edit');b=Bridge(root);e.bridge=lambda path,args:json.dumps(b(path,args))
            result=e.run_tool(None,engine.Tool('write','Write','','bridge',path='/fs/write'),{'path':str(p),'content':'overwrite'},1)
            self.assertIn('conflict',result);self.assertEqual(p.read_text(),'user edit')

if __name__=='__main__':unittest.main()
