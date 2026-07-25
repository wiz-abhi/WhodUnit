# Whodunit — narration script (v2, 4:11.6 cut)

> ## ⚠️ SUPERSEDED — do not record from this file
>
> This is the v2 script for the retired 11-beat cut (`b1, b9, b2, b3, b4, b5, b6, b10, b7,
> b11, b8`, 251.63s). The shipped cut is the 13-beat v3 sketch cut:
> **[`docs/NARRATION-SCRIPT-v3.md`](NARRATION-SCRIPT-v3.md)** — it opens on the trimmed
> landing beat `b9t` and adds the two hand-drawn sketch beats `s1` and `s2`. v3 is what
> `tools/video/captions/build_captions.py` and `final_assemble.py` read.
> Kept only as the record of the earlier cut.


> **Status:** LOCKED — all eleven beats are shot and cut. Supersedes
> `docs/video/NARRATION-SCRIPT.md`. Every window below is `[MEASURED]` with ffprobe off
> `tools/video/manifest.json`; no target durations remain. Beat order is
> `b1, b9, b2, b3, b4, b5, b6, b10, b7, b11, b8`, assembled into
> `docs/video/demo-silent.mp4` at **251.63s**. The five static intro cards are retired —
> the recorded landing-page beat (b9) opens the film.
>
> Word counts are whitespace tokens of the fenced block, exactly as
> `tools/video/captions/build_captions.py` counts them, and the speech estimate is
> words ÷ 145 wpm. **No segment overruns its window.**

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

### seg01 · b1 — the cold open  `[MEASURED 12.00s]`
**24 words ≈ 9.9s · headroom 1.8s**
*Emphasis: land on "still open" — that's the whole reason the project exists. No triumph in the voice.*

```text
SigNoz's co-founder asked for this three and a half years ago — compare two sets of
filtered spans. It's still open. Here's the implementation.
```

---

### seg02 · b9 landing page — thesis + architecture  `[MEASURED 46.10s]`
**85 words ≈ 35.2s · headroom 10.6s**
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

### seg03 · b2 — the elimination board  `[MEASURED 16.27s]`
**35 words ≈ 14.5s · headroom 1.5s**
*Emphasis: the near-misses should sound dismissive; "only the conjunction" is the answer landing.
Time it to the winner row highlighting.*

```text
One question to ClickHouse. Then the whole lattice is enumerated locally. The machine weighs
the obvious answers — the edge alone — and rejects them. Only the conjunction separates the
cohorts, at thirteen times lift.
```

---

### seg04 · b3 — the honest baseline fails  `[MEASURED 13.83s]`
**30 words ≈ 12.4s · headroom 1.1s**
*Emphasis: stress "every flat tool" — you're pre-empting "isn't this just BubbleUp?". Matter-of-fact,
not defensive. Pause before "zero point one seven".*

```text
This is what every flat tool sees — BubbleUp, compare, Trace Patterns. Its best single
predicate lands at precision zero point one seven. The fault needs two conditions at once.
```

---

### seg05 · b4 — the compiler and the receipt  `[MEASURED 12.57s]`
**29 words ≈ 12.0s · headroom 0.3s — tightest segment, don't dawdle**
*Open cold on "No model wrote this" — no run-up. Read the expression as "A implies B, and not C" —
never "equals greater than". Time "SigNoz returned sixty-one" to the receipt snapping in.*

```text
No model wrote this. It's compiled into SigNoz's own grammar — A implies B, and not C —
then run back against the engine. Mined sixty-one. SigNoz returned sixty-one.
```

---

### seg06 · b5 — the permalink in Trace Explorer  `[MEASURED 28.30s]`
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

### seg07 · b6 — arm it  `[MEASURED 30.97s]`
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

### seg08 · b10 abstention + the one it first got wrong  `[MEASURED 32.93s]`
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

### seg09 · b7 — determinism  `[MEASURED 25.40s]`
**34 words ≈ 14.1s · headroom 11.0s — you can take this one slowly**
*Emphasis: "no LLM anywhere in the runtime" is the differentiator in an AI hackathon. Say the last
sentence as a disclosure, not a defence.*

```text
Run it twice. Same input, same seed, same verdict hash. There is no LLM anywhere in the
runtime — this is deterministic. The corpus is synthetic and disclosed; ground truth comes
from a manifest.
```

---

### seg10 · b11 replay app — try it yourself  `[MEASURED 18.00s]`
**34 words ≈ 14.1s · headroom 3.6s**
*Emphasis: "you don't need my machine" is the point — it answers the judge's "can I actually try this".*

```text
And you don't need my machine to check any of it. The whole run is stepped through in the
browser — the board, the compiled query, the receipt, the hash — hosted, no install.
```

---

### seg11 · b8 — close  `[MEASURED 18.23s]`
**23 words ≈ 9.5s · headroom 8.4s**
*Slow down. This is the tagline; let it sit. Beat of silence before "One command".*

```text
Everyone can show you the difference. Only SigNoz can arm it. One command reproduces the
whole thing — casting file and lock, committed.
```

---

## Budget

All eleven windows are ffprobe-measured off `tools/video/manifest.json`; the film total is
the assembled `demo-silent.mp4`, which is shorter than the column sum because consecutive
beats overlap by one 0.3s crossfade.

| seg | beat | starts | window | words | ≈ speech | headroom |
|---|---|--:|--:|--:|--:|--:|
| 01 | b1 citation | 0.00 | 12.00 | 24 | 9.9s | +1.8 |
| 02 | b9 landing | 11.70 | 46.10 | 85 | 35.2s | +10.6 |
| 03 | b2 board | 57.50 | 16.27 | 35 | 14.5s | +1.5 |
| 04 | b3 baseline | 73.46 | 13.83 | 30 | 12.4s | +1.1 |
| 05 | b4 receipt | 86.99 | 12.57 | 29 | 12.0s | +0.3 |
| 06 | b5 permalink | 99.25 | 28.30 | 47 | 19.4s | +8.6 |
| 07 | b6 arm it | 127.25 | 30.97 | 66 | 27.3s | +3.4 |
| 08 | b10 abstention | 157.91 | 32.93 | 71 | 29.4s | +3.3 |
| 09 | b7 determinism | 190.54 | 25.40 | 34 | 14.1s | +11.0 |
| 10 | b11 replay | 215.64 | 18.00 | 34 | 14.1s | +3.6 |
| 11 | b8 close | 233.34 | 18.23 | 23 | 9.5s | +8.4 |
| | **total** | | **251.63** | **478** | **≈3:18** | |

Every headroom is positive: **no segment overruns its measured window**, so no copy was
trimmed in the re-sync and every real number in the script survives. The two to watch in
the booth are **seg05** (+0.3s — open cold, don't dawdle) and **seg04** (+1.1s).

## Numbers used — all real, all from the seed-778 run or the benchmark

- **13.1× lift**, **mined 61 = SigNoz 61**, verdict hash `95f8835…` — the seed-778 demo run
- **precision 0.17** (seg04) — the flat baseline on the *same seed-778* matrix, matching what's on
  screen in b3. ⚠️ Not to be confused with **0.23**, which is the baseline on the benchmark's
  `conditional_dep` seed-101 run. Both are real; each is quoted only where it matches the footage.
- **six seeded faults · never a false culprit · the one it first got wrong** (seg08) — `benchmark/REPORT.md`
  and `benchmark/ISSUES.md` #2. On screen in b10, straight out of `benchmark/results.json`:
  6/6 pass, **0 false culprits**, ABSTAIN on `decoys` and `null_scenario`, PARTIAL on
  `retry_storm`, and the `cache_bypass` re-run at `(A => B) && NOT (C => D)`, recall 1.0,
  precision 1.0, **160/160** live match. ⚠️ The seed-101 `conditional_dep` baseline reads
  **0.23** on that board — the 0.17 in seg04 is the seed-778 matrix; do not swap them.
- **t+182s webhook** (seg07) — the real captured firing in `docs/video/raw/webhook.log`
