# Statistical notes — what's solid, and what I'd sharpen next

The mining core is deliberately conservative (enumerate the whole family *before*
testing, gate on effect size before significance, treat abstention as a first-class
outcome, and back every verdict with a live differential check). Two independent
review passes confirmed the mechanics that matter are correct: the FP-growth
enumeration (cross-checked against brute force), the Fisher/χ² p-values, the BH
step-up with the full-family denominator, and trace-level resampling.

This note records, in the open, the refinements a stats-literate reviewer would
rightly ask about. They are **deferred, not overlooked** — each changes the reported
numbers, so applying it means re-running the six-scenario benchmark against a live
stack and regenerating `benchmark/REPORT.md`. They do not affect the flagship
verdict (`conditional_dep` separates 61/0 — significant under any of these).

### 1. Effect measure: report the odds ratio alongside lift

`lift = P(bad | present) / P(bad)` uses `P(bad) = n_bad / n`, which in a matched
case-control sample is **fixed by the sampling ratio** (default 4:1 → `P(bad)=0.2`),
so lift is capped at `1/P(bad)` and rescales if you change the healthy:bad ratio.
The **odds ratio** (`a·d / b·c`) is invariant to that ratio and is the correct
effect measure for a case-control design. Plan: report the odds ratio (with a
stratified-bootstrap CI) as the headline effect and keep lift as an in-sample
descriptor. Until then, read every "N× lift" as *in-sample at the 4:1 matching
ratio*, not a population risk ratio.

### 2. FDR under negative dependence: BH → Benjamini–Yekutieli

The tested family contains, for each feature, both `f` and `NOT f` (perfectly
negatively dependent) plus nested conjunctions — not an independent or PRDS family,
which is what plain Benjamini–Hochberg assumes. Benjamini–Yekutieli (the `×Σ1/i`
variant) guarantees FDR control under *arbitrary* dependence. BY is uniformly more
conservative, so it only strengthens the "abstain on decoys/null" claims; it can
change borderline verdicts, hence the re-validation requirement.

### 3. Matching variable: root-span vs whole-trace duration

The duration stratum currently matches on `max(duration_nano)` over the trace. For a
latency/retry fault that *inflates* trace duration, matching on it is overmatching
(conditioning on a mediator) and can balance the signal away — a contributor to the
`retry_storm` abstain. Plan: match on **root-span** duration (a pre-fault baseline),
or make duration matching opt-in with a documented caveat.

### 4. Minority-cohort faults: lower the support floor (with care)

The enumeration floor and the tolerance gate are now pinned to the same fraction
(`min_support_frac_bad`, default 0.5), so nothing is silently unreachable — but that
also means a fault present in a *minority* of the bad cohort (< 50%) is not mined.
Lowering both together widens coverage at the cost of a larger family (and a larger
BH denominator); it's a deliberate, re-validated change, not a default.

### Not deferred — already fixed

- **Determinism.** The final scan now emits `ORDER BY trace_id` and the cohort
  sampler sorts strata and pools before drawing, so the seeded bootstrap and the
  matched cohort — and thus the verdict hash — are reproducible across processes and
  across ClickHouse's otherwise-unordered scans. Regression tests shuffle the input
  order and assert an identical cohort (`tests/extract/test_cohort.py`).
- **Empty-result verification** no longer raises on a legitimately-empty
  discriminator (returns 0); pagination no longer truncates on an empty page that
  still carries a next cursor.
