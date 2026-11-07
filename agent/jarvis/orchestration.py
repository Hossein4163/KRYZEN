"""Bounded request admission and durable, source-aware task DAG execution."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
import hashlib
import json
from pathlib import PurePosixPath, Path
import threading
import time
import uuid


class RequestGate:
    """FIFO admission for model requests. Concurrency adapts: -1 on each rate limit, +1 after a streak of
    clean calls, within [1, max_limit]."""
    def __init__(self, limit=2, spacing=.5, max_limit=4, streak=10):
        self.limit, self.spacing = limit, spacing
        self.max_limit, self.streak_needed, self.streak = max_limit, streak, 0
        self.condition = threading.Condition()
        self.queue, self.active = deque(), 0
        self.next_start, self.cooldown = 0., 0.

    def defer(self, seconds):
        with self.condition:
            self.cooldown = max(self.cooldown, time.monotonic()+max(0, seconds))
            self.condition.notify_all()

    def on_success(self):
        with self.condition:
            self.streak += 1
            if self.streak >= self.streak_needed and self.limit < self.max_limit:
                self.limit += 1; self.streak = 0
                self.condition.notify_all()

    def on_rate_limit(self):
        with self.condition:
            self.streak = 0
            self.limit = max(1, self.limit - 1)

    def configure(self, max_limit):
        with self.condition:
            self.max_limit = max(1, int(max_limit))
            self.limit = min(self.limit, self.max_limit)
            self.condition.notify_all()

    def snapshot(self):
        with self.condition:
            return {'limit':self.limit,'max_limit':self.max_limit,'active':self.active,'queued':len(self.queue),
                    'spacing':self.spacing,'cooldown_seconds':round(max(0,self.cooldown-time.monotonic()),1)}

    @contextmanager
    def slot(self, emit, agent, check, ready=lambda:True):
        ticket={'id':uuid.uuid4().hex[:12],'ready':ready}
        admitted=False
        failed=False
        with self.condition:
            if len(self.queue)>=64:raise RuntimeError('Request queue is full; retry after existing work completes')
            self.queue.append(ticket)
        try:
            emit({'type':'request_state','request_id':ticket['id'],'agent':agent,'state':'queued',**self.snapshot()})
            while not admitted:
                check()
                with self.condition:
                    eligible=next((item for item in self.queue if item['ready']()),None)
                    if eligible is ticket and self.active<self.limit and time.monotonic()>=max(self.next_start,self.cooldown):
                        self.queue.remove(ticket);self.active+=1;admitted=True
                        self.next_start=time.monotonic()+self.spacing
                    else:self.condition.wait(.05)
            emit({'type':'request_state','request_id':ticket['id'],'agent':agent,'state':'running',**self.snapshot()})
            yield
        except BaseException:
            failed=True
            raise
        finally:
            with self.condition:
                if admitted:self.active-=1
                elif ticket in self.queue:self.queue.remove(ticket)
                self.condition.notify_all()
            emit({'type':'request_state','request_id':ticket['id'],'agent':agent,'state':('failed' if failed else 'finished') if admitted else 'cancelled',**self.snapshot()})


REQUESTS=RequestGate(limit=3)


def source_path(value):
    if not isinstance(value,str) or not value or '\\' in value:raise ValueError('Source paths must be project-relative files')
    p=PurePosixPath(value)
    if not p.parts or p.is_absolute() or '..' in p.parts or p.parts[0] in ('.git','.devpilot'):raise ValueError('Source path must stay in the project source tree')
    return str(p)


def task_schema():
    return {'type':'function','function':{'name':'execute_parallel_tasks','description':
        'Execute a saved dependency graph in the selected project. Independent source-disjoint tasks run concurrently; '
        'dependencies wait. Matching completed tasks reuse saved results and source revisions. '
        'Each lane can read files and write only declared files with file tools. Shell/custom tools and nested delegation '
        'are unavailable in lanes; run builds/tests in the coordinator after join. Interrupted effects need reconciliation. '
        'Use stable task IDs and revision; change revision only for authorized new work, never to bypass a failure.',
        'parameters':{'type':'object','additionalProperties':False,'required':['tasks'],'properties':{'tasks':{'type':'array','minItems':1,'maxItems':24,
        'items':{'type':'object','additionalProperties':False,'required':['id','agent','task','depends_on','files','reads','revision'],
        'properties':{'id':{'type':'string'},'agent':{'type':'string'},'task':{'type':'string'},'revision':{'type':'string'},
        'depends_on':{'type':'array','items':{'type':'string'}},'files':{'type':'array','items':{'type':'string'}},'reads':{'type':'array','items':{'type':'string'}}}}}}}}}


class TaskLedger:
    def __init__(self, bridge, root):
        self.bridge,self.root=bridge,root.rstrip('/')
        self.path=self.root+'/.devpilot/execution.json'
        self.lock=threading.RLock()
        self.data={'version':1,'tasks':{},'runs':[]}
        self.revision=None
        self._ignore_ready=False
        read=self.call('/fs/read',{'path':self.path,'raw':True})
        if read.get('error'):
            # The bridge reports missing files as errors; all other failures must remain visible.
            err = str(read['error']).lower()
            if not any(p in err for p in ('not found', 'no such file', 'filenotfounderror', 'errno 2')):
                raise ValueError(read['error'])
        else:
            self.data=json.loads(read['content']);self.revision=read.get('revision')
            if self.data.get('version')!=1 or not isinstance(self.data.get('tasks'),dict):raise ValueError('Unsupported saved execution ledger')
            recovered=False
            for record in list(self.data['tasks'].values())+self.data.get('coordinators',[]):
                if record.get('state')=='running':record.update(state='interrupted',error='Engine restarted; inspect saved history and sources before continuing');recovered=True
            if recovered:
                for run in self.data.get('runs',[]):
                    if run.get('state')=='running':run['state']='interrupted'
                self.save()

    def call(self,path,body):
        if path in ('/fs/read','/fs/write'):
            Path(body['path']).resolve().relative_to(Path(self.root).resolve())
        result=self.bridge(path,body)
        return json.loads(result) if isinstance(result,str) else result

    def save(self):
        with self.lock:
            if not self._ignore_ready:
                path=self.root+'/.gitignore'
                current=self.call('/fs/read',{'path':path,'raw':True})
                if current.get('error'):
                    err = str(current['error']).lower()
                    if not any(p in err for p in ('not found', 'no such file', 'filenotfounderror', 'errno 2')):
                        raise RuntimeError('Cannot protect local execution history: '+str(current['error']))
                text=current.get('content','')
                missing=[p for p in ('.devpilot/execution.json','.devpilot/task-history/') if p not in text.splitlines()]
                if missing:
                    args={'path':path,'content':text.rstrip('\n')+'\n\n# Local execution checkpoints and tool history\n'+'\n'.join(missing)+'\n'}
                    if current.get('revision'):args['expected_revision']=current['revision']
                    else:args['create_only']=True
                    value=self.call('/fs/write',args)
                    if value.get('error'):raise RuntimeError('Cannot protect local execution history: '+str(value['error']))
                self._ignore_ready=True
            self.data['updated']=time.time()
            if len(json.dumps(self.data,ensure_ascii=False).encode())>1600000:
                for record in self.data['tasks'].values():
                    if record.get('state')=='completed':
                        record['result']=record.get('result','')[:1800]
                        record['task']=record.get('task','')[:1200]
            if len(json.dumps(self.data,ensure_ascii=False).encode())>1900000:
                raise RuntimeError('Execution ledger is too large; archive old task definitions before adding more')
            args={'path':self.path,'content':json.dumps(self.data,ensure_ascii=False),'expected_revision':self.revision} if self.revision else {'path':self.path,'content':json.dumps(self.data,ensure_ascii=False),'create_only':True}
            result=self.call('/fs/write',args)
            if result.get('error'):raise RuntimeError('Execution checkpoint could not save: '+str(result['error']))
            self.revision=result['revision']
            try:
                import brain
                brain.StateDB(self.root).set_state("ledger", self.data)
            except Exception:
                pass

    def fingerprints(self, paths):
        result={}
        for name in sorted(set(paths)):
            value=self.call('/fs/read',{'path':self.root+'/'+source_path(name),'raw':True})
            if value.get('error'):
                err = str(value['error']).lower()
                if any(p in err for p in ('not found', 'no such file', 'filenotfounderror', 'errno 2')):result[name]='missing'
                else:raise ValueError('Cannot verify source '+name+': '+str(value['error']))
            else:result[name]=value.get('revision') or hashlib.sha256(value['content'].encode()).hexdigest()
        return result

    def memory(self):
        with self.lock:
            return [{'id':r['id'],'agent':r['agent'],'task':r['task'],'revision':r['revision'],'depends_on':r['depends_on'],'state':r['state'],'files':r['files'],'reads':r['reads'],
                     'result':r.get('result','')[:1800],'error':r.get('error',''),'checkpoint':r.get('checkpoint',{})} for r in list(self.data['tasks'].values())[-24:]]

    def checkpoint(self,key,messages,step,pending,record=None):
        with self.lock:
            if record is None:record=self.data['tasks'][key]
            path=self.root+'/.devpilot/task-history/'+key+'.json'
            journal=self.root+'/.devpilot/task-history/'+key+'.jsonl'
            previous=record.get('history_messages',0)
            new=messages[previous:]
            if new:
                args={'path':journal,'content':''.join(json.dumps(m,ensure_ascii=False)+'\n' for m in new),'append':True}
                if record.get('journal_revision'):args['expected_revision']=record['journal_revision']
                else:args['create_only']=True
                result=self.call('/fs/write',args)
                if result.get('error'):raise RuntimeError('Task journal could not save: '+str(result['error']))
                record['journal_revision']=result['revision'];record['history_messages']=len(messages)
            checkpoint={'messages':messages,'step':step,'pending':pending,'t':time.time(),'journal':journal}
            if len(json.dumps(checkpoint,ensure_ascii=False).encode())>1700000:
                checkpoint={'step':step,'pending':pending,'t':time.time(),'journal':journal,'summary':'Read the append-only history journal and current sources before continuing.'}
            args={'path':path,'content':json.dumps(checkpoint,ensure_ascii=False)}
            if record.get('checkpoint_revision'):args['expected_revision']=record['checkpoint_revision']
            else:args['create_only']=True
            result=self.call('/fs/write',args)
            if result.get('error'):raise RuntimeError('Task history could not save: '+str(result['error']))
            record['checkpoint_revision']=result['revision']
            record['checkpoint']={'path':path,'journal':journal,'step':step,'pending':pending,'t':checkpoint['t']}
            self.save()

    def run(self, tasks, allowed, execute, check, emit, max_workers=3):
        if not isinstance(tasks,list) or not 1<=len(tasks)<=24:raise ValueError('Use 1–24 task nodes')
        nodes={}
        for task in tasks:
            if not isinstance(task,dict):raise ValueError('Each task must be an object')
            for field in ('id','agent','task','revision'):
                if not isinstance(task.get(field),str) or not task[field].strip() or len(task[field])>(12000 if field=='task' else 100):raise ValueError('Invalid task '+field)
            if task['id'] in nodes:raise ValueError('Duplicate task id')
            if task['agent'] not in allowed:raise ValueError('Agent is not available for delegation: '+task['agent'])
            for field in ('depends_on','files','reads'):
                if not isinstance(task.get(field),list) or len(task[field])>120 or any(not isinstance(x,str) for x in task[field]):raise ValueError('Invalid '+field)
            def canonical(value):
                relative=source_path(value)
                return str((Path(self.root)/relative).resolve().relative_to(Path(self.root).resolve()))
            nodes[task['id']]={**task,'depends_on':sorted(set(task['depends_on'])),'files':sorted(set(canonical(p) for p in task['files'])),'reads':sorted(set(canonical(p) for p in task['reads']))}
        keys,visiting={},set()
        def identity(name):
            if name not in nodes:raise ValueError('Unknown dependency: '+name)
            if name in visiting:raise ValueError('Task dependencies contain a cycle')
            if name in keys:return keys[name]
            visiting.add(name);node=nodes[name]
            parents=[identity(dep) for dep in node['depends_on']]
            keys[name]=hashlib.sha256(json.dumps({**node,'parents':parents},sort_keys=True).encode()).hexdigest()
            visiting.remove(name);return keys[name]
        for name in nodes:identity(name)
        run_id=uuid.uuid4().hex[:12]
        run={'id':run_id,'started':time.time(),'state':'running','nodes':[{'id':n,'key':keys[n],'depends_on':t['depends_on']} for n,t in nodes.items()]}
        with self.lock:
            self.data['runs']=(self.data.get('runs',[])+[run])[-20:]
            states={}
            for name,node in nodes.items():
                previous=self.data['tasks'].get(keys[name]);state='waiting'
                if previous:
                    if previous['state']=='completed':
                        state='reused' if self.fingerprints(node['files']+node['reads'])==previous.get('sources') else 'review_required'
                    elif previous['state'] in ('running','interrupted','review_required','failed'):
                        state='review_required'
                else:
                    previous={**node,'state':'waiting','created':time.time()};self.data['tasks'][keys[name]]=previous
                states[name]=state
                if state=='review_required':previous['error']='Saved work needs source reconciliation; do not repeat its side effects. Inspect checkpoint and changed files.'
            self.save()
        emit({'type':'parallel_run','run_id':run_id,'state':'running','nodes':[{'id':n,'agent':t['agent'],'depends_on':t['depends_on'],'files':t['files'],'reads':t['reads'],'state':states[n]} for n,t in nodes.items()]})
        def report(name,state,**extra):
            states[name]=state
            next(n for n in run['nodes'] if n['id']==name)['state']=state
            record=self.data['tasks'][keys[name]]
            with self.lock:
                record.update(state='completed' if state=='reused' else state,updated=time.time(),**extra);self.save()
            emit({'type':'task_state','run_id':run_id,'task_id':run_id+':'+name,'id':name,'agent':nodes[name]['agent'],'state':state,'depends_on':nodes[name]['depends_on'],'files':nodes[name]['files'],**extra})
        for name,state in list(states.items()):
            if state in ('reused','review_required'):report(name,state)
        def conflict(a,b):
            aw,ar=set(a['files']),set(a['reads'])|{'PROJECT.md','docs/plan/PLAN.md'};bw,br=set(b['files']),set(b['reads'])|{'PROJECT.md','docs/plan/PLAN.md'}
            return bool(aw&(bw|br) or bw&ar)
        pending={n for n,s in states.items() if s=='waiting'}
        futures={}
        try:
            with ThreadPoolExecutor(max_workers=max_workers,thread_name_prefix='kryzen-task') as pool:
                while pending or futures:
                    check()
                    for name in list(nodes):
                        if name not in pending:continue
                        deps=[states[d] for d in nodes[name]['depends_on']]
                        if any(s in ('failed','blocked','review_required','interrupted') for s in deps):
                            pending.remove(name);report(name,'blocked',error='A prerequisite needs attention');continue
                        if not all(s in ('completed','reused') for s in deps):continue
                        if len(futures)>=max_workers or any(conflict(nodes[name],nodes[other]) for other in futures.values()):continue
                        pending.remove(name);report(name,'running',started=time.time())
                        predecessors={d:self.data['tasks'][keys[d]].get('result','') for d in nodes[name]['depends_on']}
                        futures[pool.submit(execute,nodes[name],keys[name],run_id+':'+name,predecessors,self)]=name
                    if not futures:
                        if pending:raise RuntimeError('Task graph cannot progress')
                        break
                    done,_=wait(futures,timeout=.1,return_when=FIRST_COMPLETED)
                    for future in done:
                        name=futures.pop(future)
                        try:
                            result=future.result()
                            report(name,'completed',result=str(result)[:18000],sources=self.fingerprints(nodes[name]['files']+nodes[name]['reads']),finished=time.time())
                        except Exception as error:
                            report(name,'failed',error=str(error)[:1500],finished=time.time())
                check()
                # Accept only verified writes from later lanes, never unrelated user edits.
                for name,state in states.items():
                    if state not in ('completed','reused'):continue
                    record=self.data['tasks'][keys[name]]
                    current=self.fingerprints(nodes[name]['files']+nodes[name]['reads'])
                    changed={p for p,v in current.items() if v!=record.get('sources',{}).get(p)}
                    verified=set()
                    for other,status in states.items():
                        if other==name or status!='completed':continue
                        writer=self.data['tasks'][keys[other]]
                        if writer.get('finished',0)<=record.get('finished',0):continue
                        verified.update(p for p in changed if p in nodes[other]['files'] and writer.get('sources',{}).get(p)==current[p])
                    if changed-verified:
                        report(name,'review_required',error='Source changed outside verified task writes; inspect saved history and current files')
                    else:record['sources']=current
                self.save()
            run['state']='completed' if all(s in ('completed','reused') for s in states.values()) else 'needs_attention'
        except BaseException:
            for name,state in list(states.items()):
                if state in ('waiting','running'):report(name,'interrupted')
            run['state']='interrupted'
            raise
        finally:
            run['finished']=time.time();self.save()
            emit({'type':'parallel_run','run_id':run_id,'state':run['state']})
        return {'ok':run['state']=='completed','run_id':run_id,'state':run['state'],'tasks':[{'id':n,'state':s,'result':self.data['tasks'][keys[n]].get('result',''),'error':self.data['tasks'][keys[n]].get('error','')} for n,s in states.items()]}
