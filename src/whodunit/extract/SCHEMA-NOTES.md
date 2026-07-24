# Extractor — live ClickHouse schema notes

Recorded by probing the live SigNoz stack (v0.132.x) through the **v5
`clickhouse_sql` query type** (`POST /api/v5/query_range`), never `docker exec`.
The product must work against any SigNoz, so every schema fact below was
recovered with a `DESCRIBE TABLE ...` sent as a `clickhouse_sql` query.

## Tables

| logical | actual table |
|---|---|
| trace index | `signoz_traces.distributed_signoz_index_v3` |
| logs | `signoz_logs.distributed_logs_v2` |
| edge oracle | `signoz_traces.distributed_dependency_graph_minutes_v2` (NOT `_minutes`; the un-suffixed name 404s) |

## `signoz_traces.distributed_signoz_index_v3` — load-bearing columns

- `trace_id` — **`FixedString(32)`**
- `span_id` — `String`
- `parent_span_id` — `String` (root spans have `''`)
- `name` — `LowCardinality(String)` (the span/operation name, e.g. `redis-retry`)
- `duration_nano` — `UInt64` (**raw** duration; bucket from this, NOT `signoz_latency.bucket`)
- `has_error` — `Bool`; `status_code` — `Int16`
- `attributes_string` — `Map(LowCardinality(String), String)` (e.g. `attributes_string['cache.hit']`)
- `attributes_number`, `attributes_bool` — sibling maps
- `resources_string` — `Map(...)` — **this is where `deployment.environment` lives**
  (`resources_string['deployment.environment']='whodunit-demo'`)
- **service name column is `resource_string_service$$name`** (materialized,
  `LowCardinality(String)`). The `$$` means the identifier MUST be backtick-quoted
  in SQL: `` `resource_string_service$$name` ``. There is also a camelCase alias
  column `serviceName`, but the `$$` form is the canonical one and is what we use.
- HTTP route materialized column: `` `attribute_string_http$$route` `` (also `httpRoute` alias).

## `signoz_logs.distributed_logs_v2` — load-bearing columns

- `trace_id` — **`String`** (NOT FixedString like traces — the cross-signal join
  compares a `FixedString(32)` to a `String`; ClickHouse coerces this fine, and we
  key both sides off the same 32-hex-char id so equality holds).
- `body` — `String`; `severity_text` — `LowCardinality(String)`
- `attributes_string`, `resources_string` — same Map shape; env filter identical.

## `distributed_dependency_graph_minutes_v2` — edge-vocabulary oracle

Columns: `src`, `dest` (`LowCardinality(String)`), `total_count`, `error_count`,
`duration_quantiles_state`, `timestamp` (`DateTime`), `deployment_environment`.
Pre-aggregated per minute; answers "which service-edges exist at all in-window"
cheaply. It is a **vocabulary oracle only** — it is `(src,dest)` service-level and
pre-aggregated, so it cannot supply per-trace features. We use it to prune the
edge feature vocabulary before the one scan runs.

## v5 `clickhouse_sql` envelope that works

```json
{"schemaVersion":"v1","start":<ms>,"end":<ms>,"requestType":"raw",
 "compositeQuery":{"queries":[{"type":"clickhouse_sql",
   "spec":{"name":"A","query":"<SQL>","disabled":false}}]}}
```

Response: rows at `data.data.results[0].rows[i].data` (dict per row). Cost meter at
`data.meta` → `rowsScanned`, `bytesScanned`, `durationMs`.

- Multi-CTE (`WITH a AS (...), b AS (...) SELECT ...`) queries are accepted — the
  whole one-scan matrix is a single such statement.
- `countDistinctIf`, `maxIf`, `has`, `ILIKE` all work.
- **Time window:** the envelope `start`/`end` (ms) are applied by SigNoz; we also
  keep an explicit `deployment.environment` predicate so probe agents' artifacts in
  other environments are never mixed in.

## ExecStats caveat (surfaced verbatim in `FeatureMatrix`)

`bucket_cache.mergeBuckets` sums stats from **cached** buckets into `ExecStats`, so
API-reported `bytesScanned`/`rowsScanned` can **over-report** actual ClickHouse
work when buckets are warm. We surface the API numbers as a cost meter and say so;
for exactness one would read ClickHouse `read_bytes` directly.

## Live validation (seed 42, `conditional_dep`, `deployment.environment=whodunit-demo`)

A single generated scan reproduced every manifest ground-truth number exactly:

| quantity | value |
|---|---|
| total traces | 500 |
| edge `shop-payment => redis-retry` present | **276** |
| `shop-flag-service` absent | **217** |
| conjunction (edge ∧ ¬flag) = bad cohort | **55** |
| error-log template (`retry_exhausted`) present, joined by `trace_id` | **55** |
