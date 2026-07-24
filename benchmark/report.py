"""Render benchmark/results.json into benchmark/REPORT.md."""
from __future__ import annotations


def _b(x: bool | None) -> str:
    return "yes" if x else ("no" if x is not None else "-")


def _f(x) -> str:
    return "-" if x is None else (f"{x:.2f}" if isinstance(x, float) else str(x))


def render_report(payload: dict) -> str:
    results = payload["results"]
    sc = payload.get("scan_config", {})
    L: list[str] = []
    L.append("# Whodunit benchmark — live results\n")
    L.append(f"_Generated {payload['generated_at']} against the running SigNoz "
             f"stack (localhost:8080). Total wall-clock "
             f"**{payload['total_wall_clock_s']}s**._\n")

    # ---- bottom line -------------------------------------------------------
    npass_pre = sum(1 for r in results if r["passed"])
    L.append("## Bottom line\n")
    L.append(f"**{npass_pre}/{len(results)} scenarios pass.** Whodunit nails the "
             "flagship conjunctive fault the flat baseline cannot (`conditional_dep`: "
             "`(A => B) && NOT C`, recall 1.0, baseline top-feature precision 0.23); "
             "ties the baseline on the single-feature fault (`new_edge`); and takes the "
             "honesty path — calibrated ABSTAIN/PARTIAL, never a false culprit — on the "
             "inexpressible (`retry_storm`), the decoy trap (`decoys`), and the null "
             "cohort (`null_scenario`). The one miss is `cache_bypass`: a pure trace-"
             "scoped absence (`NOT cache-get`) that the baseline finds but whodunit "
             "abstains on, because the compiler needs a positive anchor and the MDL "
             "prune drops the compilable anchored phrasing (ISSUES.md #2).\n")

    # ---- aggregate table ---------------------------------------------------
    L.append("## Aggregate results\n")
    L.append("| scenario | expected | got | pass | precision@1 | label-recall | "
             "label-prec | abstain-ok | baseline-found | base prec/rec | "
             "wall-clock | rows | features |")
    L.append("|---|---|---|:--:|:--:|:--:|:--:|:--:|:--:|---|--:|--:|--:|")
    npass = 0
    for r in results:
        npass += 1 if r["passed"] else 0
        basepr = (f"{_f(r['baseline_precision'])}/{_f(r['baseline_recall'])}"
                  if r["baseline_predicate"] else "-")
        L.append(
            f"| `{r['key']}` | {r['expected']} | **{r['got']}** | {_b(r['passed'])} | "
            f"{_b(r['precision_at_1']) if r['expected']=='discriminator' else '-'} | "
            f"{_f(r['label_recall'])} | {_f(r['label_precision'])} | "
            f"{_b(r['abstained_correctly'])} | {_b(r['baseline_found'])} | {basepr} | "
            f"{_f(r['wall_clock_s'])}s | {_f(r['rows_scanned'])} | {r['n_features']} |"
        )
    L.append(f"\n**{npass}/{len(results)} scenarios passed.**\n")

    # ---- verification receipts --------------------------------------------
    L.append("## Verification receipts (mined vs live SigNoz)\n")
    L.append("| scenario | mined | signoz | match | verdict headline |")
    L.append("|---|--:|--:|:--:|---|")
    for r in results:
        L.append(f"| `{r['key']}` | {_f(r['verify_mined'])} | {_f(r['verify_signoz'])} | "
                 f"{_b(r['verify_match'])} | {r['headline'][:90]} |")
    L.append("")

    # ---- per-scenario detail ----------------------------------------------
    L.append("## Per-scenario detail\n")
    for r in results:
        L.append(f"### `{r['key']}` — {r['fault']} (seed {r['seed']})\n")
        L.append(f"- **Expected:** {r['expected']}  **Got:** **{r['got']}**  "
                 f"**Pass:** {_b(r['passed'])}")
        if r["chosen_itemset"]:
            L.append(f"- **Winner itemset:** `{' AND '.join(r['chosen_itemset'])}`")
        if r["expression"]:
            L.append(f"- **Compiled trace-operator:** `{r['expression']}`")
        L.append(f"- **Matrix:** {r['n_bad']} bad / {r['n_healthy']} healthy traces, "
                 f"{r['n_features']} features, family size {r['family_size']}, "
                 f"{_f(r['ingested_bad'])} bad ingested")
        L.append(f"- **Label metrics vs manifest:** recall {_f(r['label_recall'])}, "
                 f"precision(in-corpus) {_f(r['label_precision'])}")
        L.append(f"- **Flat baseline top pick:** `{r['baseline_predicate']}` "
                 f"(z={_f(r['baseline_z'])}, prec {_f(r['baseline_precision'])}, "
                 f"rec {_f(r['baseline_recall'])}) -> found={_b(r['baseline_found'])}")
        if r["refusals"]:
            L.append(f"- **Refusals surfaced:** {'; '.join(r['refusals'])}")
        L.append(f"- _{r['notes']}_\n")

    # ---- baseline honesty section -----------------------------------------
    L.append("## Where the flat baseline wins or loses\n")
    L.append("The flat baseline ranks every *single* feature (presence and "
             "trace-scoped absence) by a two-proportion z-test and takes the top "
             "pick — no conjunctions, no algebra. Per the thesis:\n")
    for r in results:
        verdict = ("WINS/TIES" if r["baseline_found"] else "FAILS")
        L.append(f"- `{r['key']}`: baseline **{verdict}** "
                 f"(top `{r['baseline_predicate']}`, prec {_f(r['baseline_precision'])}, "
                 f"rec {_f(r['baseline_recall'])}).")
    L.append("")

    # ---- methods -----------------------------------------------------------
    mc = payload.get("mine_config", {})
    L.append(_METHODS.format(
        dur=payload.get("duration_hours_per_run"),
        logs=sc.get("include_logs"),
        attrs=", ".join(sc.get("attribute_keys", []) or ["-"]),
        anc=sc.get("include_ancestors"),
        nboot=mc.get("n_bootstrap"),
    ))
    return "\n".join(L) + "\n"


_METHODS = """## Methods

**Corpus.** Each scenario emits a fresh, fully-disclosed synthetic corpus via
`corpus.generate` under a distinct seed (101-106), ~800 traces, spread over
{dur} h (~36 s) so a run's traces cluster tightly in time. The generator writes a
manifest with machine-checkable ground truth and the exact bad-`trace_id` set;
its own self-check asserts the ground-truth spec selects exactly the bad labels
before emission. Emission uses the OTel-capable warmup-agent interpreter; the
pipeline runs under `uv run`.

**Windowing & contamination handling.** The shared stack already holds many other
`whodunit-demo` corpora. We discovered (and verified twice) that SigNoz's
`clickhouse_sql` query type **ignores the `start`/`end` window** — a 3-minute
window and a 1-year window return byte-identical rows (see `benchmark/ISSUES.md`
#1). Time-window scoping alone is therefore insufficient. Every corpus trace id
is a pure function of `(seed, index)`, so we reconstruct each run's COMPLETE id
set and hand explicit bad + healthy id sets to `run_scan` (whose
`trace_id IN (...)` scope genuinely restricts the scan). This makes extraction
and mining contamination-free; scoring against the manifest label set is robust
by construction. Verification's live `builder_trace_operator` count can still see
other corpora, so we report both the raw `signoz` count and a contamination-robust
`label-recall`/in-corpus `label-precision` computed from the operator's actual
matched id set intersected with this run's ids.

**Structural-only features.** `include_logs=False`. The corpus injects ERROR-level
log lines whose bodies literally name the fault (e.g. *"payment retry exhausted:
redis-retry issued while feature flags unavailable"*); mining those is
ground-truth leakage that would trivialise every scenario and, worse, hand
`retry_storm` a spurious perfect separator and defeat its abstention test. We test
STRUCTURAL discrimination — the blog's actual claim. Attributes are restricted to
`{attrs}` (the decoy trap); `order.completed`/`cache.hit` are dropped because they
mirror the label. Transitive-ancestor (`->`) features are off
(`include_ancestors={anc}`): the `WITH RECURSIVE` closure roughly doubles the
structural feature count and blows up the k=3 family, and the flagship
discriminator is a DIRECT (`=>`) edge that direct-edge features already capture.

**Mining config.** Pipeline defaults except `n_bootstrap={nboot}` (down from 1000):
the lift-CI bootstrap is ~10^9 pure-Python ops/scan at the default and dominates
wall-clock; 300 resamples leave `ci_low` (which drives every gate) unchanged to
2 d.p. for these clean separations. The harness is explicitly designed to sweep
`MineConfig`; every other knob is the shipped default.

**Baseline.** A properly-implemented BubbleUp-style flat ranker over the SAME
matrix: two-proportion z-test per single (feature, polarity), top pick by
bad-enrichment; "found" iff that single predicate meets the pipeline's own gate
(precision >= 0.80 AND recall >= 0.50).

**Metrics.** verdict correctness (vs expected); precision@1 (the winner is the
ground-truth structural separator: label-recall >= 0.99 and in-corpus
label-precision >= 0.99); label recall/precision of the compiled query vs the
manifest bad set; abstention correctness; false-culprit rate (a confident
DISCRIMINATOR where ground truth is abstain); wall-clock; rows scanned.

## Limitations

- **Pure-absence discriminators are lost (`cache_bypass` fails).** When the only
  separator is a trace-scoped absence (`NOT cache-get`), whodunit ABSTAINS: the
  compiler soundly refuses absence-only itemsets (a `builder_trace_operator` needs
  a positive operand to return spans from), and the miner's MDL dominance prune
  discards the compilable positive-anchored superset (`db-span && NOT cache-get`)
  because it shares the minimal itemset's CI floor. So a fault that *is*
  expressible in the algebra is missed, and here the flat baseline beats whodunit.
  This is a real limitation (design seam between miner prune and compiler anchor
  rule), documented with a repro and a local fix suggestion in `ISSUES.md` #2.
- **Repetition faults are inexpressible.** `retry_storm` is a per-trace
  cardinality regression (2-5 vs 1 redis-retry). The presence/absence trace
  algebra has no cardinality qualifier, so the honest answer is ABSTAIN/PARTIAL,
  not a fabricated presence discriminator. The benchmark scores this as the
  honesty path; a confident DISCRIMINATOR is counted a FAILURE. Whodunit returned
  PARTIAL on a latency-bucket symptom (in-corpus precision 0.23) — surfaced, not
  claimed as a culprit.
- **Scale is small** (~800 traces/run) to keep the live loop fast; the statistics
  are calibrated for this regime but larger corpora would tighten CIs.
- **Synthetic, disclosed data.** All traffic is generated and labelled by
  `corpus.generate`; ground truth comes from the manifest, not human judgement.
  This is a methodology strength (exact labels) and a caveat (no real-world
  messiness beyond the injected decoys/noise).
- **Platform window bug.** Because `clickhouse_sql` ignores the time window, this
  harness leans on trace-id-set scoping rather than time scoping; on a clean
  single-tenant stack, time-window scoping would suffice.
"""
