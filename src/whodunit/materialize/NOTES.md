# Materializer — empirical findings

All reverse-engineered live against self-hosted SigNoz **v0.132.2**
(`http://localhost:8080`, OTLP `:4318`) on 2026-07-24. Every payload shape below
was proven by a real `POST`/`GET`/`DELETE`; the golden JSON under
`tests/materialize/golden/` is frozen from these.

---

## 1. Trace Explorer permalink — operator DOES deep-link (better than feared)

The Explorer reads a single `compositeQuery` URL param holding the **front-end
builder state** as JSON. Two facts, both verified by driving a live browser:

- **The param is DOUBLE URL-encoded.** The SPA stores the state already
  `encodeURIComponent`-encoded and then serialises it into the query string,
  encoding a second time — so `{` appears as `%257B`. We reproduce this with a
  double `urllib.parse.quote(..., safe="")`. (Sibling params `options` /
  `pagination` are only single-encoded; `compositeQuery` is the double-encoded
  one.)
- **The builder carries a first-class `builder.queryTraceOperator` array**, and
  every leaf carries a v5 `filter.expression`. So the trace operator deep-links:
  we constructed a URL for the ground-truth `(A => B) && NOT C`, navigated to it
  live, and the Explorer rendered the three leaves + the operator and fired a
  **`200` `POST /api/v5/query_range`**. No fallback to a bare leaf-A view was
  needed on this version.

Decoded param shape (see `permalink.py::composite_query_state`):

```jsonc
{
  "queryType": "builder",
  "builder": {
    "queryData": [ /* one disabled leaf per LeafQuery, each with filter.expression */ ],
    "queryFormulas": [],
    "queryTraceOperator": [
      {"name":"T1","expression":"(A => B) && NOT C","returnSpansFrom":"A",
       "aggregations":[{"expression":"count_distinct(trace_id)"}], ... }
    ]
  },
  "promql": [ ... ], "clickhouse_sql": [ ... ], "id": "<uuid>", "unit": ""
}
```

**Gap (documented honestly):** absolute time is NOT URL-addressable on v0.132.2.
Adding `startTime`/`endTime` (epoch-ms) params is silently stripped on load — the
Explorer's global time picker owns the range. We still append them for
provenance, but the opened view uses the picker's current window. This is a UI
limitation, not a query-encoding one.

---

## 2. Native v6 (Perses) dashboard — authored natively, operator survives verbatim

Probe 3 held: `GET /api/v2/dashboards` `501`s on every v5-schema dashboard, so
there is no v1→v6 read conversion. We therefore author natively via
`POST /api/v2/dashboards`, reverse-engineered field-by-field from strict Go
`DisallowUnknownFields` errors:

- Top level: `{"schemaVersion":"v6", "name":<slug>, "spec":{...}}`.
  - `name` is validated as a **lowercase RFC-1123 label**
    (`[a-z0-9]([-a-z0-9]*[a-z0-9])?`) — no spaces/uppercase/em-dash. The human
    title lives in `spec.display.name`; `dashboard.py::slugify` derives the slug.
- Panel plugin kinds (exhaustive, from the validator):
  `signoz/{TimeSeries,Number,Table,BarChart,Histogram,Pie,List}Panel`.
  **There is NO text/markdown panel kind in v6.** The verification receipt
  therefore rides in a panel's `display.description` (markdown) — we use a
  `signoz/NumberPanel` for it.
- **A panel takes exactly one query** ("panel must have one query"). The whole
  trace-operator composite (leaves + `builder_trace_operator` + optional
  `builder_formula`) is wrapped in a single **`signoz/CompositeQuery`** query
  plugin whose `spec.queries` is the familiar typed array. Query plugin kinds:
  `signoz/{BuilderQuery,ClickHouseSQL,CompositeQuery,Formula,PromQLQuery,TraceOperator}`.
  Per-query `kind` is the request type (`time_series` here).
- Layout is Perses `{"kind":"Grid","spec":{"items":[...]}}` on a **12-column**
  grid; each item's `content.$ref` = `#/spec/panels/<key>`.

Verified live: POST → `201`, `GET /api/v2/dashboards/{id}` → `200`, and the
`builder_trace_operator` (`(A => B) && NOT C`, `count_distinct(trace_id)`)
round-trips **verbatim** inside `signoz/CompositeQuery`. DELETE → `204`.

Three panels emitted (title pattern `Whodunit — <expression>`):
1. **Matching traces over time** — `count_distinct(trace_id)` of the operator.
2. **Share of traffic** — formula `F1 = T1 / ADenom` (operator over anchor-leaf
   denominator, both trace-scoped).
3. **Verification receipt** — NumberPanel whose markdown description embeds the
   expression + the mined/SigNoz counts + precision/recall.

---

## 3. v2alpha1 alert rule — armed, fired, webhook delivered (demo climax)

Rule POST goes to **`/api/v2/rules`** with the exact schema Probe 1 proved and we
re-confirmed live (accepted first try). Shape (`alert.py::build_rule`, frozen as
`golden/rule_v2alpha1.json`):

- top-level `"version":"v5"` **and** `"schemaVersion":"v2alpha1"`.
- `"evaluation":{"kind":"rolling","spec":{"evalWindow":"5m0s","frequency":"30s"}}`
  (an object — NOT top-level `evalWindow`/`frequency`).
- `condition.compositeQuery.queries` = leaves (`count()`) + operator
  (`count_distinct(trace_id)`); `condition.selectedQueryName` = operator name.
- `condition.thresholds = {"kind":"basic","spec":[<warning>,<critical>]}` with
  two named tiers, `op:"1"` (>), `matchType:"1"` (at least once), and
  `channels:[<name>]` per tier (channels referenced by **name**).
- `notificationSettings:{groupBy:[],usePolicy:false,renotify:{enabled:false}}`.

Channels: `POST /api/v1/channels`
`{"name","type":"webhook","webhook_configs":[{"send_resolved":true,"url":...}]}`
→ `201`. Referenced by name in rules.

**Deletes:** rule `DELETE /api/v1/rules/{id}` → `200`; channel
`DELETE /api/v1/channels/{id}` → `204`; dashboard `DELETE /api/v2/dashboards/{id}`
→ `204`. (`DELETE /api/v2/rules/{id}` → `404`; use the v1 path.)

### Live fire timeline (proven from code)

Listener on host `:9099`, channel URL `http://host.docker.internal:9099/whodunit`
(reachable from the `signoz` container). Rule armed with `warn=0`, `crit=5`,
`evalWindow=5m0s`, `frequency=30s`. Fresh matching bad traces emitted directly via
raw OTLP/HTTP-JSON to `:4318` every 20 s (the `corpus` package needs
`opentelemetry`, absent from this venv, so we emitted equivalent
`shop-payment → redis-retry`, no `shop-flag-service`, `env=whodunit-demo` spans).

```
t+0s    rule armed (id 019f9527-…); listener up
t+0..180s  25 matching bad traces emitted every 20s
           (query_range confirms operator count_distinct(trace_id) = 25)
t+182s  WEBHOOK POST /whodunit  (4126 bytes, status "firing")  ← CLIMAX
t+182s  rule + channel deleted (cleanup)
```

Delivered webhook body (trimmed):

```jsonc
{
  "receiver": "whodunit-fire-test", "status": "firing",
  "alerts": [{
    "status": "firing",
    "labels": {"alertname":"whodunit-fire-test","ruleId":"019f9527-…",
               "severity":"critical","team":"whodunit","threshold.name":"critical"},
    "annotations": {
      "description": "Whodunit discriminator (A => B) && NOT C — count_distinct(trace_id) of matching traces.",
      "related_traces": "http://localhost:8080/traces-explorer?compositeQuery=…service.name%3D'shop-flag-service'…"
    }
  }]
}
```

It fired on the **critical** tier (count 25 > 5), proving the two-named-threshold
construction notifies (hazard #10591 did not manifest for single-channel tiers).

### The corroborated upstream bug

SigNoz's **own** auto-generated `related_traces` deep link in the fired alert was
built from a **leaf filter** — specifically query **C**
(`service.name='shop-flag-service'`, the `NOT` operand!) — not from the trace
operator. This is exactly the `prepareParamsForTraces` degradation Probe 1
flagged: it type-switches only on plain builder queries, so an operator alert's
"view related traces" link is misleading. This is precisely why Whodunit ships
its own `permalink()` (§1) that correctly encodes `builder.queryTraceOperator`.

---

## 4. Interface implemented

`whodunit.materialize.Materializer(client, *, ui_base_url=None)`:

- `permalink(compiled, *, window_start_ms, window_end_ms) -> str`
- `create_dashboard(compiled, *, title) -> str` (dashboard id; `dashboard_url(id)` for the UI link)
- `arm_alert(compiled, *, rule_name, warn_threshold, crit_threshold, channel_webhook_url, window="5m0s") -> str` (rule id)
- cleanup/verify helpers: `delete_dashboard`, `delete_rule`, `delete_channel`,
  `get_rule`, `channel_id_by_name`.

`arm_alert` creates/reuses the webhook channel first (a default named
`whodunit-default` when `channel_webhook_url` is `None`), then POSTs the rule.
