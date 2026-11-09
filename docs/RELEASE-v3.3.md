# K.R.Y.Z.E.N Release v3.3: Obscura V8 Engine & Autonomous Isolation

> **Release Date:** November 9, 2026  
> **Status:** Production Ready  
> **Test Suite:** 130/130 Passing  
> **Target Upstream:** [h4ckf0r0day/obscura](https://github.com/h4ckf0r0day/obscura)

---

## ⚡ Executive Summary

Release **v3.3** introduces **[Obscura](https://github.com/h4ckf0r0day/obscura)** as the primary headless browser automation engine for K.R.Y.Z.E.N. Obscura is an ultralight, Rust-native headless browser built on top of the V8 JavaScript engine. It completely eliminates the heavy memory footprint and startup latencies of full Chromium/Playwright bundles, dropping browser RAM usage from **250MB+ to ~30MB** while delivering sub-second cold starts, native DOM scraping, consistent TLS fingerprint impersonation, and tracker blocking.

In addition, Release v3.3 brings **Isolated Agent Box Staging** and **Branch-Per-Change Git Verification** directly into the Mission Control UI.

---

## 🚀 Key Features

### 1. Obscura Headless Browser Engine (Rust + V8 DOM)
- **Ultra-Low Memory Footprint:** Runs at ~30MB RAM per worker thread compared to 250MB–400MB for traditional Chromium processes (over **88% memory reduction**).
- **Sub-Second Cold Starts:** Near-instantaneous page initialization and rendering (<400ms end-to-end latency).
- **Stealth Mode & TLS Impersonation:** Built-in TLS fingerprint masking and tracker evasion without running full desktop Chrome.
- **Native Rendered Screenshots:** High-fidelity full-page PNG capture via `obscura fetch <url> -s <output.png>`.
- **Chrome DevTools Protocol (CDP) Server:** Built-in CDP WebSocket listener on port 9222 (`obscura serve`) compatible with Chrome DevTools Protocol 1.3 and Puppeteer/Playwright clients.
- **Model Context Protocol (MCP):** Native MCP server integration (`obscura mcp`) for agent context retrieval.

### 2. Mission Control AI UI Integration
- **Engine Selection:** Configure active browser engine directly under **Settings > Models & Architecture**:
  - `Auto`: Probes Obscura V8; seamlessly falls back to Agent-Browser if unavailable.
  - `Obscura (Rust V8 30MB)`: Enforces ultra-lightweight V8 automation.
  - `Agent-Browser (Chromium)`: Standard Chromium CDP runner.
- **Stealth Toggle:** One-click toggle for TLS impersonation and tracker blocking.
- **Live Diagnostics:** Interactive `⚡ Test Browser Engine` button providing live latency metrics, detected V8 versions, and memory footprint validation.

### 3. Isolated Agent Box & Branch-Per-Change
- **Isolated Staging:** Agents execute file modifications inside isolated sandbox directories (`.devpilot/isolated/<box_id>`) with cryptographic hash checking before atomic merges into production.
- **Dedicated Git Branching:** Each change is committed to an isolated branch (`agent/<slug>-<timestamp>`). Automated test gates verify the build, and the change is merged into `main`/`master` only after explicit user approval.

---

## 📊 Benchmark & Performance Comparison

| Metric | Chromium (Agent-Browser) | Obscura V8 (v0.2.6) | Advantage |
| :--- | :--- | :--- | :--- |
| **Idle Memory Footprint** | ~250MB – 400MB | **~30MB** | **88% less RAM** |
| **Cold Start Latency** | 1800ms – 3200ms | **<350ms** | **5x faster startup** |
| **Runtime Dependencies** | Node.js, npm, npx, libc++ | **Zero** (Static Rust Binary) | Clean standard system |
| **Screenshot Capture** | Multi-step CDP session | **1-shot native CLI** | Highly resilient |
| **Anti-Bot Stealth** | Requires plugin patches | **Built-in TLS impersonation** | Native evasion |

---

## 🛠️ Installation & Setup

### Prebuilt Binary (Recommended)
Download the official Obscura release asset and install to `/usr/local/bin`:

```bash
# Fetch and extract release v0.2.6
curl -fsSL https://github.com/h4ckf0r0day/obscura/releases/latest/download/obscura-x86_64-linux.tar.gz | sudo tar -xz -C /usr/local/bin/

# Ensure executable permissions
sudo chmod +x /usr/local/bin/obscura /usr/local/bin/obscura-worker

# Verify installation
obscura -V
# Output: obscura 0.2.6
```

### Build from Source via Cargo
```bash
cargo install --git https://github.com/h4ckf0r0day/obscura --bin obscura
```

---

## 🧪 Verification & Health Checks

Verify your Obscura installation using the live API endpoint:

```bash
# Check status
curl -s http://127.0.0.1:8770/api/browser/status | jq .

# Run live latency probe
curl -s -X POST http://127.0.0.1:8770/api/browser/test \
  -H "Content-Type: application/json" \
  -H "X-Jarvis: 1" -d '{}' | jq .
```

Run the unit and integration test suite:
```bash
python3 -m unittest agent/jarvis/tests/test_obscura.py
# 6 tests passed (0.136s)

python3 -m unittest discover -s agent/jarvis/tests
# 130 tests passed (8.063s)
```
