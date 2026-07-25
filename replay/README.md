---
title: Whodunit Replay
emoji: 🔎
colorFrom: green
colorTo: gray
sdk: static
pinned: false
---

# Whodunit — Interactive Replay (seed 778)

A polished, fully-offline single-page replay of a **real recorded run** of
[Whodunit](https://github.com/wiz-abhi/WhodUnit) against live SigNoz v0.132.2.

> Everyone can show you the difference. **Only SigNoz can arm it.**

This is the "Deployed link" for the Agents of SigNoz hackathon submission
(Track 2 — Signals & Dashboards). It steps a judge through the full pipeline —
**point → extract + mine → compile → verify → materialize → determinism →
benchmark** — with every number read from the committed run at
`docs/video/raw/explain-result.json` (seed 778):

- 7,806 candidate itemsets · 36 features · **6 survivors**
- winner `(payment ⇒ redis-retry) && NOT flag-service` · lift **13.1×** · CI [10.8, 17.2] · bad 61 / healthy 0
- compiled `(A ⇒ B) && NOT C`, returnSpansFrom = A
- verified: **mined 61 · SigNoz 61 · MATCH · precision 1.00 · recall 1.00**
- verdict hash `95f8835759e2865ec90f17b45df7f1f74f9944484bad4f014e0f209826f91fb5`

## It is honest by construction

- **No live SigNoz required.** The run is replayed from committed data — nothing
  is fabricated for the demo.
- **No LLM in the runtime.** Whodunit is a deterministic synthesis engine; the
  "Run again" button re-shows the identical verdict hash.
- **Self-contained.** HTML + CSS + vanilla JS, no CDN, no external fonts, no
  network requests. The real data lives in `data/`; screenshots in `assets/`.

## Contents

| Path | What it is |
|---|---|
| `index.html` | the entire app (self-contained) |
| `data/explain-result.json` | the committed seed-778 run — source of every number |
| `data/webhook.log` | the real firing-alert webhook body |
| `data/permalink.txt` | the real Trace Explorer deep-link |
| `assets/*.png` | real screenshots (board, benchmark, operator-probe, alert-firing) |
| `DEPLOY.md` | exact steps to host on Hugging Face Spaces |

## Run locally

```bash
cd replay
python -m http.server 8000
# open http://localhost:8000
```

Or just open `index.html` directly — it works over `file://` too (no fetch).

See [`DEPLOY.md`](DEPLOY.md) to publish it as a Hugging Face static Space.
