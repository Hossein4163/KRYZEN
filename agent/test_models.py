#!/usr/bin/env python3
"""List and live-test every chat model on NVIDIA NIM and Google Gemini.

Keys come from env vars NVIDIA_API_KEY / GEMINI_API_KEY, or from agent/.keys.env
(lines KEY=value, keep it chmod 600). Each model gets a tiny prompt plus a
tool-calling test (the n8n agents need tool calling). Results: models_report.md
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
NIM = "https://integrate.api.nvidia.com/v1"
GEM = "https://generativelanguage.googleapis.com/v1beta"
SKIP = ("embed", "rerank", "reward", "guard", "safety", "parse", "clip", "retriever", "nv-dino", "vila",
        "deplot", "kosmos", "neva", "paligemma", "fuyu", "imagen", "veo", "tts", "aqa", "audio", "-image")
TOOL = {"name": "get_weather", "description": "Get weather for a city",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}


def load_keys():
    f = HERE / ".keys.env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"\''))
    return os.environ.get("NVIDIA_API_KEY", ""), os.environ.get("GEMINI_API_KEY", "")


def call(url, body=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"[:200]


def short_err(code, data):
    msg = data if isinstance(data, str) else json.dumps(data)
    return f"HTTP {code}: {msg[:120]}".replace("\n", " ").replace("|", "/")


def test_nim(key, model):
    h = {"Authorization": f"Bearer {key}"}
    t = time.time()
    code, d = call(f"{NIM}/chat/completions", {"model": model, "max_tokens": 64, "temperature": 0,
                   "messages": [{"role": "user", "content": "Reply with exactly: OK"}]}, h)
    if code != 200:
        return model, False, False, 0, short_err(code, d)
    latency = time.time() - t
    code, d2 = call(f"{NIM}/chat/completions", {"model": model, "max_tokens": 256, "temperature": 0,
                    "tools": [{"type": "function", "function": TOOL}], "tool_choice": "auto",
                    "messages": [{"role": "user", "content": "What's the weather in Paris? Use the tool."}]}, h)
    tools = code == 200 and bool(d2["choices"][0]["message"].get("tool_calls"))
    text = (d["choices"][0]["message"].get("content") or "").strip()[:40]
    return model, True, tools, latency, text


def test_gemini(key, model):
    url = f"{GEM}/{model}:generateContent?key={key}"
    t = time.time()
    code, d = call(url, {"contents": [{"parts": [{"text": "Reply with exactly: OK"}]}]})
    if code != 200:
        return model, False, False, 0, short_err(code, d).replace(key, "***")
    latency = time.time() - t
    code, d2 = call(url, {"contents": [{"parts": [{"text": "What's the weather in Paris? Use the tool."}]}],
                          "tools": [{"functionDeclarations": [TOOL]}]})
    tools = code == 200 and any("functionCall" in p for c in d2.get("candidates", [])
                                for p in c.get("content", {}).get("parts", []))
    parts = d.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
    return model, True, tools, latency, (parts[0].get("text") or "").strip()[:40]


def run(label, fn, key, models, workers):
    print(f"\n{label}: testing {len(models)} models…", flush=True)
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(lambda m: fn(key, m), models))
    rows.sort(key=lambda r: (not r[1], not r[2], r[3]))
    ok = [r for r in rows if r[1]]
    lines = [f"## {label} — {len(ok)}/{len(rows)} working, {sum(r[2] for r in rows)} with tool calling", "",
             "| Model | Works | Tools | Latency | Reply / error |", "|---|---|---|---|---|"]
    lines += [f"| `{m}` | {'✅' if w else '❌'} | {'✅' if tl else '—'} | {f'{lat:.1f}s' if w else ''} | {txt} |"
              for m, w, tl, lat, txt in rows]
    print("\n".join(lines[:4]))
    for m, w, tl, lat, _ in ok:
        print(f"  {'TOOLS' if tl else 'chat '}  {lat:5.1f}s  {m}")
    return "\n".join(lines)


def main():
    nim_key, gem_key = load_keys()
    if not (nim_key or gem_key):
        sys.exit("Set NVIDIA_API_KEY and/or GEMINI_API_KEY (env or agent/.keys.env)")
    report = [f"# Model test — {time.strftime('%Y-%m-%d %H:%M')}"]
    if nim_key:
        code, d = call(f"{NIM}/models", headers={"Authorization": f"Bearer {nim_key}"})
        if code != 200:
            report.append(f"## NVIDIA NIM\nCould not list models: {short_err(code, d)}")
        else:
            ids = sorted(m["id"] for m in d["data"] if not any(s in m["id"].lower() for s in SKIP))
            report.append(run("NVIDIA NIM", test_nim, nim_key, ids, 8))
    if gem_key:
        code, d = call(f"{GEM}/models?pageSize=1000&key={gem_key}")
        if code != 200:
            report.append(f"## Google Gemini\nCould not list models: {short_err(code, d).replace(gem_key, '***')}")
        else:
            ids = sorted(m["name"] for m in d["models"]
                         if "generateContent" in m.get("supportedGenerationMethods", [])
                         and not any(s in m["name"].lower() for s in SKIP))
            report.append(run("Google Gemini", test_gemini, gem_key, ids, 4))
    out = HERE / "models_report.md"
    out.write_text("\n\n".join(report) + "\n")
    print(f"\nFull table: {out}")


if __name__ == "__main__":
    main()
