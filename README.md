# Whodunit

**Deterministic structural root cause whose output is a SigNoz query you own.**

> **STATUS: 🚧 Scaffolding.** Interfaces are frozen; the extractor, miner, and
> compiler land in Wave 2. Nothing below the MVP line is wired yet.

Whodunit points at a set of failing traces, auto-selects a case-control–matched
healthy cohort, mines the full itemset lattice for the span/edge/log patterns
that structurally separate them, and then **compiles the winning finding into a
valid SigNoz `builder_trace_operator` query** — verified against the live engine,
with precision/recall reported. No LLM anywhere. The deliverable is a Query
Builder artifact you own: a permalink, a dashboard panel, and an armed alert.

Tagline: *"Everyone can show you the difference. Only SigNoz can arm it."*

## Quickstart

```bash
# placeholder — full `whodunit explain` CLI lands in Wave 3
uv venv && uv pip install -e ".[dev]"
export SIGNOZ_URL=http://localhost:8080
export SIGNOZ_EMAIL=... SIGNOZ_PASSWORD=... SIGNOZ_ORG_ID=...
whodunit version
```

## Development

```bash
just lint    # ruff
just type    # mypy (strict, src only)
just test    # pytest
```

(or use the `make` equivalents: `make lint type test`)

## AI disclosure

This project was developed with AI assistance. Claude (Fable 5 and Opus 4.8,
via Claude Code) was used for research, repository scaffolding, and code
generation, with human review of all output. This disclosure is required by the
hackathon rules; AI is used only in *development*, never in the shipped product
(there is no LLM anywhere in Whodunit's runtime).

---

Built for the **Agents of SigNoz** hackathon, **Track 2 — Signals & Dashboards**.
