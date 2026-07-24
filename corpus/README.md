# Whodunit — Demo Corpus & Seeded Fault Engine

A single Python process that emits **OTLP traces + logs at volume** (thousands of
traces) for a synthetic 8-service "shop", with a switchable library of
**structural faults**. It exists because the live SigNoz instance holds only
~2.5k spans — a convincing structural-mining demo needs volume, and the fault
must be *structural* (not separable by any single attribute) so that Whodunit's
conjunction-mining earns its keep.

> **Disclosure (methodology, not deception).** All data here is **synthetic** and
> **deterministic** under `--seed`. Every resource carries `service.name` with the
> `shop-` prefix and `deployment.environment=whodunit-demo`, so demo data is
> trivially filterable and removable. The exact seed, fault, and ground truth are
> recorded in a per-run manifest and disclosed on screen in the demo. Hidden
> synthetic data would be fatal; disclosed synthetic data is standard benchmark
> methodology (cf. fault-injection benchmarks in the RCA literature).

## The shop

Eight logical services, each emitted as a distinct `service.name` resource from
one process (multiple `TracerProvider`s sharing a deterministic id generator):

```
shop-checkout ─┬─ shop-flag-service        (GET /flags/evaluate; feature flags)
               ├─ shop-cart ─┬─ shop-cache  (cache-get; cache.hit)
               │             ├─ shop-db     (SELECT cart_items)      ← db-read
               │             └─ shop-inventory (inventory-sync)      ← new_edge fault
               ├─ shop-inventory ─ shop-db  (SELECT stock)
               ├─ shop-payment ─┬─ shop-payment (redis-retry ×N)     ← flagship / retry_storm
               │                └─ shop-db   (UPDATE ledger)
               └─ shop-notification          (notify.enqueue; kafka)
```

Every trace: a 6–11 span tree, **log-normal** span durations, realistic
attributes (`http.route`, `db.system`, `cache.hit`, `feature.flag.*`,
`order.completed`), and **1–3 logs** per trace carrying the trace's `trace_id`
with templated bodies (one is an error template on bad traces).

## Usage

```bash
pip install -r corpus/REQUIREMENTS.txt

# Flagship run (5000 traces):
python -m corpus.generate --traces 5000 --seed 42 \
    --fault conditional_dep --fault-rate 0.12 \
    --endpoint http://localhost:4318

# Smoke (50 traces, prints counts):
python -m corpus.smoke --endpoint http://localhost:4318

# Offline (manifest + ground-truth self-check only, no network):
python -m corpus.generate --no-emit --fault conditional_dep
```

### CLI flags

| flag | default | meaning |
|---|---|---|
| `--traces N` | 5000 | number of traces |
| `--seed N` | 42 | deterministic seed (identical seed → identical trace ids + manifest) |
| `--fault NAME` | conditional_dep | which fault (one active per run; see below) |
| `--fault-rate F` | 0.12 | fraction of traces that are the bad cohort |
| `--endpoint URL` | http://localhost:4318 | OTLP/HTTP base (`/v1/traces`, `/v1/logs` appended) |
| `--error-visible {true,false}` | false | true → bad spans carry status ERROR; false → fail politely via `order.completed=false`, status OK |
| `--decoys F` | 0.0 | decoy overlay strength [0..1]: inject a correlated-but-non-causal attribute + high-cardinality noise into *any* fault |
| `--duration-hours H` | 1.0 | spread emitted traces across the last H hours |
| `--no-emit` | — | plan + manifest + self-check only, no OTLP |

## Fault library (one active per run)

| # | `--fault` | Ground-truth discriminator | Expressible in trace-operator algebra? |
|---|---|---|---|
| 1 | `conditional_dep` | `(checkout => payment => redis-retry) && NOT flag-service` | **yes** — flagship. Perfect separator; each single conjunct is a low-lift near-miss. |
| 2 | `new_edge` | `checkout => cart => inventory-sync` (post-deploy only) | yes — a new edge appears after the deploy marker |
| 3 | `cache_bypass` | `NOT cache-get` (with inflated db-read) | yes — **trace-scoped** absence; span-level negation must be refused |
| 4 | `retry_storm` | `count(redis-retry) >= 2` | **no** — no cardinality operator in the algebra. Ground truth = **abstain/refuse**; tests honest refusal. |
| 5 | `decoys` | none (a 60–70% correlated non-causal attribute + noise) | **no** — ground truth = **abstain**; tests false-culprit avoidance |
| 6 | `null_scenario` | none (nothing is wrong) | **no** — ground truth = **abstain** |

The flagship `conditional_dep` is engineered so **healthy traffic never contains
the culprit conjunction**: healthy traces have flag-service present *or* no
redis-retry. Therefore the conjunction is a *perfect* separator (precision =
recall = 1.0) while each single predicate appears in **both** cohorts and has low
lift — exactly the regime where naive single-attribute tools (BubbleUp-style) see
nothing.

**Conjunction lift vs background = `1 / fault_rate`.** At `--fault-rate 0.12` the
lift is ~8.3×; to reach the ≥20× headline, use `--fault-rate 0.05` or lower. The
manifest reports the achieved lift. (The real, seed-independent claim is *perfect
separation*, which the self-check and the ClickHouse validation both confirm.)

## Manifest — `corpus/out/manifest-<runid>.json`

Each run writes a manifest containing:

- `seed`, `fault`, `fault_rate`, `error_visible`, `decoys_strength`, `endpoint`;
- `window` (base time + duration) so verification can be time-scoped;
- `counts` (total / bad / healthy / per-cohort / spans / logs / background bad
  rate / conjunction lift);
- `ground_truth` — **human text** *and* a **machine-checkable spec**: required
  span presence/absence and edges per cohort, plus `expressible_in_trace_operator`
  and, for the abstain faults, `ground_truth_verdict: "abstain"`;
- `self_check` — the machine spec re-evaluated against the generated trees; for
  expressible faults it must select **exactly** the bad-labelled set
  (`spec_matches_label: true`), otherwise `corpus.generate` exits non-zero;
- `bad_trace_ids` — inline, or gzipped to a `-badids.json.gz` side file when
  large (> 2000).

## Determinism

`(seed, trace_index)` fully determines the trace id, span ids, cohort
assignment, attributes, and log bodies. A re-run with the same seed lands
identical `trace_id`s in ClickHouse; the manifest's `bad_trace_ids` are therefore
reproducible and stable. Span/log *timestamps* are the only wall-clock-relative
values (the corpus is placed in the last `--duration-hours`).

## Validation (performed against the live SigNoz stack)

A 500-trace `conditional_dep` seed-42 run was emitted to `localhost:4318` and
verified in ClickHouse (`signoz-telemetrystore-clickhouse-0-0`):

- **(a) counts** — `count(DISTINCT trace_id)` = **500**, matching the manifest.
- **(b) separation** — via `parent_span_id` self-joins for the `=>` edges and a
  trace-level anti-join for flag-service absence: the conjunction
  `has(payment=>redis-retry) AND NOT has(flag-service)` selected **exactly the 55
  bad traces** (0 false positives, 0 false negatives), while the single
  predicates matched **276** and **217** traces respectively — neither separates.
- **(c) logs** — joined by `trace_id`, the `payment.retry_exhausted` error
  template landed on **exactly the 55 bad traces** (the cross-signal join that is
  impossible on Tempo+Loki).

## Docker

```bash
docker build -f corpus/Dockerfile -t whodunit-corpus .
docker run --rm --network <signoz-network> \
    -v "$PWD/corpus/out:/app/corpus/out" whodunit-corpus \
    --traces 5000 --seed 42 --fault conditional_dep --fault-rate 0.12
```

The image `ENTRYPOINT` defaults `--endpoint` to `http://ingester:4318` (the
compose network service name for the SigNoz OTLP ingester).

## Files

| file | role |
|---|---|
| `generate.py` | CLI + orchestration; writes the manifest |
| `topology.py` | builds the base shop trace tree |
| `faults.py` | the six-fault library + ground-truth specs |
| `emit.py` | per-service OTLP TracerProviders/LoggerProviders; deterministic emission |
| `ids.py` | deterministic trace/span id generation |
| `model.py` | `SpanNode` / `TracePlan` / `LogRecordPlan` |
| `manifest.py` | manifest build, ground-truth self-check, gzip side-file |
| `smoke.py` | 50-trace smoke test, prints counts |
| `Dockerfile` / `REQUIREMENTS.txt` | packaging |
