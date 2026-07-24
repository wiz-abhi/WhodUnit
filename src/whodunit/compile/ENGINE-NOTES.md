# Compiler engine notes — verified trace-operator semantics

Empirical findings from probing the live SigNoz stack (`v0.132.x`,
`http://localhost:8080`, corpus `deployment.environment = 'whodunit-demo'`,
500 traces). These pin the compiler's lowering. Cross-referenced with
`Track2/probe-results/PROBES.md` (probes agent) and independently re-confirmed by
this agent's own probes.

## 1. Operator mapping (BLOCKER-class — the concept doc is flipped)

On the live engine:

| Operator | Meaning | Corpus check |
|---|---|---|
| `=>` | **DIRECT**, single-hop descendant | `rootWrap => childOp` (2 hops) = **0** |
| `->` | **INDIRECT**, any-depth descendant | `rootWrap -> childOp` (2 hops) = **20** |

So EDGE features (direct parent→child) compile to `=>`; ANCESTOR features
(transitive) compile to `->`. `WHODUNIT-CONCEPT.md` §4.5 states the reverse
("`->` is direct descendant … `=>` is indirect") — it is **wrong**. This module
and the brief's constraint list are right; `PROBES.md` PROBE 2 is authoritative.
Emitting the wrong token makes every multi-level discriminator silently return 0.

`ir.py` encodes: `FeatureKind.EDGE -> OP_DIRECT ("=>")`,
`FeatureKind.ANCESTOR -> OP_INDIRECT ("->")`.

## 2. Count scoping — trace vs span (resolves the open question)

Operator results are **span-scoped**: one row per returned span from the
`returnSpansFrom` operand. To get a trace count you must aggregate
`count_distinct(trace_id)`.

Verified on the ground-truth conjunction:

| Aggregation | `(P => Q) && NOT C` | interpretation |
|---|---|---|
| `count()` | **118** | spans returned (span scope) |
| `count_distinct(trace_id)` | **55** | distinct traces (trace scope) — **ground truth** |

The compiler therefore **always** emits `count_distinct(trace_id)` in the
verification companion scalar. Raw `count()` would silently over-count.

## 3. `returnSpansFrom` and directionality (the "left-bias")

`returnSpansFrom` explicitly names which operand's spans are returned (probes:
`A => B` returned 40 A-spans; returning from `B` gave 80 B-spans). For a
trace-scoped `count_distinct(trace_id)` the *count* is identical regardless of
operand (the trace set is the same — verified: returning from P vs Q both gave
55), but the returned **spans** differ, so the Trace Explorer permalink and any
span-level consumer need the outcome-bearing operand named. The compiler
normalises the outcome/anchor operand to the **left** and sets `returnSpansFrom`
to that subtree's leftmost leaf.

Operand order is **directional**, not a mere bias: `B => A` = 0 where
`A => B` = 276. The normaliser never reorders the two sides of a `=>`/`->`
(that would change meaning); it only decides which positive fragment is the
left-most overall and pushes negations to the right of `&&`.

## 4. Trace-scoped `NOT`, and why absence-only itemsets are refused

`NOT` lowers to `GLOBAL NOT IN (SELECT trace_id …)` — trace-scoped. "This trace
contains no `C` span anywhere" compiles soundly. "This span is not accompanied
by `C`" (span-scoped) does not, and is **refused** (`refuse.REASON_SPAN_NEGATION`)
whenever `FeatureColumn.requires_span_level_negation` is set.

A **bare** `NOT C` is degenerate: the conformance suite measured operator
`count_distinct(trace_id)` = **0** for `NOT C` while 217 traces genuinely lack
`C`. With no positive operand there are no spans to return, so the trace set is
empty. The compiler therefore refuses absence-only itemsets (they have no
positive anchor to return spans from). This is documented, not hidden.

## 5. Denominator leaves are skipped from independent execution

Leaves referenced by an operator are not executed independently, so the anchor
feature's own count (the contingency denominator) needs a **separately-named**
duplicate leaf. `emit.py` appends `<ret>Denom` (a `count_distinct(trace_id)`
leaf duplicating the return operand's filter). It also carries the base-cohort
filter so the denominator is cohort-scoped.

## 6. `trace` request type for precision/recall (an emit gotcha)

To fetch the operator's matched `trace_id` set (for precision/recall) use
`requestType: "trace"`. Two things break a naive reuse of the scalar envelope:

1. Scalar-only siblings (the `count_distinct` denominator has no `LIMIT`) make
   ClickHouse emit `LIMIT expression must be constant … Actual: ''`. Fix: keep
   only the operator and the leaves it references by name.
2. A lingering scalar `aggregations` on the operator triggers the same
   empty-`LIMIT` CTE. Fix: drop `aggregations`, add `selectFields:[trace_id]`,
   `limit ≤ 10000`, and an `order`. Paginate via `nextCursor`.

Verified: the ground-truth query returns exactly **55** distinct trace_ids.

## 7. Response shapes (for parsing)

* Scalar: `data.data.results[i].data[0][0]` = aggregation value;
  `data.meta.rowsScanned` = cost.
* Trace/raw: `data.data.results[i].rows[j].data["trace_id"]`;
  `results[i].nextCursor` for pagination.

## 8. Conformance table (live, against the corpus)

Operator count vs an independent trace-set reference (set algebra for
`&&`/`||`/`NOT`; membership upper-bound for `=>`/`->`):

| Shape | Operator | Reference | Verdict |
|---|---|---|---|
| `A => B` | 276 | 276 | MATCH (no structural pruning) |
| `B => A` (flip) | 0 | 276 | STRUCTURAL — directional, membership is an upper bound |
| `A -> B` | 276 | 276 | MATCH |
| `A && B` | 276 | 276 | MATCH |
| `A || B` | 500 | 500 | MATCH |
| `NOT C` | 0 | 217 | MISMATCH — bare NOT returns no spans (see §4) |
| `A && NOT C` | 217 | 217 | MATCH |
| `(A => B) && NOT C` | **55** | **55** | MATCH — the ground truth |

(`A=B` here because on this corpus every `redis-retry` span sits directly under a
`shop-payment` span, so the direct-edge and co-membership sets coincide. On a
corpus with deeper nesting `A => B` < `A && B`.)

## 9. Multi-operator envelopes & upstream material

* `ValidateUniqueTraceOperator` is **not** wired into the live validation switch,
  so two operators per `compositeQuery` are accepted today (PROBE 4). The compiler
  still emits **one operator per request** — it can be enforced any release.
* Trace-operator conditions inside v2alpha1 rules fire and deliver webhooks
  end-to-end (PROBE 1 PASS). But the alert's `related_traces` deep link is built
  from a leaf query's filter, not the operator (`prepareParamsForTraces` does not
  type-switch on the trace operator) — upstream fix material.
