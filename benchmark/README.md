# Whodunit benchmark

Live, reproducible benchmark of the whodunit pipeline against a running SigNoz
stack. For each of six scenarios it emits a fresh synthetic corpus, waits for
ingestion, runs the full pipeline (`extract -> mine -> compile -> verify`) plus a
flat-attribute baseline, and scores both against the corpus manifest's
machine-checkable ground truth.

## Prerequisites

- A running SigNoz stack: UI `http://localhost:8080`, OTLP/HTTP `:4318`.
- The repo venv (managed by `uv`) — runs the pipeline.
- The OTel-capable interpreter for the emitter (the repo venv lacks the OTel SDK).
  The corpus deps are pinned in `corpus/REQUIREMENTS.txt`; this harness uses
  `C:\Users\abhis\Desktop\OSS\Signoz\warmup-agent\.venv\Scripts\python.exe`,
  which already has them. Point `WARMUP_PY` in `run.py` at any interpreter that
  satisfies `corpus/REQUIREMENTS.txt` if yours differs.

## Credentials (env only — never committed)

```bash
export SIGNOZ_EMAIL=user.abhishek2004@gmail.com
export SIGNOZ_PASSWORD='SigNoz@Warmup2026'
export SIGNOZ_ORG_ID=019f5768-e00c-7dc4-9376-b2b4a44c5e55
```

## Run

```bash
# all six scenarios (~12-18 min against a warm stack)
uv run python benchmark/run.py

# a subset
uv run python benchmark/run.py conditional_dep retry_storm
```

Outputs:
- `benchmark/results.json` — raw per-scenario metrics.
- `benchmark/REPORT.md` — the rendered aggregate table + methods + limitations.
- `corpus/out/manifest-*.json` — the ground-truth manifest for each emitted run.

## What each file does

- `run.py` — orchestrator: emit -> poll ingestion -> score -> render.
- `scenarios.py` — the six scenario definitions and their expected verdicts.
- `pipeline_scoped.py` — contamination-robust driver: reconstructs each run's
  complete trace-id set and hands explicit bad + healthy sets to the *real*
  engine functions (`run_scan`/`mine`/`compile_finding`/`verify`). See
  `ISSUES.md` #1 for why time-window scoping alone is insufficient here.
- `baseline.py` — the flat BubbleUp-style single-feature z-test baseline.
- `report.py` — renders `results.json` into `REPORT.md`.

## Reproducibility notes

- Every corpus run is deterministic in its seed (101-106); the same seed yields
  identical trace ids, cohorts, and manifest.
- The pipeline is deterministic given the matrix + mining seed; `verdict_hash`
  in the `ExplainResult` is the run-twice-identical proof.
- Because the stack is shared and multi-tenant, absolute `signoz` verification
  counts can include other corpora; the scored metrics are the
  contamination-robust `label-recall` / in-corpus `label-precision` derived from
  the compiled query's actual matched id set. See `ISSUES.md`.
