# Reddit Submission for r/LocalLLaMA

**Subreddit:** r/LocalLLaMA  
**Recommended Flair:** `Project`  
**Direct Submit URL:** https://www.reddit.com/r/LocalLLaMA/submit

---

## Post Title
```text
I built an open-source, local-first autonomous agent mesh with Bubblewrap OS sandboxing & telemetry HUD (K.R.Y.Z.E.N)
```

---

## Post Body (Markdown)

```markdown
Hey r/LocalLLaMA,

Like many of you, I've spent the last year experimenting with autonomous agent frameworks (AutoGPT, CrewAI, MetaGPT). While great in theory, running them against local models (via Ollama or vLLM) almost always hit the same three walls:

1. **Prompt & Context Bloat:** Most frameworks dump massive system prompts with 30 tools into a single context window. Small 7B–14B local models get overwhelmed, produce malformed tool JSON, and hallucinate within 3 loops.
2. **The "Rogue Agent" Fear:** Letting an autonomous agent execute raw bash or python scripts on your host machine without sandboxing is asking for trouble.
3. **Black-Box Failure:** When an agent gets stuck in an infinite retry loop, you have no visibility into what state it's in or why it failed without sifting through gigabytes of terminal logs.

To solve this, I built **K.R.Y.Z.E.N** — a lightweight, modular autonomous agent mesh and telemetry studio designed specifically to run reliably with both local and hosted models.

* **GitHub:** [https://github.com/Hossein4163/KRYZEN](https://github.com/Hossein4163/KRYZEN)
* **Documentation & Architecture:** [https://hossein4163.github.io/KRYZEN/](https://hossein4163.github.io/KRYZEN/)
* **License:** MIT (100% Free & Open Source)

---

### Core Architecture & How It Works

Instead of one monolithic LLM trying to do everything, K.R.Y.Z.E.N organizes 14 specialized agents across a structured 6-stage linear pipeline:

```
[PLAN] ──> [DEV] ──> [TEST] ──> [PACK] ──> [DEPLOY] ──> [GROW]
  │           │         │         │          │            │
Architect   Builder   Auditor   Packager   SiteOps       SEO
PM          Refactor  Security  Docker     Release      Reviewer
```

Each stage has dedicated, orthogonal conduits and features built for local AI stability:

#### 1. Context Diet & Targeted Tool Allocation
Rather than exposing dozens of tools at once, agents only inherit the minimal tools needed for their lifecycle stage. A `Builder` gets file editing and AST analysis; an `Auditor` gets test runners and diff inspectors. This keeps context sizes under 2k–4k tokens, allowing models like **Qwen 2.5 Coder (7B/14B)**, **Llama 3.3 70B**, and **DeepSeek-R1** to execute tool calls with near-zero syntax failures.

#### 2. Linux Kernel Sandboxing via Bubblewrap (`bwrap`)
All agent shell executions, tool invocations, and test suites run strictly inside an unprivileged Bubblewrap (`bwrap`) container with bind-mounted workdirs, isolated `/tmp`, and no host privilege escalation. If an agent tries to wipe `/` or access protected files, the kernel blocks it at the syscall layer.

#### 3. Stage Gate Circuit Breakers (Human-in-the-Loop)
Between pipeline stages, hardware-style circuit breakers can be locked or released. When locked, the pipeline holds before transitioning from Dev to Test or Pack to Deploy, allowing you to inspect diffs and approve actions before anything touches production or disk.

#### 4. Real-Time Telemetry & Honeycomb HUD
The UI is a lightweight, zero-framework Swiss Modernist canvas inspired by Linear and cockpit telemetry. It streams real-time agent cognitive states, request/response payloads, and execution loops over WebSockets with a live radar minimap.

---

### Quickstart (Running with Local Ollama / vLLM)

You don't need any paid API keys. If you have Ollama or vLLM running locally:

```bash
# 1. Clone the repository
git clone https://github.com/Hossein4163/KRYZEN.git
cd K.R.Y.Z.E.N

# 2. Configure local model endpoint in agent/runtime.env
cat <<EOF > agent/runtime.env
OPENAI_API_BASE=http://localhost:11434/v1
OPENAI_MODEL=qwen2.5-coder:14b
KRYZEN_SANDBOX=bwrap
EOF

# 3. Launch the studio
./agent/jarvis/start.sh
```

Then open `http://localhost:8770` in your browser.

---

### What I’d Love Feedback On
* **Local Model Prompt Formats:** Which prompt structures or tool calling wrappers have worked best for you with Ollama/vLLM?
* **Subprocess Sandboxing:** Would Docker / Firecracker integration be preferred over native `bwrap` for non-Linux users?
* **Community Contributions:** The agent mesh and skill pack definitions are straightforward JSON/Python files if you'd like to plug in your own local tools.

Check out the repo, star it if you find the architecture useful, and let me know your thoughts or criticisms!
```
