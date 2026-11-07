# Reddit Submission for r/Python

**Subreddit:** r/Python  
**Recommended Flair:** `Showcase` (or `Project`)  
**Direct Submit URL:** https://www.reddit.com/r/Python/submit

---

## Post Title
```text
Showcase: K.R.Y.Z.E.N — A lightweight, sandboxed autonomous agent mesh and telemetry studio built with pure Python & async pipelines
```

---

## Post Body (Markdown)

```markdown
Hey everyone,

I wanted to share **K.R.Y.Z.E.N**, an open-source Python framework and studio I built for orchestrating autonomous AI agent meshes with sandboxed command execution, stage gates, and real-time visual telemetry.

* **GitHub:** [https://github.com/Hossein4163/KRYZEN](https://github.com/Hossein4163/KRYZEN)
* **Live Documentation:** [https://hossein4163.github.io/KRYZEN/](https://hossein4163.github.io/KRYZEN/)
* **License:** MIT

---

### Why Build This? (The Python Architecture Rationale)

Most popular agent frameworks today (LangChain, CrewAI, AutoGen) tend to suffer from two common issues:
1. **Dependency Heaviness:** Hundreds of transitive dependencies, complex abstraction layers, and opaque metaclasses that make debugging asyncio loops or custom tools frustrating.
2. **Execution Safety:** When building agents that write and test code, executing raw subprocesses directly on the host OS is unsafe.

With K.R.Y.Z.E.N, I wanted an architecture that prioritized:
* **Zero unnecessary framework bloat:** Built around clean Python 3.12+ `asyncio`, standard HTTP/WebSocket protocols, and lightweight modular handlers.
* **Deterministic Concurrency:** An orchestrator that manages discrete agent lifecycle states rather than chaotic, uncontrolled recursive callbacks.
* **OS-Level Sandboxing:** Tight integration with Linux Bubblewrap (`bwrap`) so subprocess calls never escape into the host environment.

---

### Key Architectural Components

#### 1. The 6-Stage Honeycomb Lifecycle
Instead of a single "do-it-all" agent, the workload is distributed across 14 specialized workers partitioned into 6 sequential product phases:
* **`Plan`** (System Architect, Technical PM)
* **`Dev`** (Code Builder, Refactoring Specialist)
* **`Test`** (E2E Auditor, Security Pen-Tester)
* **`Pack`** (Dependency Bundler, Docker Containerizer)
* **`Deploy`** (SiteOps Engineer, Semantic Release Manager)
* **`Grow`** (SEO Engineer, Code Reviewer)

Each agent is initialized with an isolated skill manifest, keeping context token usage minimal and responses highly focused.

#### 2. Sandboxed Tool Execution (`bwrap`)
Tool invocations that interact with the filesystem or terminal are routed through an unprivileged Bubblewrap sandbox:

```python
# Conceptual sandbox dispatcher in K.R.Y.Z.E.N
import asyncio
import subprocess

async def run_sandboxed(command: list[str], workspace_dir: str) -> subprocess.CompletedProcess:
    bwrap_cmd = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/lib64", "/lib64",
        "--proc", "/proc",
        "--dev", "/dev",
        "--bind", workspace_dir, "/workspace",
        "--tmpfs", "/tmp",
        "--unshare-all",
        "--die-with-parent",
        "--chdir", "/workspace",
        *command
    ]
    proc = await asyncio.create_subprocess_exec(
        *bwrap_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    return stdout.decode(), stderr.decode(), proc.returncode
```

#### 3. Human-in-the-Loop Circuit Breakers
Before critical transitions (e.g., from `Dev` to `Pack`, or running privileged scripts), stage gate breakers can pause pipeline execution. Events are dispatched over WebSockets to a Swiss-Modernist web HUD, allowing real-time inspection of AST diffs, gate releases, and radar tracking.

---

### How to Try It

```bash
git clone https://github.com/Hossein4163/KRYZEN.git
cd K.R.Y.Z.E.N

# Copy example config (supports OpenAI, Anthropic, or local Ollama/vLLM)
cp agent/runtime.env.example agent/runtime.env

# Start the Python orchestration service
./agent/jarvis/start.sh
```

Navigate to `http://localhost:8770` to explore the agent mesh canvas, inspect agent nodes, and run test tasks.

---

I would love to hear feedback from Python engineers on:
* Patterns you prefer for managing asynchronous inter-agent messaging queues.
* Ways to extend the unprivileged sandbox for macOS/Windows environments without relying on Docker daemon root privileges.

Code, issues, and PRs are warmly welcome on GitHub!
```
