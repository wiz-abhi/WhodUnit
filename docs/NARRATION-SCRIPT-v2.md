# Whodunit — narration script (v2, ~4:13 cut)

> **Status:** DRAFT — for the revised 11-beat structure (landing page in, static intro cards out,
> abstention beat added). Supersedes `docs/video/NARRATION-SCRIPT.md` once the new cut is recorded.
> **Do not record until the three new beats are shot** — windows marked `[TARGET]` are estimates and
> will be re-synced to measured durations; windows marked `[MEASURED]` are locked to existing footage.

## How to record

- **One file per segment**, named `audio/seg01.wav` … `audio/seg11.wav`. Segmented beats a single take
  every time — one flub costs you 20 seconds, not four minutes.
- Quiet room, mic ~20 cm and slightly off-axis (avoids plosives), **48 kHz / 16-bit mono**, peaks
  around −12 to −6 dBFS.
- **Leave ~1 second of silence at the start** of each file; the assembler trims and offsets precisely.
- If you fluff a line, **stop and restart the segment** — don't punch in.
- Pace ≈ **145 words per minute**. Every segment below has headroom; you do not need to rush.
- Read it like you're explaining it to one competent engineer, not presenting to a room. Flat and
  certain beats enthusiastic.

---

### seg01 · b1 — the cold open  `[MEASURED 12.0s]`
**26 words ≈ 10.8s · headroom 1.2s**
*Emphasis: land on "still open" — that's the whole reason the project exists. No triumph in the voice.*

```text
SigNoz's co-founder asked for this three and a half years ago — compare two sets of
filtered spans. It's still open. Here's the implementation.
```

---

### seg02 · landing page — thesis + architecture  `[TARGET 46s]` 🔴 new footage
**88 words ≈ 36.4s · headroom 9.6s**
*Emphasis: "and then a human types the query by hand" is the problem statement — slight pause after it.
Hit "no LLM in any of them" cleanly; it's the claim people will doubt.*
*Covers the form's required "tech stack and architecture" beat.*

```text
Every tool in this space shows you the difference between two cohorts of traces. BubbleUp,
Trace Patterns, DDx, Grafana's compare — they rank attributes, and then a human types the
query by hand. Whodunit closes that loop. One ClickHouse scan builds a feature matrix over
traces and logs in the same store. FP-growth mines the whole lattice. The winner gets
compiled into SigNoz's own trace-operator grammar, verified against the live engine, and
armed as an alert. Five stages, and no LLM in any of them.
```

---

### seg03 · b2 — the elimination board  `[MEASURED 16.3s]`
**36 words ≈ 14.9s · headroom 1.4s**
*Emphasis: the near-misses should sound dismissive; "only the conjunction" is the answer landing.
Time it to the winner row highlighting.*

```text
One question to ClickHouse. Then the whole lattice is enumerated locally. The machine weighs
the obvious answers — the edge alone — and rejects them. Only the conjunction separates the
cohorts, at thirteen times lift.
```

---

### seg04 · b3 — the honest baseline fails  `[MEASURED 13.8s]`
**30 words ≈ 12.4s · headroom 1.4s**
*Emphasis: stress "every flat tool" — you're pre-empting "isn't this just BubbleUp?". Matter-of-fact,
not defensive. Pause before "zero point one seven".*

```text
This is what every flat tool sees — BubbleUp, compare, Trace Patterns. Its best single
predicate lands at precision zero point one seven. The fault needs two conditions at once.
```

---

### seg05 · b4 — the compiler and the receipt  `[MEASURED 12.6s]`
**30 words ≈ 12.4s · headroom 0.2s — tightest segment, don't dawdle**
*Open cold on "No model wrote this" — no run-up. Read the expression as "A implies B, and not C" —
never "equals greater than". Time "SigNoz returned sixty-one" to the receipt snapping in.*

```text
No model wrote this. It's compiled into SigNoz's own grammar — A implies B, and not C —
then run back against the engine. Mined sixty-one. SigNoz returned sixty-one.
```

---

### seg06 · b5 — the permalink in Trace Explorer  `[MEASURED 28.3s]`
**47 words ≈ 19.5s · headroom 8.8s**
*Emphasis: "the real UI" — the point is this isn't a mock. Slow down on the last clause; the flame
graph is doing the proving.*

```text
That permalink opens the machine-written query in SigNoz's own Trace Explorer — all three
leaves and the operator, rendered in the real UI. The result set collapses to the matched
traces. Open one, and the flame graph shows the shape: payment retries redis, and
flag-service never ran.
```

---

### seg07 · b6 — arm it  `[MEASURED 31.0s]`
**66 words ≈ 27.3s · headroom 3.7s**
*Emphasis: "the rule ID in that payload is the rule the command just created" is the proof it's real,
not a mock webhook — say it deliberately. The last sentence is the thesis; land it.*

```text
One flag arms it. The discriminator becomes a native v2alpha1 alert with warning and critical
thresholds. Replay the fault, and at t plus one eighty-two seconds the webhook fires — the
rule ID in that payload is the rule the command just created. Everyone else in this category
stops at a panel. None of them hand you back a query, a dashboard, and an armed tripwire.
```

---

### seg08 · abstention + the one it first got wrong  `[TARGET 32s]` 🔴 new footage
**70 words ≈ 29.0s · headroom 3.0s**
*The most important segment in the video. Deliver it plainly — no apology, no bragging. "I found the
seam, fixed it, and left the original failure in the repo" is the line judges remember.*
*Covers the form's optional "learning and growth" beat.*

```text
Here's what matters more. Point it at a decoy — an attribute that tracks failure but doesn't
cause it — and it abstains. Point it at a healthy system, it abstains again. Across six
seeded faults, it never named a false culprit. And this one it first got wrong — it abstained
where a real answer existed. I found the seam, fixed it, and left the original failure in the repo.
```

---

### seg09 · b7 — determinism  `[MEASURED 25.4s]`
**34 words ≈ 14.1s · headroom 11.3s — you can take this one slowly**
*Emphasis: "no LLM anywhere in the runtime" is the differentiator in an AI hackathon. Say the last
sentence as a disclosure, not a defence.*

```text
Run it twice. Same input, same seed, same verdict hash. There is no LLM anywhere in the
runtime — this is deterministic. The corpus is synthetic and disclosed; ground truth comes
from a manifest.
```

---

### seg10 · replay app — try it yourself  `[TARGET 18s]` 🔴 new footage
**34 words ≈ 14.1s · headroom 3.9s**
*Emphasis: "you don't need my machine" is the point — it answers the judge's "can I actually try this".*

```text
And you don't need my machine to check any of it. The whole run is stepped through in the
browser — the board, the compiled query, the receipt, the hash — hosted, no install.
```

---

### seg11 · b8 — close  `[MEASURED 18.2s]`
**23 words ≈ 9.5s · headroom 8.7s**
*Slow down. This is the tagline; let it sit. Beat of silence before "One command".*

```text
Everyone can show you the difference. Only SigNoz can arm it. One command reproduces the
whole thing — casting file and lock, committed.
```

---

## Budget

| seg | beat | window | words | ≈ speech | headroom |
|---|---|--:|--:|--:|--:|
| 01 | b1 citation | 12.0 `[M]` | 26 | 10.8s | +1.2 |
| 02 | landing 🔴 | 46.0 `[T]` | 88 | 36.4s | +9.6 |
| 03 | b2 board | 16.3 `[M]` | 36 | 14.9s | +1.4 |
| 04 | b3 baseline | 13.8 `[M]` | 30 | 12.4s | +1.4 |
| 05 | b4 receipt | 12.6 `[M]` | 30 | 12.4s | +0.2 |
| 06 | b5 permalink | 28.3 `[M]` | 47 | 19.5s | +8.8 |
| 07 | b6 arm it | 31.0 `[M]` | 66 | 27.3s | +3.7 |
| 08 | abstention 🔴 | 32.0 `[T]` | 70 | 29.0s | +3.0 |
| 09 | b7 determinism | 25.4 `[M]` | 34 | 14.1s | +11.3 |
| 10 | replay 🔴 | 18.0 `[T]` | 34 | 14.1s | +3.9 |
| 11 | b8 close | 18.2 `[M]` | 23 | 9.5s | +8.7 |
| | **total** | **≈4:13** | **484** | **≈3:20** | |

`[M]` measured from existing footage · `[T]` target for footage not yet shot.

## Numbers used — all real, all from the seed-778 run or the benchmark

- **13.1× lift**, **mined 61 = SigNoz 61**, verdict hash `95f8835…` — the seed-778 demo run
- **precision 0.17** (seg04) — the flat baseline on the *same seed-778* matrix, matching what's on
  screen in b3. ⚠️ Not to be confused with **0.23**, which is the baseline on the benchmark's
  `conditional_dep` seed-101 run. Both are real; each is quoted only where it matches the footage.
- **six seeded faults · never a false culprit · the one it first got wrong** (seg08) — `benchmark/REPORT.md`
  and `benchmark/ISSUES.md` #2
- **t+182s webhook** (seg07) — the real captured firing in `docs/video/raw/webhook.log`
