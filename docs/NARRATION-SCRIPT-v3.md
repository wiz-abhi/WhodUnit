# Whodunit — narration script (v3, 4:48.6 sketch cut)

> **Status:** LOCKED — thirteen beats, cut and measured. Supersedes
> `docs/NARRATION-SCRIPT-v2.md`. Every window below is `[MEASURED]` with ffprobe off
> `tools/video/manifest.json`; no target durations remain. Beat order is
> `b9t, b1, s1, b2, b3, b4, s2, b5, b6, b10, b7, b11, b8`, assembled into
> `docs/video/demo-silent.mp4` at **288.63s (4:48.6)** — 11.37s under the 5:00 cap.
>
> What changed from v2: the film **opens on the landing page** (`b9t`, b9 re-trimmed to
> 44.60s) instead of the GitHub issue, and two **hand-drawn animated sketch beats** are
> new — `s1` "the fault, drawn" (seg03) and `s2` "one store, not three" (seg07), rendered
> by `tools/video/sketch/`.
>
> Word counts are whitespace tokens of the fenced block, exactly as
> `tools/video/captions/build_captions.py` counts them, and the speech estimate is
> words ÷ 145 wpm. **No segment overruns its window.**

## How to record

- **One file per segment**, named `audio/seg01.wav` … `audio/seg13.wav`. Segmented beats a
  single take every time — one flub costs you 20 seconds, not five minutes. (If you would
  rather do it in one pass, read `docs/NARRATION-ONE-TAKE.md`, which is the same thirteen
  segments with silence-gap markers.)
- Quiet room, mic ~20 cm and slightly off-axis (avoids plosives), **48 kHz / 16-bit mono**, peaks
  around −12 to −6 dBFS.
- **Leave ~1 second of silence at the start** of each file; the assembler trims and offsets precisely.
- If you fluff a line, **stop and restart the segment** — don't punch in.
- Pace ≈ **145 words per minute**. Every segment below has headroom; you do not need to rush.
- Read it like you're explaining it to one competent engineer, not presenting to a room. Flat and
  certain beats enthusiastic.

---

### seg01 · b9t landing page — who, what, and the problem  `[MEASURED 44.60s]`
**104 words ≈ 43.0s · headroom 1.3s**
*The longest segment in the film and the one that has to carry it. Your name and the track go
by quickly — the weight is on "Then a human re-types that finding into a query, at three in
the morning." Pause after "morning", then "Whodunit closes that loop" lands flat and certain.
The five stages are a list; don't sing them. Hit "no LLM anywhere" cleanly — it's the claim
people will doubt.*
*Covers the form's required "who you are" and "tech stack and architecture" beats.*

```text
I'm Abhishek. This is Whodunit, built for the Agents of SigNoz hackathon — Track 2,
Signals and Dashboards. When production breaks, every observability tool shows you the
difference between the traces that failed and the ones that didn't. BubbleUp, Trace
Patterns, Grafana's compare — they rank attributes and hand you a panel. Then a human
re-types that finding into a query, at three in the morning. Whodunit closes that loop.
One ClickHouse scan, mine the pattern that separates the cohorts, compile it into a real
SigNoz query, verify it against the live engine, and arm it as an alert. Five stages,
no LLM anywhere.
```

---

### seg02 · b1 — the citation  `[MEASURED 12.00s]`
**25 words ≈ 10.3s · headroom 1.4s**
*Land on "still open" — that's the whole reason the project exists. No triumph in the voice;
it's a fact you're pointing at.*

```text
And this isn't a problem I invented for a hackathon. SigNoz's co-founder asked for exactly
this, three and a half years ago — still open.
```

---

### seg03 · s1 sketch — the fault, drawn  `[MEASURED 23.70s]`
**51 words ≈ 21.1s · headroom 2.3s**
*Slow and explanatory — this is the one beat where you're teaching, not proving. The drawing
reveals in step with you: healthy tree (~1s), failing tree (~5s), the retry circled on both
sides (~9s), the missing flag circled on both sides (~13s), the green box (~18s). Let each
"also in healthy traces" sit for a beat before moving on. "Only both at once" is the payoff —
land it with the green box, not before.*

```text
Here's the fault, drawn. A healthy checkout calls the flag service. A failing one retries
redis, and the flag-service span is missing. But the retry alone shows up in healthy traces
too. And plenty of healthy traces skip the flag check. Neither condition alone separates
them — only both at once.
```

---

### seg04 · b2 — the elimination board  `[MEASURED 16.27s]`
**35 words ≈ 14.5s · headroom 1.5s**
*Emphasis: the near-misses should sound dismissive; "only the conjunction" is the answer landing.
Time it to the winner row highlighting.*

```text
One question to ClickHouse. Then the whole lattice is enumerated locally. The machine weighs
the obvious answers — the edge alone — and rejects them. Only the conjunction separates the
cohorts, at thirteen times lift.
```

---

### seg05 · b3 — the honest baseline fails  `[MEASURED 13.83s]`
**30 words ≈ 12.4s · headroom 1.1s**
*Emphasis: stress "every flat tool" — you're pre-empting "isn't this just BubbleUp?". Matter-of-fact,
not defensive. Pause before "zero point one seven".*

```text
This is what every flat tool sees — BubbleUp, compare, Trace Patterns. Its best single
predicate lands at precision zero point one seven. The fault needs two conditions at once.
```

---

### seg06 · b4 — the compiler and the receipt  `[MEASURED 12.57s]`
**29 words ≈ 12.0s · headroom 0.3s — tightest segment, don't dawdle**
*Open cold on "No model wrote this" — no run-up. Read the expression as "A implies B, and not C" —
never "equals greater than". Time "SigNoz returned sixty-one" to the receipt snapping in.*

```text
No model wrote this. It's compiled into SigNoz's own grammar — A implies B, and not C —
then run back against the engine. Mined sixty-one. SigNoz returned sixty-one.
```

---

### seg07 · s2 sketch — one store, not three  `[MEASURED 15.40s]`
**33 words ≈ 13.7s · headroom 1.4s**
*The "why SigNoz" beat, and the judges' actual question. Say it as an architectural fact, not a
pitch. The three drums are already struck through by the time you reach "Tempo plus Loki" —
that last sentence is the close, so drop the pitch slightly and stop.*

```text
And this is why it has to be SigNoz. Traces and logs live in one ClickHouse, so a single
scan joins them by trace ID. On Tempo plus Loki, that join doesn't exist.
```

---

### seg08 · b5 — the permalink in Trace Explorer  `[MEASURED 28.30s]`
**47 words ≈ 19.4s · headroom 8.6s**
*Emphasis: "the real UI" — the point is this isn't a mock. Slow down on the last clause; the flame
graph is doing the proving.*

```text
That permalink opens the machine-written query in SigNoz's own Trace Explorer — all three
leaves and the operator, rendered in the real UI. The result set collapses to the matched
traces. Open one, and the flame graph shows the shape: payment retries redis, and
flag-service never ran.
```

---

### seg09 · b6 — arm it  `[MEASURED 30.97s]`
**66 words ≈ 27.3s · headroom 3.4s**
*Emphasis: "the rule ID in that payload is the rule the command just created" is the proof it's real,
not a mock webhook — say it deliberately. The last sentence is the thesis; land it.*

```text
One flag arms it. The discriminator becomes a native v2alpha1 alert with warning and critical
thresholds. Replay the fault, and at t plus one eighty-two seconds the webhook fires — the
rule ID in that payload is the rule the command just created. Everyone else in this category
stops at a panel. None of them hand you back a query, a dashboard, and an armed tripwire.
```

---

### seg10 · b10 — abstention + the one it first got wrong  `[MEASURED 32.93s]`
**71 words ≈ 29.4s · headroom 3.3s**
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

### seg11 · b7 — determinism  `[MEASURED 25.40s]`
**34 words ≈ 14.1s · headroom 11.0s — you can take this one slowly**
*Emphasis: "no LLM anywhere in the runtime" is the differentiator in an AI hackathon. Say the last
sentence as a disclosure, not a defence.*

```text
Run it twice. Same input, same seed, same verdict hash. There is no LLM anywhere in the
runtime — this is deterministic. The corpus is synthetic and disclosed; ground truth comes
from a manifest.
```

---

### seg12 · b11 replay app — try it yourself  `[MEASURED 18.00s]`
**34 words ≈ 14.1s · headroom 3.6s**
*Emphasis: "you don't need my machine" is the point — it answers the judge's "can I actually try this".*

```text
And you don't need my machine to check any of it. The whole run is stepped through in the
browser — the board, the compiled query, the receipt, the hash — hosted, no install.
```

---

### seg13 · b8 — close  `[MEASURED 18.23s]`
**26 words ≈ 10.8s · headroom 7.2s**
*Slow down. This is the tagline; let it sit. Beat of silence before "Everything's on GitHub".*

```text
Everyone can show you the difference. Only SigNoz can arm it. Everything's on GitHub — one
command reproduces the whole run, casting file and lock committed.
```

---

## Budget

All thirteen windows are ffprobe-measured off `tools/video/manifest.json`; the film total is
the assembled `demo-silent.mp4`, which is shorter than the column sum because consecutive
beats overlap by one 0.3s crossfade.

| seg | beat | starts | window | words | ≈ speech | headroom |
|---|---|--:|--:|--:|--:|--:|
| 01 | **b9t landing** | 0.00 | 44.60 | 104 | 43.0s | +1.3 |
| 02 | b1 citation | 44.30 | 12.00 | 25 | 10.3s | +1.4 |
| 03 | **s1 sketch — the fault** | 56.00 | 23.70 | 51 | 21.1s | +2.3 |
| 04 | b2 board | 79.40 | 16.27 | 35 | 14.5s | +1.5 |
| 05 | b3 baseline | 95.36 | 13.83 | 30 | 12.4s | +1.1 |
| 06 | b4 receipt | 108.89 | 12.57 | 29 | 12.0s | +0.3 |
| 07 | **s2 sketch — one store** | 121.15 | 15.40 | 33 | 13.7s | +1.4 |
| 08 | b5 permalink | 136.25 | 28.30 | 47 | 19.4s | +8.6 |
| 09 | b6 arm it | 164.25 | 30.97 | 66 | 27.3s | +3.4 |
| 10 | b10 abstention | 194.91 | 32.93 | 71 | 29.4s | +3.3 |
| 11 | b7 determinism | 227.54 | 25.40 | 34 | 14.1s | +11.0 |
| 12 | b11 replay | 252.64 | 18.00 | 34 | 14.1s | +3.6 |
| 13 | b8 close | 270.34 | 18.23 | 26 | 10.8s | +7.2 |
| | **total** | | **288.63** | **585** | **≈4:02** | |

Every headroom is positive: **no segment overruns its measured window.** The one to watch in
the booth is **seg06** (+0.3s — open cold, don't dawdle); **seg05** (+1.1s) and **seg01**
(+1.3s) are next.

### What was trimmed against the v3 brief, and why

Two segments came in longer than the picture they sit on, and both were shortened rather
than letting the voice run past the cut. **No number, name or claim was removed.**

- **seg01** — the brief's draft was 116 words ≈ 48.0s. The *untrimmed* b9 is 46.10s, so
  "keep more of b9t rather than cut the words" bottoms out before it fits; b9t was pushed
  back up to **44.60s** (only 1.5s trimmed off b9, not the planned ~8s) *and* the copy came
  down to **104 words**. Cut: the sentence "Here's the problem it solves." (redundant — the
  next sentence is the problem); "by hand," (redundant with "re-types"); "can show you" →
  "shows you"; "the two cohorts" → "the cohorts"; "verify that query against" → "verify it
  against"; "Five stages, and no LLM anywhere" → "Five stages, no LLM anywhere"; and the
  opening clause re-punctuated to "I'm Abhishek. This is Whodunit, built for…".
  Everything load-bearing survives: the name, the hackathon and **Track 2, Signals
  and Dashboards**, the three competitors, "at three in the morning", all five stages, and
  "no LLM anywhere".
- **seg02** — the brief's draft was 28 words ≈ 11.6s against a 12.00s window (+0.1s, which
  is an overrun in practice). Trimmed to 25 by dropping "own" and collapsing "The issue is
  still open." to "— still open." **co-founder**, **three and a half years ago** and **still
  open** all survive.

Everything else is v2 copy, verbatim, renumbered.

## Numbers used — all real, all from the seed-778 run or the benchmark

- **13.1× lift**, **mined 61 = SigNoz 61**, verdict hash `95f8835…` — the seed-778 demo run
  (`docs/video/raw/explain-result.json`). The s1 sketch quotes **13.1× lift, 61 bad / 0 healthy**
  from the same file (`winner_lift`, `support_bad`, `support_healthy`).
- **precision 0.17** (seg05) — the flat baseline on the *same seed-778* matrix, matching what's on
  screen in b3. ⚠️ Not to be confused with **0.23**, which is the baseline on the benchmark's
  `conditional_dep` seed-101 run. Both are real; each is quoted only where it matches the footage.
- **six seeded faults · never a false culprit · the one it first got wrong** (seg10) — `benchmark/REPORT.md`
  and `benchmark/ISSUES.md` #2. On screen in b10, straight out of `benchmark/results.json`:
  6/6 pass, **0 false culprits**, ABSTAIN on `decoys` and `null_scenario`, PARTIAL on
  `retry_storm`, and the `cache_bypass` re-run at `(A => B) && NOT (C => D)`, recall 1.0,
  precision 1.0, **160/160** live match.
- **t+182s webhook** (seg09) — the real captured firing in `docs/video/raw/webhook.log`.
- **7,806 itemsets · 36 features · 6 survivors · 163,464 rows / 1,843 ms** — on screen in b2 and
  b9t, read out of the same run; not spoken, so they are never paraphrased.
- The s2 sketch makes an **architectural** claim only ("traces and logs in one ClickHouse, joined
  on trace ID; not possible across Tempo + Loki"). It quotes no run counters on purpose.
