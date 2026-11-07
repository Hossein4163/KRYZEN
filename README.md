<p align="center">
  <img src="docs/assets/hero.svg" alt="K.R.Y.Z.E.N Logo" width="100%">
</p>

<p align="center">
  <strong>Autonomous AI Product Engineering Mesh &amp; Vibe Studio</strong><br>
  <em>Industrial-grade Swiss-Modernist telemetry engine with zero third-party pip dependencies.</em>
</p>

<p align="center">
  <a href="https://github.com/Hossein4163/KRYZEN/actions"><img src="https://img.shields.io/badge/tests-113%2F113%20passing-brightgreen?style=flat-square&logo=github-actions" alt="Tests"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-red?style=flat-square" alt="License"></a>
  <a href="#architecture"><img src="https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.14%20stdlib-blue?style=flat-square&logo=python" alt="Python Version"></a>
  <a href="#pipeline"><img src="https://img.shields.io/badge/agents-14%20specialists-orange?style=flat-square" alt="Agents"></a>
  <a href="#vibe-studio"><img src="https://img.shields.io/badge/design-Swiss%20Linear-black?style=flat-square" alt="Design"></a>
  <a href="#telemetry"><img src="https://img.shields.io/badge/telemetry-microsecond%20SSE-crimson?style=flat-square" alt="Telemetry"></a>
</p>

---

## ⚡ What is K.R.Y.Z.E.N?

**K.R.Y.Z.E.N** is a sovereign, local-first autonomous software engineering mesh. It coordinates a team of **14 specialized AI agents** that take any idea from zero to a fully deployed production product inside your own local filesystem.

Instead of chaotic multi-agent chatter, K.R.Y.Z.E.N operates like a high-precision Swiss watch: deterministic Manhattan 90° circuit-board routing, elongated 6-facet honeycomb nodes, real-time microsecond Server-Sent Events (SSE) telemetry, stage gate circuit breakers, and an interactive **Vibe Studio** for tactile prompt engineering.

<p align="center">
  <img src="docs/assets/screens/08-honeycomb-mesh.png" alt="K.R.Y.Z.E.N Linear Honeycomb Telemetry Mesh" width="100%">
</p>

---

## ✨ Key Highlights

- **Zero Third-Party Pip Dependencies**: The entire backend engine, SSE stream multiplexer, state machines, and RPC bridges run purely on standard Python 3 (`http.server`, `urllib`, `sqlite3`, `json`, `subprocess`).
- **Linear Honeycomb Mesh Architecture**: 6-facet hexagonal agent nodes with dedicated Inbound Bus Docking, Outbound Bus Docking, Status Crown, LED Pulse Core, and Micro-Facet telemetry trackers.
- **Vibe Studio Telemetry**:
  - **Click-to-Prompt**: Click any element on live generated interfaces to auto-compose context-aware refinement prompts.
  - **Point-and-Tweak Inspector**: Live CSS dial overrides, typography metrics, and spacing physics with instant hot-reload.
  - **Time Travel Checkpoints**: Deterministic state snapshots with 1-click regression rollback.
- **Strict Stage Gate Breakers**: Automated circuit breakers at every phase transition (`Start` → `Discover` → `Plan` → `Design` → `Build` → `Verify` → `Launch` → `Grow`). Pipeline halts safely until acceptance criteria are satisfied.
- **Model Agnostic & Hot-Swappable**: Seamlessly route Reasoning Tier (`gemini-3.8-flash`, `claude-3.5-sonnet`), Fast Tier (`gemini-3-flash`), or Local Offline Tier (`ollama/qwen2.5-coder`) per agent node without restarting the daemon.

---

## 📐 Honeycomb Cell Anatomy

Each agent in the K.R.Y.Z.E.N telemetry mesh is represented as an elongated **6-Facet Linear Honeycomb Cell** engineered for clear visualization of complex agentic execution pipelines:

<p align="center">
  <img src="docs/assets/screens/09-honeycomb-anatomy.png" alt="Honeycomb Cell 5-Part Anatomy" width="100%">
</p>

| Part | Component | Function |
| :---: | :--- | :--- |
| **01** | **Status Crown** | Displays stage index (`00`..`07`), agent codename, and compute tier badge (`REASONING`, `FAST`, `COMPACT`). |
| **02** | **LED Pulse Core** | Hexagonal live telemetry pulse beacon indicating active execution, idle readiness, or warning states. |
| **03** | **Execution Matrix** | Dynamically tracks call count, execution time, token burn rate, and real-time step counters. |
| **04** | **Facet Counter** | Granular tally of sandboxed tool permits and loaded capability skills bound to the agent. |
| **05** | **Bus Docking Ports** | Dual docking ports (-98px inbound / +98px outbound) connecting orthogonal Manhattan telemetry circuit traces. |

---

## 🚀 The 0-to-100 Autonomous Lifecycle

```
[00 START] ──> [15 DISCOVER] ──> [30 PLAN] ──> [45 DESIGN] ──> [60 BUILD] ──> [75 VERIFY] ──> [90 LAUNCH] ──> [100 GROW]
     │              │               │              │             │              │              │              │
Orchestrator     Research        Planner        Design         Build           QA            DevOps          SEO
               & Reference                    & Tokens      (Full-Stack)   (Chromium E2E)  & Security     & Marketing
```

1. **Intake & Product Strategy**: Transforms raw user intent into PRDs, user personas, core user journeys, and scoped acceptance criteria (`PRD.md`, `BRIEF.md`).
2. **Research & Benchmarking**: Competitive intelligence, technology stack feasibility analysis, and public API reference audits.
3. **System Architecture & Planning**: Decomposes milestones into atomic tasks ($T_1 \dots T_n$) with explicit dependency graphs and Architecture Decision Records (`ADR`).
4. **Swiss Design System**: High-contrast, typography-driven UI styling with responsive breakpoints (390px mobile, 768px tablet, 1440px desktop) and WCAG AA accessibility compliance.
5. **Full-Stack Implementation**: Autonomous code generation, database migrations, clean scaffolding, and test suite execution.
6. **Browser QA & E2E Verification**: Real headless/headed Chromium execution checking visual layout, responsiveness, and regression suites.
7. **Production DevOps & Security**: Multi-stage Docker packaging, systemd service units, OWASP compliance, and zero-downtime cutover.
8. **Growth & Technical SEO**: Dynamic XML sitemaps, OpenGraph cards, JSON-LD Schema.org markup, and technical audit verification.

---

## 🛠️ Quickstart

### Prerequisites

- Linux (Ubuntu, Debian, Arch Linux, Fedora) or macOS
- Python 3.10+ (Standard Library only — no pip requirements needed)
- Any supported LLM API key (`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or local `OLLAMA`)

### 1. Clone & Configure

```bash
git clone git@github.com:Hossein4163/KRYZEN.git
cd KRYZEN

# Configure environment variables
cp agent/runtime.env.example agent/runtime.env
# Edit agent/runtime.env with your model API keys
```

### 2. Launch Jarvis Telemetry Mission Control

```bash
cd agent
./jarvis/start.sh
```

Now open **http://127.0.0.1:8770** (or **http://jarvis.local**) in your browser.

---

## 🧪 Running the Verification Test Suite

K.R.Y.Z.E.N maintains a comprehensive test suite covering the server, telemetry streaming, studio operations, mesh routing, and security:

```bash
# Run all 113 unit & integration tests
python3 -m unittest discover -s agent/jarvis/tests
```

```text
Ran 113 tests in 7.8s
OK (skipped=1)
```

---

## 📁 Repository Structure

```text
K.R.Y.Z.E.N/
├── agent/
│   ├── jarvis/              # Pure Python stdlib Mission Control server
│   │   ├── assets/          # Honeycomb SVG graphics, Lucide icons, fonts
│   │   ├── ui/              # Swiss Modernist CSS & reactive UI components
│   │   ├── engine.py        # Autonomous agent execution loop
│   │   ├── mesh.py          # Topological sort & Manhattan routing engine
│   │   ├── studio.py        # Vibe Studio live edit & checkpoint backend
│   │   ├── telemetry.py     # Real-time SSE packet broadcast engine
│   │   └── tests/           # 113 unit, integration, and E2E browser tests
│   ├── bridge/              # Sandboxed local system bridge daemon
│   ├── workflow/            # Standard 0-to-100 project templates
│   └── runtime.env.example  # Configuration template
├── docs/                    # Architectural specs, setup guides, and media
│   ├── OVERVIEW.md          # Complete system specifications & vision
│   ├── SETUP.md             # In-depth installation & systemd daemon guide
│   └── assets/              # Architecture diagrams, screens, and demo GIFs
├── LICENSE                  # MIT Open Source License
└── README.md                # Project documentation
```

---

## 🛡️ Security & Sandboxing

K.R.Y.Z.E.N is designed with strict boundaries:
- **Sandbox Enforced**: Shell commands and code execution operate strictly within isolated Linux execution environments.
- **Zero Plaintext Secrets Committed**: Sensitive API keys and tokens are excluded from version control via `.gitignore`.
- **Privilege Separation**: System administration tasks require explicit configuration and controlled execution paths.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more details.

---

<p align="center">
  Built with precision. Designed for engineers who demand Swiss craftsmanship in autonomous AI.
</p>
