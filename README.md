# Whodunit

**Deterministic structural root-cause analysis whose output is a SigNoz query you own.**

> *Everyone can show you the difference between two sets of traces. Only SigNoz can arm it.*

![Whodunit mines the structural discriminator, then compiles and verifies it as a SigNoz trace-operator query](docs/assets/hero.gif)

<sub>**Real run (seed 778):** 7,806 candidate itemsets in one scan → the conjunction `(payment ⇒ redis-retry) ∧ ¬ flag-service` wins at **13.1× lift** → compiled to `(A ⇒ B) && NOT C` → **mined 61, SigNoz returned 61, MATCH**. No LLM in the runtime.</sub>

![ci](https://img.shields.io/badge/ci-passing-brightgreen)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![tests](https://img.shields.io/badge/tests-131%20passing-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)
![track](https://img.shields.io/badge/SigNoz%20hackathon-Track%202-orange)

> **▶ Live replay** — step through the real run in your browser (no install):
> `https://<username>-whodunit-replay.hf.space` *(deploy `replay/`, see [`replay/DEPLOY.md`](replay/DEPLOY.md))*

---

Point Whodunit at a set of failing traces. It matches a healthy cohort, mines the span /
edge / log patterns that structurally separate the two, **compiles the winner into a valid
`builder_trace_operator` query**, verifies that query against the live engine, and arms it
as an alert. The deliverable is never a paragraph — it is a Query Builder artifact you own.

Every product in this space (BubbleUp, Datadog Trace Patterns, Chronosphere DDx, Grafana
`compare()`) stops at a ranking you re-type by hand. Whodunit closes the loop. It's the
implementation of [SigNoz/signoz#1957](https://github.com/SigNoz/signoz/issues/1957)
— *"compare 2 sets of filtered spans"*, opened by co-founder pranay01 in Jan 2023, still open.

## How it works

![extract → mine → compile → verify → materialize](docs/assets/flow-pipeline.png)

Five stages, **no LLM in any of them** — same input + seed → same verdict hash. One
`clickhouse_sql` scan builds the trace×feature matrix (case-control matched); FP-growth
mines the full lattice with valid FDR and calibrated abstention; the compiler emits a valid
trace-operator envelope; verify runs it via `/api/v5/query_range` and asserts the count
matches; materialize ships the permalink, panel, and alert.

## How it uses SigNoz

![Whodunit reads ClickHouse + /api/v5, writes Trace Explorer, Dashboard, Alert](docs/assets/flow-signoz.png)

Not a tool that *sends data to* SigNoz — it reads, computes against, and writes back into
**all five surfaces**:

| Surface | Use |
|---|---|
| **Traces + Logs** | One `clickhouse_sql` scan joins traces⋈logs by `trace_id` — a cross-signal join impossible on Tempo+Loki (separate stores). |
| **Query Builder** | Output is a first-class `builder_trace_operator` expression, verified via `/api/v5/query_range`. |
| **Dashboards** | The discriminator is emitted as a native Perses **v6** panel. |
| **Alerts** | Armed as a **v2alpha1** WARN/CRIT rule; a fired webhook was caught end-to-end at **t+182s**. |
| **Foundry** | `deploy/casting.yaml` installs SigNoz **+** the MCP server in one command. |

## Quickstart

```bash
foundryctl cast -f deploy/casting.yaml          # 1. stand up SigNoz + MCP
python -m corpus.generate --traces 800 --seed 778 \
    --fault conditional_dep --endpoint http://localhost:4318   # 2. seed a demo fault
whodunit explain --from-manifest corpus/out/manifest-<runid>.json   # 3. mine → compile → verify
```

Add `--arm` (live alert), `--dashboard` (v6 panel), or `--json`. Run `cast` on a clean host —
the dev stack already holds `:8080`/`:4318`. See [`docs/DEMO-RUNBOOK.md`](docs/DEMO-RUNBOOK.md).

## The verified result

```
(A => B) && NOT C   returnSpansFrom = A      ← the compiled discriminator
mined 61  |  SigNoz 61  |  MATCH  |  precision 1.00  |  recall 1.00
```

The compiled query is run back against SigNoz and asserted equal to the local count. A match
means the synthesised query means what the miner thought; a mismatch is **reported, never
hidden**. That receipt is the honesty mechanism.

## Benchmark — 6/6, with an honest baseline

Six scenarios, run live, scored against a ground-truth manifest, versus a properly-implemented
BubbleUp-style flat baseline ([`benchmark/REPORT.md`](benchmark/REPORT.md)):

| scenario | whodunit | flat baseline |
|---|---|---|
| `conditional_dep` (conjunction) | **discriminator** ✓ | **fails** (0.23 prec) |
| `new_edge`, `cache_bypass` (single-feature) | **discriminator** ✓ | ties |
| `retry_storm` (N+1, inexpressible) | partial ✓ | fails |
| `decoys`, `null_scenario` | **abstain** ✓ | fails |

Whodunit nails the conjunction flat tools can't see, ties on their home turf (single-feature
faults — reported honestly), and abstains rather than inventing a culprit. Never a false culprit.

## Notes

- **Engine constraints** the compiler respects (operator left-bias + `=>`/`->` direction,
  documented in [#10025](https://github.com/SigNoz/signoz/issues/10025); trace-scoped `NOT`;
  time-window handling) are enforced by the compiler and surfaced by the differential receipt —
  details in [`compile/ENGINE-NOTES.md`](src/whodunit/compile/ENGINE-NOTES.md).
- **Limits:** N+1/repetition faults are inexpressible in the algebra (Whodunit abstains);
  pure-absence needs a positive anchor. The demo corpus is **synthetic + disclosed** —
  ground truth from a manifest, not human judgement.
- **AI disclosure:** developed with AI assistance (Claude Code); **no LLM in the runtime**.
- **Dev:** `just lint · type · test` (ruff, mypy strict, 131 tests). MIT licensed.

---

Built for the **Agents of SigNoz** hackathon, **Track 2 — Signals & Dashboards**.
