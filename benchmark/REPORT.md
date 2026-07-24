# Whodunit benchmark — live results

_Generated 2026-07-24T18:44:08Z against the running SigNoz stack (localhost:8080). Total wall-clock **946.5s**._

## Bottom line

**6/6 scenarios pass.** Whodunit nails the flagship conjunctive fault the flat baseline cannot (`conditional_dep`: `(A => B) && NOT C`, recall 1.0, baseline top-feature precision 0.23); ties the baseline on the single-feature fault (`new_edge`); and takes the honesty path — calibrated ABSTAIN/PARTIAL, never a false culprit — on the inexpressible (`retry_storm`), the decoy trap (`decoys`), and the null cohort (`null_scenario`). It also recovers the pure trace-scoped absence (`cache_bypass`: `NOT cache-get`) that the flat baseline finds — the pipeline now anchors the absence to an always-present positive (`... && NOT cache-get`) so it compiles and verifies (recall 1.0, ISSUES.md #2 FIXED).

## Aggregate results

| scenario | expected | got | pass | precision@1 | label-recall | label-prec | abstain-ok | baseline-found | base prec/rec | wall-clock | rows | features |
|---|---|---|:--:|:--:|:--:|:--:|:--:|:--:|---|--:|--:|--:|
| `conditional_dep` | discriminator | **discriminator** | yes | yes | 1.00 | 1.00 | - | no | 0.23/1.00 | 147.60s | 162057 | 36 |
| `new_edge` | discriminator | **discriminator** | yes | yes | 1.00 | 1.00 | - | yes | 1.00/1.00 | 145.10s | 164955 | 36 |
| `cache_bypass` | discriminator | **discriminator** | yes | yes | 1.00 | 1.00 | - | yes | 1.00/1.00 | 107.40s | 142956 | 34 |
| `retry_storm` | abstain | **partial** | yes | - | 0.81 | 0.23 | yes | no | 0.21/0.99 | 139.10s | 180216 | 36 |
| `decoys` | abstain | **abstain** | yes | - | - | - | yes | no | 0.29/0.85 | 128.10s | 119884 | 35 |
| `null_scenario` | abstain | **abstain** | yes | - | - | - | yes | no | 0.14/0.77 | 136.20s | 164703 | 36 |

**6/6 scenarios passed.**

## Verification receipts (mined vs live SigNoz)

| scenario | mined | signoz | match | verdict headline |
|---|--:|--:|:--:|---|
| `conditional_dep` | 89 | 89 | yes | The culprit is WITH edge__shop_payment__redis_retry AND WITHOUT span__shop_flag_service__G |
| `new_edge` | 147 | 147 | yes | The culprit is WITH edge__shop_cart__inventory_sync (lift 5.4x) |
| `cache_bypass` | 160 | 160 | yes | The culprit is WITH edge__shop_cart__SELECT_cart_items AND WITHOUT edge__shop_cart__cache_ |
| `retry_storm` | 555 | 673 | no | A partial (below-confidence) signal: WITH dur__ge2204678_lt4504835 AND WITH dur__ge4504835 |
| `decoys` | - | - | - | ABSTAIN — no structural discriminator cleared every gate. The engine refuses to invent a c |
| `null_scenario` | - | - | - | ABSTAIN — no structural discriminator cleared every gate. The engine refuses to invent a c |

## Per-scenario detail

### `conditional_dep` — conditional_dep (seed 101)

- **Expected:** discriminator  **Got:** **discriminator**  **Pass:** yes
- **Winner itemset:** `edge__shop_payment__redis_retry AND NOT span__shop_flag_service__GET_flags_evaluate`
- **Compiled trace-operator:** `(A => B) && NOT C`
- **Matrix:** 89 bad / 711 healthy traces, 36 features, family size 7806, 89 bad ingested
- **Label metrics vs manifest:** recall 1.00, precision(in-corpus) 1.00
- **Flat baseline top pick:** `NOT edge__shop_checkout__GET_flags_evaluate` (z=10.44, prec 0.23, rec 1.00) -> found=no
- _Flagship: (payment => redis-retry) && NOT flag-service. No single predicate separates; only the conjunction does. Expect recall 1.0._

### `new_edge` — new_edge (seed 102)

- **Expected:** discriminator  **Got:** **discriminator**  **Pass:** yes
- **Winner itemset:** `edge__shop_cart__inventory_sync`
- **Compiled trace-operator:** `A => B`
- **Matrix:** 147 bad / 653 healthy traces, 36 features, family size 7806, 147 bad ingested
- **Label metrics vs manifest:** recall 1.00, precision(in-corpus) 1.00
- **Flat baseline top pick:** `edge__shop_cart__inventory_sync` (z=28.28, prec 1.00, rec 1.00) -> found=yes
- _New cart => inventory-sync edge post-deploy. Single-feature presence discriminator — the flat baseline should also find it._

### `cache_bypass` — cache_bypass (seed 203)

- **Expected:** discriminator  **Got:** **discriminator**  **Pass:** yes
- **Winner itemset:** `edge__shop_cart__SELECT_cart_items AND NOT edge__shop_cart__cache_get`
- **Compiled trace-operator:** `(A => B) && NOT (C => D)`
- **Matrix:** 160 bad / 640 healthy traces, 34 features, family size 6523, 160 bad ingested
- **Label metrics vs manifest:** recall 1.00, precision(in-corpus) 1.00
- **Flat baseline top pick:** `NOT edge__shop_cart__cache_get` (z=28.28, prec 1.00, rec 1.00) -> found=yes
- **Refusals surfaced:** NOT edge__shop_cart__cache_get: itemset is absence-only (all NOT); trace-operator expressions need a positive op; NOT span__shop_cache__cache_get: itemset is absence-only (all NOT); trace-operator expressions need a positive op; NOT svc__shop_cache: itemset is absence-only (all NOT); trace-operator expressions need a positive op
- _Bad traces miss the cache-get span entirely. Trace-scoped absence discriminator recovered as a positive-anchored superset (edge__shop_cart__SELECT_cart_items && NOT cache-get); compiles + verifies (ISSUES.md #2 FIXED)._

### `retry_storm` — retry_storm (seed 104)

- **Expected:** abstain  **Got:** **partial**  **Pass:** yes
- **Winner itemset:** `dur__ge2204678_lt4504835 AND dur__ge4504835_lt8111411 AND dur__ge893951_lt2204678`
- **Compiled trace-operator:** `(A && B) && C`
- **Matrix:** 157 bad / 643 healthy traces, 36 features, family size 7806, 157 bad ingested
- **Label metrics vs manifest:** recall 0.81, precision(in-corpus) 0.23
- **Flat baseline top pick:** `dur__ge893951_lt2204678` (z=3.98, prec 0.21, rec 0.99) -> found=no
- _2-5 redis-retry siblings vs 1: a CARDINALITY fault, inexpressible in the presence/absence algebra. redis-retry is present in BOTH cohorts. Correct = ABSTAIN/PARTIAL. A confident DISCRIMINATOR here is a FAILURE._

### `decoys` — decoys (seed 105)

- **Expected:** abstain  **Got:** **abstain**  **Pass:** yes
- **Matrix:** 117 bad / 683 healthy traces, 35 features, family size 7170, 117 bad ingested
- **Label metrics vs manifest:** recall -, precision(in-corpus) -
- **Flat baseline top pick:** `attr__tenant_tier__gold` (z=9.77, prec 0.29, rec 0.85) -> found=no
- **Refusals surfaced:** attr__tenant_tier__gold/dur__ge0_lt723266: column 'attr__tenant_tier__gold' carries no compilable predicate; attr__tenant_tier__gold/dur__ge0_lt723266/NOT attr__tenant_tier__free: itemset references a complement requiring span-level negation; the trace-scoped ; attr__tenant_tier__gold/dur__ge0_lt723266/NOT attr__tenant_tier__platinum: itemset references a complement requiring span-level negation; the trace-scoped ; attr__tenant_tier__gold/dur__ge0_lt723266/NOT attr__tenant_tier__silver: itemset references a complement requiring span-level negation; the trace-scoped 
- _tenant.tier=gold correlates ~85% with the bad label but does NOT cause it; plus high-cardinality noise. Correct = ABSTAIN. A DISCRIMINATOR on the decoy is a false culprit (FAILURE)._

### `null_scenario` — null_scenario (seed 106)

- **Expected:** abstain  **Got:** **abstain**  **Pass:** yes
- **Matrix:** 96 bad / 704 healthy traces, 36 features, family size 7806, 96 bad ingested
- **Label metrics vs manifest:** recall -, precision(in-corpus) -
- **Flat baseline top pick:** `NOT edge__shop_payment__redis_retry` (z=1.93, prec 0.14, rec 0.77) -> found=no
- _Nothing is wrong; only natural structural variation. We select a RANDOM 12% 'suspected' cohort (no structural cause) and require the engine to ABSTAIN rather than invent a culprit._

## Where the flat baseline wins or loses

The flat baseline ranks every *single* feature (presence and trace-scoped absence) by a two-proportion z-test and takes the top pick — no conjunctions, no algebra. Per the thesis:

- `conditional_dep`: baseline **FAILS** (top `NOT edge__shop_checkout__GET_flags_evaluate`, prec 0.23, rec 1.00).
- `new_edge`: baseline **WINS/TIES** (top `edge__shop_cart__inventory_sync`, prec 1.00, rec 1.00).
- `cache_bypass`: baseline **WINS/TIES** (top `NOT edge__shop_cart__cache_get`, prec 1.00, rec 1.00).
- `retry_storm`: baseline **FAILS** (top `dur__ge893951_lt2204678`, prec 0.21, rec 0.99).
- `decoys`: baseline **FAILS** (top `attr__tenant_tier__gold`, prec 0.29, rec 0.85).
- `null_scenario`: baseline **FAILS** (top `NOT edge__shop_payment__redis_retry`, prec 0.14, rec 0.77).

## Methods

**Corpus.** Each scenario emits a fresh, fully-disclosed synthetic corpus via
`corpus.generate` under a distinct seed (101-106), ~800 traces, spread over
0.01 h (~36 s) so a run's traces cluster tightly in time. The generator writes a
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
`tenant.tier` (the decoy trap); `order.completed`/`cache.hit` are dropped because they
mirror the label. Transitive-ancestor (`->`) features are off
(`include_ancestors=False`): the `WITH RECURSIVE` closure roughly doubles the
structural feature count and blows up the k=3 family, and the flagship
discriminator is a DIRECT (`=>`) edge that direct-edge features already capture.

**Mining config.** Pipeline defaults except `n_bootstrap=300` (down from 1000):
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

- **Pure-absence discriminators — recovered (`cache_bypass` passes, ISSUES.md #2
  FIXED).** When the only separator is a trace-scoped absence (`NOT cache-get`) the
  compiler soundly refuses the absence-only itemset (a `builder_trace_operator`
  needs a positive operand to return spans from), and the miner's MDL dominance
  prune drops the compilable positive-anchored superset (`anchor && NOT cache-get`)
  because it shares the minimal itemset's CI floor — so the naive pipeline
  ABSTAINed. The pipeline's `_select_finding` now closes this seam: when every
  surviving finding is compiler-refusable, it recovers the best *compilable*
  candidate from `near_misses` whose lift-CI floor ties the refused top tier
  (statistically equivalent, engineering choice favours executability — the same
  principle as the intra-tier tie-break). `cache_bypass` (seed 203) now returns a
  verified DISCRIMINATOR, `edge__shop_cart__SELECT_cart_items && NOT
  edge__shop_cart__cache_get`, recall 1.0 / precision 1.0, 160/160 live match. The
  sibling compiler and miner are left untouched; the fix is local to
  `whodunit.pipeline`.
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

