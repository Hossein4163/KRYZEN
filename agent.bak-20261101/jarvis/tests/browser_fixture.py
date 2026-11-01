"""Disposable system fixture for browser QA. Never uses keys, models or real projects.

python3 agent/jarvis/tests/browser_fixture.py --port 8771
"""
import argparse
import json
import random
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import struct
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
import engine
import mesh
import forms
import control
import studio
from test_reliability import pc


class FixtureEngine(engine.Engine):
    def __init__(self, emit, project="", **_kw):
        self.emit, self.project = emit, project
        self.stop, self.paused, self.pause_requested = threading.Event(), threading.Event(), threading.Event()

    def respond(self, text, history):
        self.emit({"type": "agent_start", "agent": engine.ORCHESTRATOR, "depth": 0, "task": text})
        if "parallel demo" in text:
            from orchestration import REQUESTS
            runner=engine.Engine.__new__(engine.Engine)
            runner._context=threading.local()
            runner.project=self.project;runner.project_root=str(FIXTURE_ROOT/self.project);runner.ledger=None
            runner.stop,runner.pause_requested,runner.paused=self.stop,self.pause_requested,self.paused
            runner.emit=lambda ev:self.emit({**({'task_id':runner._context.task_id} if getattr(runner._context,'task_id',None) else {}),**ev})
            runner.bridge=lambda path,body:json.dumps(server.bridge(path,body))
            write=engine.Tool('write','Write Source','','bridge',path='/fs/write')
            lead=engine.AgentSpec(engine.ORCHESTRATOR,'fixture','fixture',3,[engine.Tool('delegate','Build','','agent',agent='Build Agent')])
            runner.agents={engine.ORCHESTRATOR:lead,'Build Agent':engine.AgentSpec('Build Agent','fixture','fixture',3,[write])}
            def chat(spec,messages,tools):
                with REQUESTS.slot(runner.emit,spec.name,runner.checkpoint_control):
                    if runner.stop.wait(.12):raise engine.Stopped()
                    if any(m['role']=='tool' for m in messages):return 'Source saved. Coordinator QA remains.',[]
                    path=runner._context.node['files'][0]
                    return '',[{'id':'write-'+path,'name':'write','args':json.dumps({'path':runner.project_root+'/'+path,'content':'Verified fixture source for '+path})}]
            runner.chat=chat
            tasks=[{'id':name,'agent':'Build Agent','task':'Fixture source branch '+name,'revision':'1','files':['src/parallel-'+name+'.txt'],'reads':[],'depends_on':deps} for name,deps in [('A',[]),('B',[]),('C',['A','B'])]]
            result=runner.parallel_tasks(tasks)
            return 'Fixture task graph '+result['state']+'. '+str(len(result['tasks']))+' tasks saved.'
        if "fast" in text:
            self.emit({"type": "token", "agent": engine.ORCHESTRATOR, "text": "Fast reply verified."})
            return "Fast reply verified."
        for word in ["Testing ", "a ", "recoverable ", "local ", "run. "] * 10:
            self.checkpoint_control()
            self.emit({"type": "token", "agent": engine.ORCHESTRATOR, "text": word})
            if self.stop.wait(.07):
                raise engine.Stopped()
        return "Fixture run complete. No model or project mutations occurred."


def main(port):
    with tempfile.TemporaryDirectory(prefix="jarvis-system-qa-") as temp:
        root = Path(temp)
        global FIXTURE_ROOT
        FIXTURE_ROOT = root
        vault = root / "_DevPilot"
        shutil.copytree(mesh.SYS, vault, ignore=shutil.ignore_patterns("Archive"))
        mesh.SYS, mesh.AGENT_NOTES, mesh.ARCHIVE = vault, vault / "Agents", vault / "Archive"
        mesh.rebuild = lambda: {"ok": True, "output": "Fixture configuration validated"}
        forms.SETTINGS, forms.TOOL_NOTES = vault / "Settings.md", vault / "Tools"
        control.UI_FILE = vault / "jarvis.json"
        control.ROOTS = {"vault": vault, "jarvis": root / "jarvis", "builder": root / "workflow"}
        for p in control.ROOTS.values(): p.mkdir(exist_ok=True)
        pc.WORKSPACE, pc.PROTECTED, pc.HERE, pc.JOBS = root, [vault, root / ".obsidian"], root / "bridge", {}
        pc.HERE.mkdir()
        pc.TEMPLATE_DIR = vault / "Templates" / "project"
        for slug in ("example-project", "other-project"):
            pc.h_project_init({"slug": slug, "title": slug, "goal": "Disposable browser verification"})
            pc.h_write({"path": str(root / slug / "docs/plan/PLAN.md"), "content": "# QA Plan\n## Milestone 1: Verify\n- [ ] Check the interface\n- [ ] Report results\n"})
            pc.h_write({"path": str(root / slug / "src/example.txt"), "content": "Original file\n"})
        project = root / "example-project"
        (project / "assets").mkdir()
        def png(width, height, noise=False):
            def chunk(kind, data):
                return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
            rng=random.Random(42)
            rows=b''.join(b'\0'+(rng.randbytes(width*4) if noise else b''.join(bytes((x*255//width,y*255//height,190,255)) for x in range(width))) for y in range(height))
            return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
        image=png(256,160)
        (project / "assets/sample.png").write_bytes(image)
        (project / "assets/race.png").write_bytes(image)
        (project / "assets/large.png").write_bytes(png(512,512,True))
        with (project / "assets/oversize.png").open('wb') as oversized:
            oversized.truncate(8*1024*1024+1)
        (project / "assets/it's a test $(touch INJECTED).png").write_bytes(image)
        (project / "assets/corrupt.png").write_bytes(b'not a real image')
        (project / "assets/vector.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="240" height="150" viewBox="0 0 240 150" onload="parent.__svgExecuted=true"><rect width="240" height="150" fill="#6b5bd2"/><circle cx="120" cy="75" r="45" fill="#8dd0c2"/><script>parent.__svgExecuted=true</script></svg>')
        (project / "assets/outside.png").symlink_to(root / "other-project/src/example.txt")
        (project / "src/components").mkdir()
        (project / "src/components/app.js").write_text('export function greet(name) {\n  const message = "Hello " + name;\n  // A colored comment\n  return message;\n}\nconst escaped = "<script>window.__codeExecuted = true</script>";\n')
        (project / "src/styles.css").write_text(':root { --accent: #bba7ed; }\nbody { color: var(--accent); }\n')
        (project / "config.json").write_text('{"enabled":true,"count":42}\n')
        server.SESSIONS = root / "sessions"
        server.SESSIONS.mkdir()
        server.engine.Engine = FixtureEngine
        def bridge(path, body):
            body = dict(body)
            for key in ("path", "cwd"):
                value = body.get(key, "")
                for prefix in ("~/Projects/devpilot", str(Path.home() / "Projects/devpilot")):
                    if value == prefix or value.startswith(prefix + "/"):
                        body[key] = str(root) + value[len(prefix):]
                        break
            if path == "/shell":
                cwd = pc.resolve(body.get("cwd"))
                result = subprocess.run(["sh", "-c", body["cmd"]], cwd=cwd, text=True, capture_output=True, timeout=10)
                return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}
            try:
                return pc.ROUTES[path](body)
            except Exception as error:
                return {"error": f"{type(error).__name__}: {error}"}
        server.bridge = bridge
        server.PORT = port
        class FixtureHandler(server.Handler):
            def do_GET(self):
                if self.path == "/api/fixture":
                    return self.send(200, {"fixture": True})
                return super().do_GET()
        print(json.dumps({"url": f"http://127.0.0.1:{port}", "root": str(root)}), flush=True)
        server.ThreadingHTTPServer(("127.0.0.1", port), FixtureHandler).serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8771)
    main(parser.parse_args().port)
