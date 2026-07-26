# Submission form — drafted answers

Live form: *Agents of SigNoz Submissions*
(`https://docs.google.com/forms/d/e/1FAIpQLSe8AwOr0mi40cj1fw2nXM7wokXwqROkYmkSXOSsSJj-ZIA0Kw/viewform`).
Fields per [`HACKATHON-REQUIREMENTS.md`](../../../HACKATHON-REQUIREMENTS.md). One member
submits per team. Paste each answer into the matching field.

---

### 1. Email *

`user.abhishek2004@gmail.com`

### 2. Team name (write YOUR NAME if solo) *

`Abhishek` *(solo — replace with team name if a team forms before submission)*

### 3. Name of person submitting *

`Abhishek`

### 4. Track *

**Track 2 — Signals & Dashboards.**

*(Whodunit is a Query Builder synthesis product: its output is a `builder_trace_operator`
Query Builder artifact, verified against the live engine and materialized as a permalink,
dashboard panel, and alert. No LLM in the runtime.)*

### 5. Project description *

Whodunit turns root-cause analysis into a SigNoz query you own.

You point it at a set of failing traces. It automatically picks a matched cohort of
healthy traces, then mines the span, edge, and log patterns that actually separate
"broken" from "fine." The winning pattern is compiled into a real SigNoz
builder_trace_operator query — and then verified against the live engine: the count
Whodunit computed locally has to equal the count SigNoz returns, or it won't ship the
finding.

What you get back is not a chart you re-type by hand. It's artifacts you keep:
- a Trace Explorer permalink,
- a native v6 dashboard panel,
- an armed multi-threshold alert.

Every other tool in this space — Honeycomb BubbleUp, Datadog Trace Patterns,
Chronosphere DDx, Grafana compare() — stops at a ranking and leaves the rest to you.
Whodunit closes the loop: mine, compile, verify, arm. It's a direct answer to SigNoz
issue #1957 ("Enable a way to compare 2 sets of filtered spans"), opened by co-founder
pranay01 in January 2023 and still open — answered with an executable query instead of
a panel.

Two things I care about most:
- No LLM at runtime. Same input + seed always produces the same verdict hash.
- It knows when to stay silent. On a live six-scenario fault-injection benchmark it
  scores 6/6: it nails the hard conjunctive fault a flat baseline (0.23 precision)
  cannot see, and it abstains — never naming a false culprit — on the three cases where
  any confident answer would be wrong.

Tagline: "Everyone can show you the difference. Only SigNoz can arm it."

### 6. GitHub link *

`https://github.com/wiz-abhi/WhodUnit`

Repo includes `deploy/casting.yaml` and `deploy/casting.yaml.lock` for reproducible
Foundry deployment, as required. (Note in README: the live dev stack occupies
`:8080`/`:4318`, so run `foundryctl cast` on a clean host/VM.)

### 7. Deployed link (optional)

**https://wiz-abhi-whodunit-replay.static.hf.space** — a static, offline interactive replay of the real seed-778 run (live on Hugging Face Spaces).

*(Whodunit itself is a CLI + engine, not a hosted service; this deployed link is an
interactive replay of the committed run — elimination board → compiled query →
verification receipt → firing alert → determinism hash — hosted as a Hugging Face
static Space. The full demo remains the video + reproducible `foundryctl cast`.)*

### 8. YouTube video demo link *

**https://youtu.be/myZlRwcpHIA** — 4:38, captioned. Covers all four requested beats:
about the project (0:00), tech stack + architecture (0:00–1:19, incl. two hand-drawn
architecture sketches), the live demo (1:19–4:01), and learning & growth (3:10 — the
benchmark scenario it first got wrong, diagnosed and fixed in the open).

*Note on length: the form suggests ≤3 minutes. This runs 4:38 because the intro covers
the required "about / tech stack / architecture" beats before the demo starts. Chapters
are set on the video so any section can be jumped to directly.*

Covers: the project (issue #1957 → mine/compile/verify/arm), tech stack and
architecture (five-stage pipeline over ClickHouse + v5 Query Builder), a live demo
(elimination board → compiled query → verification receipt → Trace Explorer permalink →
armed alert firing → determinism hash), and learnings (the four engine findings).

### 9. Describe how you used SigNoz in your project *

Whodunit uses all five SigNoz signals as load-bearing parts, plus MCP and Foundry.

Traces — the whole hypothesis lives in trace structure. A single clickhouse_sql (v5)
query builds a per-trace feature matrix over raw, 100%-sampled signoz_index_v3: latency
buckets, parent→child edges (a self-join on parent_span_id), and bounded ancestor walks.
The result compiles to a builder_trace_operator expression that opens straight in Trace
Explorer as a shareable permalink.

Logs — error templates and log-body tokens join the mining lattice as first-class
features, matched by trace_id from the same ClickHouse (signoz_logs.distributed_logs_v2).
This trace-to-log join inside one store is the SigNoz-specific move; it simply isn't
possible on Tempo + Loki, which are separate stores.

Metrics — span metrics give the denominator for the "share of traffic matching the
discriminator" number shown on the dashboard.

Dashboards — each finding writes a native v6 (Perses) dashboard via
POST /api/v2/dashboards, with three panels: matching-traces-over-time, share-of-traffic,
and a verification receipt. (v1→v6 has no read conversion, so I author v6 natively.)

Alerts — the discriminator becomes a v2alpha1 multi-threshold rule (WARN/CRIT). I proved
the full path live: rule armed → matching traces appear → webhook fires "firing" at
about t+182s. Whodunit is also a webhook consumer — point a firing rule at it and the
rule's own condition defines the bad cohort.

MCP + Foundry — casting.yaml enables MCP and injects the seeded demo corpus, so the
required compliance file doubles as a one-command installer. The engine is built to be
callable as MCP tools (whodunit_explain / _compile / _verify).

The part I'm proudest of: every compiled query is checked back against
/api/v5/query_range as a count_distinct(trace_id). Whodunit doesn't just query SigNoz —
it refuses to trust its own answer until SigNoz agrees. That same loop taught me the
operator semantics the hard way: => is single-hop and -> is any-depth (I had coded them
backwards, and the receipt caught it); a bare NOT is trace-scoped and returns nothing on
its own, so the compiler only emits absence as a conjunct like A && NOT C; and
clickhouse_sql expects the SQL to carry its own time predicate rather than applying the
request window. Most of these turned out to be documented or working-as-intended once I
understood them — the compiler just encodes each correctly. The one thing that still
looks like a real upstream edge is that a fired operator-alert's "related traces" link
resolves to a leaf filter instead of the operator (prepareParamsForTraces doesn't
type-switch), which is why Whodunit ships its own correct Trace Explorer permalink.

### 10. Project blog link *

`https://medium.com/@abhishekg8318/whodunit-compiling-a-root-cause-finding-back-into-a-signoz-query-you-own-d83bece7f422`

*(New blog written for this hackathon project; the pre-event warm-up blog does not
qualify.)*

### 11. How was your hackathon experience? *

Genuinely great — and hard in the right way.

I expected the statistics to be the hard part: the pattern mining, the false-discovery
control, the rules for when to abstain. That was real work. But the thing that actually
ate my week was the trace-operator compiler. The builder_trace_operator grammar is
barely documented, and the parts that are documented were wrong on my version: => and ->
are reversed, a bare NOT is trace-scoped and returns nothing, and clickhouse_sql
silently ignores the query time window.

I only caught each of these because I'd made the tool verify its own output against the
live engine — and a count came back wrong. That loop — mine locally, ask SigNoz, and
don't trust myself until the two numbers match — turned out to be the best design
decision in the project. It's what moves you from "here's a probably-right query" to
"here's a query SigNoz just agreed with."

The nicest surprise was how much reading the platform closely paid off. Most of the
"walls" I hit turned out to be documented or working-as-intended once I understood the
operator semantics — the real win was building on them correctly instead of papering
over them. There's one rough edge I'd still want to raise (a fired operator-alert's
"related traces" link resolves to a leaf filter, not the operator); I have a live repro,
and I'd check it against the issue tracker before filing in case it's already known.
Building deep on someone's engine, hitting real edges, and being able to hand back a
concrete repro — that's about the best outcome a hackathon can have.
