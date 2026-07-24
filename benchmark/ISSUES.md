# Benchmark ISSUES log

Issues surfaced while building/running the benchmark. Per the brief, pipeline
bugs are documented here (file, symptom, repro) rather than fixed in
sibling-owned code; the benchmark works around them and continues.

---

## #1 — SigNoz `clickhouse_sql` ignores the query time window (PLATFORM, not whodunit)

**Severity:** high (drives the whole contamination-handling design).

**Symptom.** The v5 `clickhouse_sql` query type does not apply the envelope's
`start`/`end` bounds. A 3-minute window, a 10-minute window, and a 1-year window
return byte-identical results.

**Repro** (against the live stack, env creds set):

```python
from whodunit.signoz_client import SigNozClient
from whodunit.extract.sql import run_clickhouse_sql
import time
now = int(time.time()*1000)
sql = ("SELECT count() n, min(toUnixTimestamp64Milli(timestamp)) mn, "
       "max(toUnixTimestamp64Milli(timestamp)) mx "
       "FROM signoz_traces.distributed_signoz_index_v3 "
       "WHERE resources_string['deployment.environment']='whodunit-demo'")
with SigNozClient() as c:
    c.login()
    print("3min:", run_clickhouse_sql(c, sql, now-180_000, now))
    print("1yr :", run_clickhouse_sql(c, sql, now-365*24*3600*1000, now))
# both rows identical: same count, same min/max timestamp — window not applied.
```

**Impact on whodunit.** `whodunit.extract.cohort._fetch_trace_rows` and
`whodunit.extract.scan.*` build the cohort/scan via `clickhouse_sql`, relying on
the window to bound the frame. On a shared stack this pulls *other* corpora into
the healthy cohort/vocabulary (the "SigNoz 330 vs mined 55" inflation noted in
prior runs).

**Whose bug.** SigNoz's `clickhouse_sql` handler (the user's SQL is expected to
carry its own time predicate; the envelope window is not injected). Not a
whodunit code defect, but whodunit's extract layer assumes the window binds.

**Workaround in this benchmark.** Scope by explicit trace-id SETS instead of
time. Corpus trace ids are `f(seed, index)`, so we reconstruct each run's full id
set and pass explicit bad + healthy id lists to `run_scan` (whose
`trace_id IN (...)` scope genuinely restricts the scan). Verification's live
`builder_trace_operator` count can still see other corpora, so scored metrics use
contamination-robust label-recall / in-corpus label-precision from the operator's
matched id set. See `benchmark/pipeline_scoped.py` and REPORT.md Methods.

**Suggested fix (for the extract layer, out of scope here).** Inject a
`timestamp BETWEEN {start} AND {end}` predicate into every generated
`clickhouse_sql` body rather than relying on the envelope window.

---

## #2 — Pure-absence discriminators are lost: absence-only refusal + dominance prune (WHODUNIT)

**Severity:** medium (one benchmark scenario, `cache_bypass`, fails because of it).

**Symptom.** On `cache_bypass` — where bad traces are exactly those *missing* the
`cache-get` span (a sound, trace-scoped absence) — whodunit **ABSTAINS** even
though a valid trace-scoped `NOT cache-get` discriminator exists and the flat
baseline finds it at precision=recall=1.0. The compiled result is empty and the
refusals list reads:

```
NOT edge__shop_cart__cache_get : itemset is absence-only (all NOT); trace-operator
                                 expressions need a positive operand to return spans from
NOT span__shop_cache__cache_get: (same)
NOT svc__shop_cache            : (same)
```

**Root cause (two engines interacting).**
1. `src/whodunit/compile/emit.py::build_ir` (and `ir.py`) soundly refuse an
   *absence-only* itemset: a `builder_trace_operator` expression needs a positive
   operand for `returnSpansFrom`, so `NOT C` alone cannot be emitted. Correct in
   isolation.
2. `src/whodunit/mine/rank.py::dominance_prune` (MDL) drops any superset that
   fails to beat its best subset's CI floor by `dominance_margin` (default 0.0).
   The minimal itemset `{NOT cache-get}` and the *compilable* positive-anchored
   superset `{svc__shop_db, NOT cache-get}` (db spans exist in every trace, so
   the superset separates identically) share the same CI floor, so the superset
   is pruned as "not paying for its extra bit."
3. Net: the only survivor is the absence-only `{NOT cache-get}`, which the
   compiler then refuses -> `_select_finding` returns nothing -> ABSTAIN.

So a fault that IS expressible in the algebra (trace-scoped `A && NOT C` with any
always-present anchor `A`) is missed: the miner's parsimony prune discards the
one phrasing the compiler can emit.

**Repro.** `uv run python benchmark/run.py cache_bypass` (env creds set). Expected
per the manifest: a compilable `NOT cache-get` discriminator (recall 1.0).
Observed: verdict ABSTAIN, three absence-only refusals, baseline finds it.

**Whose bug.** A design seam between two sibling engines (miner prune vs compiler
anchor requirement); neither is wrong alone. Not fixed here (sibling-owned).

**Suggested fix (out of scope).** Either (a) in the pipeline's `_select_finding`,
when the top finding is absence-only and refused, retry with a minimal
always-present positive anchor injected (`A && NOT C`); or (b) exempt an
absence-only itemset from dominance pruning when a positive-anchored superset with
an equal CI floor exists and is compilable. Option (a) is local to
`whodunit.pipeline` and would not touch sibling code.

---

## #3 — retry_storm surfaces a duration *symptom* as PARTIAL (expected, not a bug)

**Severity:** informational.

`retry_storm` is inexpressible (a per-trace cardinality regression). Whodunit
correctly does **not** emit a confident DISCRIMINATOR; it returns **PARTIAL** on a
latency-bucket conjunction (the extra retries make bad traces slower), with
in-corpus precision 0.23 — i.e. surfaced honestly as a below-confidence symptom,
not a claimed culprit. This is the intended honesty path (ABSTAIN/PARTIAL both
accepted). Noted only so the PARTIAL verdict + the 555-vs-673 verification
mismatch (contamination, issue #1) are not mistaken for a false positive.
