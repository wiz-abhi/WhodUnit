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

> Whodunit is a deterministic structural root-cause engine whose output is a SigNoz
> query you own. You point it at a set of failing traces; it auto-selects a
> case-control–matched healthy cohort, mines the full itemset lattice for the span,
> edge, and log patterns that structurally separate the two cohorts, and then compiles
> the winning finding into a valid SigNoz `builder_trace_operator` query. That query is
> verified against the live engine — the count Whodunit mined locally is asserted equal
> to the count SigNoz returns — and reported with precision/recall. The finding then
> round-trips into artifacts you own: a Trace Explorer permalink, a native v6 dashboard
> panel, and an armed v2alpha1 multi-threshold alert.
>
> Every other tool in this category (Honeycomb BubbleUp, Datadog Trace Patterns,
> Chronosphere DDx, Grafana `compare()`) stops at a ranking a human then re-types by
> hand. Whodunit closes the loop — mine, compile, verify, arm — and it is the
> implementation of SigNoz issue #1957 ("Enable a way to compare 2 sets of filtered
> spans"), opened by co-founder pranay01 in January 2023 and still open, answered with
> an executable artifact rather than a panel. There is no LLM anywhere in the runtime;
> the same input plus seed always produces the same verdict hash. On a six-scenario
> fault-injection benchmark run live against the stack it passes 5/6, nailing the
> flagship conjunctive fault a flat baseline (precision 0.23) cannot see, and taking a
> calibrated abstain/partial — never a false culprit — on the three scenarios where a
> confident answer would be wrong. Tagline: "Everyone can show you the difference. Only
> SigNoz can arm it."

### 6. GitHub link *

`https://github.com/<user>/whodunit` **[FILL IN before submitting]**

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

> Whodunit leans on all five SigNoz surfaces, load-bearingly, plus MCP and Foundry:
>
> - **Traces** — the hypothesis space *is* trace structure. One `clickhouse_sql` v5
>   query builds a per-`trace_id` feature matrix over raw, 100%-sampled
>   `signoz_index_v3`: span predicates (latency bucketed from raw `duration_nano`),
>   parent→child edges via a self-join on `parent_span_id`, and depth-bounded ancestor
>   walks. The output artifact is a `builder_trace_operator` expression that opens in
>   Trace Explorer as a deep-linked permalink.
> - **Logs** — log-derived features (error-template presence, body tokens) are
>   first-class members of the mining lattice, joined by `trace_id` from the *same*
>   ClickHouse (`signoz_logs.distributed_logs_v2`). This cross-signal join is impossible
>   on Tempo+Loki (separate stores) — it's the SigNoz-specific move.
> - **Metrics** — span metrics supply the denominator for the "share of traffic matching
>   the discriminator" formula on the emitted dashboard panel.
> - **Dashboards** — every finding emits a native **v6 (Perses)** dashboard authored via
>   `POST /api/v2/dashboards`, wrapping the trace-operator composite in a
>   `signoz/CompositeQuery` plugin (we found v1→v6 has no read conversion, so we author
>   v6 natively). Three panels: matching-traces-over-time, share-of-traffic, and a
>   verification receipt.
> - **Alerts** — the discriminator becomes a **v2alpha1** multi-threshold rule
>   (WARN/CRIT) whose webhook fires end-to-end; we proved the full timeline live (rule
>   armed → matching traces emitted → webhook POST "firing" at ~t+182s). Whodunit is
>   also a webhook *consumer*: register it as a channel target and a firing rule's own
>   condition defines the bad cohort.
> - **MCP + Foundry** — `casting.yaml` sets `spec.mcp.spec.enabled: true` and injects the
>   seeded demo corpus via a compose patch, so the mandated compliance file is also the
>   one-command installer. The engine is designed to be callable as MCP tools
>   (`whodunit_explain` / `_compile` / `_verify`).
>
> Every compiled query is differentially verified against `/api/v5/query_range` as a
> scalar `count_distinct(trace_id)` — Whodunit doesn't just talk to SigNoz, it holds
> itself accountable to SigNoz's own answer. Building this deep surfaced four
> undocumented/misdocumented engine semantics (the `=>`/`->` mapping is reversed on
> v0.132.2; `NOT` is trace-scoped; operator alert deep links are built from a leaf
> filter; `clickhouse_sql` ignores the envelope time window), each of which becomes an
> upstream PR/issue.

### 10. Project blog link *

`https://dev.to/<user>/<slug>` **[FILL IN — new blog, per `docs/BLOG-DRAFT.md`]**

*(New blog written for this hackathon project; the pre-event warm-up blog does not
qualify.)*

### 11. How was your hackathon experience? *

> Genuinely great, and harder than I expected in the right way. I went in thinking the
> hard part would be the statistics — the mining, the FDR control, the abstention gates
> — and it was real work, but the thing that actually ate my week was the trace-operator
> compiler. The `builder_trace_operator` grammar is barely documented, and the parts
> that *are* documented turned out to be wrong on the version I was running: `=>` and
> `->` are reversed from the intuitive reading, `NOT` is trace-scoped so a bare negation
> returns nothing, and `clickhouse_sql` quietly ignores the query time window. I only
> found each of those because I made the tool verify its own output against the live
> engine and a count came back wrong. That feedback loop — mine locally, ask SigNoz, and
> refuse to trust myself until the two numbers match — ended up being the most valuable
> design decision in the project, and it's what turned "here's a probably-right query"
> into "here's a query SigNoz just agreed with." I'm walking away with four upstream
> issues/PRs I actually want to file, which feels like the best possible outcome for a
> hackathon: I built on the platform, hit real walls, and can hand the maintainers a
> patch for the wall.
