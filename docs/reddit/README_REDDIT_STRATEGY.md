# Reddit Launch Strategy & Guide for K.R.Y.Z.E.N

This guide outlines the optimal strategy for launching K.R.Y.Z.E.N across developer and AI subreddits to achieve organic reach, upvotes, GitHub stars, and community recognition.

---

## 1. Subreddit Priority & Schedule

Do **NOT** post all three at the exact same minute. Staggering prevents Reddit's cross-post spam filters from dampening reach:

| Subreddit | File | Recommended Time (UTC) | Flair | Key Focus |
| :--- | :--- | :--- | :--- | :--- |
| **`r/LocalLLaMA`** | `01-r-LocalLLaMA.md` | **01:00 PM – 03:00 PM UTC** (Day 1) | `Project` | Local models (Ollama/vLLM), context diet, Bubblewrap sandboxing |
| **`r/Python`** | `02-r-Python.md` | **02:00 PM – 04:00 PM UTC** (Day 2) | `Showcase` | Pure Python, asyncio event loop, clean dependencies, code snippet |
| **`r/ArtificialIntelligence`** | `03-r-ArtificialIntelligence.md` | **01:00 PM – 03:00 PM UTC** (Day 3) | `Project` or `Discussion` | Multi-agent systems, stage gates, avoiding hallucination doom-loops |

---

## 2. Reddit Submission Files in this Directory

* [`01-r-LocalLLaMA.md`](file:///home/kryazzy/Space/K.R.Y.Z.E.N/docs/reddit/01-r-LocalLLaMA.md): Ready-to-copy title and markdown for `r/LocalLLaMA`.
* [`02-r-Python.md`](file:///home/kryazzy/Space/K.R.Y.Z.E.N/docs/reddit/02-r-Python.md): Ready-to-copy title and markdown for `r/Python`.
* [`03-r-ArtificialIntelligence.md`](file:///home/kryazzy/Space/K.R.Y.Z.E.N/docs/reddit/03-r-ArtificialIntelligence.md): Ready-to-copy title and markdown for `r/ArtificialIntelligence`.

---

## 3. High-Conversion Tactical Tips

1. **Attach the Hero Visual:**
   * In your Reddit post, attach the visual GIF or screenshot (`docs/assets/tour.gif` or `docs/assets/screens/08-honeycomb-mesh.png`). Posts with rich preview images get **3x higher click-through rates**.
2. **First-Hour Engagement (The Golden Window):**
   * Reddit algorithms heavily weight early comment velocity. Monitor the thread during the first 60 minutes after posting.
   * Respond to every technical question with depth, humility, and code references.
3. **Handle Skeptics Professionally:**
   * In `r/LocalLLaMA`, people will ask: *"How is this different from CrewAI or AutoGen?"*
   * Answer: K.R.Y.Z.E.N uses a deterministic, sequential 6-stage honeycomb mesh with human-in-the-loop stage gates, unprivileged Linux Bubblewrap (`bwrap`) OS sandboxing, and token diet controls—avoiding prompt bloat and uncontrolled chaotic loops.
