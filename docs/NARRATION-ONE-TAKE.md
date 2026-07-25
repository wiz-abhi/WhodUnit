# 🎙️ Whodunit — one-take recording script

**Read this top to bottom in a single recording.** I'll split it into the 13 segments
automatically and sync each one to its beat. Total speech ≈ 4 min 2 s; with the pauses,
expect a file around **4 min 45 s**.

> This is the **v3 sketch cut** (13 beats, 4:48.6). It matches
> `docs/NARRATION-SCRIPT-v3.md` word for word — that file is the source of truth for the
> burned captions, so don't paraphrase. Two of the beats (segments **3** and **7**) are
> hand-drawn animated sketches, not screen recordings.

---

## Before you start

| | |
|---|---|
| **Record** | One continuous file. Phone voice memo is fine. |
| **Format** | Anything (`.m4a`, `.mp3`, `.wav`) — I'll convert. Higher quality is better. |
| **Mic** | ~20 cm from your mouth, angled slightly off to the side (stops popping on "p" sounds). |
| **Room** | Quiet, soft furnishings if possible. Fan/AC off. Phone on Do Not Disturb. |
| **Save as** | `audio/full-take.m4a` (or wherever — just tell me the path). |

---

## The three rules that make this work

**1. Start with 3 seconds of silence.** Hit record, count to three in your head, *then* speak.

**2. Leave a clear 3-second gap between every segment.** This is how I find the splits.
Count *"one-thousand-one, one-thousand-two, one-thousand-three"* silently at each ⏸ marker.
**Do not pause for 3 seconds in the middle of a segment** — that would create a false split.
Natural half-second breaths inside a segment are completely fine.

**3. If you fluff a line — don't panic, and don't start over.**
Stop, pause 3 seconds, and **re-read that whole segment from its beginning.** I'll keep the
last clean version and throw the rest away. You can retry a segment as many times as you like.

Pace: **conversational, ~145 words per minute.** Every segment has headroom — you do not need
to rush. Read it like you're explaining it to one competent engineer at their desk. Flat and
certain beats enthusiastic.

*(Italic lines are direction — don't read them aloud.)*

---
---

# ▶ START RECORDING

*(3 seconds of silence first)*

---

## 1

*The longest one — 44 seconds of picture, so you have room. Your name and the track go by
quickly; the weight is on "at three in the morning". Pause after "morning". The five stages
are a list, don't sing them. Hit "no LLM anywhere" cleanly — it's the claim people doubt.*

> I'm Abhishek. This is Whodunit, built for the Agents of SigNoz hackathon — Track 2,
> Signals and Dashboards. When production breaks, every observability tool shows you the
> difference between the traces that failed and the ones that didn't. BubbleUp, Trace
> Patterns, Grafana's compare — they rank attributes and hand you a panel. Then a human
> re-types that finding into a query, at three in the morning. Whodunit closes that loop.
> One ClickHouse scan, mine the pattern that separates the cohorts, compile it into a real
> SigNoz query, verify it against the live engine, and arm it as an alert. Five stages,
> no LLM anywhere.

## ⏸ pause 3s

---

## 2

*Land on "still open" — that's the whole reason the project exists. No triumph in the voice;
it's a fact you're pointing at.*

> And this isn't a problem I invented for a hackathon. SigNoz's co-founder asked for exactly
> this, three and a half years ago — still open.

## ⏸ pause 3s

---

## 3

*Over the hand-drawn sketch. Slow and explanatory — the one beat where you're teaching, not
proving. Let each "also in healthy traces" sit for a beat. "Only both at once" is the payoff.*

> Here's the fault, drawn. A healthy checkout calls the flag service. A failing one retries
> redis, and the flag-service span is missing. But the retry alone shows up in healthy traces
> too. And plenty of healthy traces skip the flag check. Neither condition alone separates
> them — only both at once.

## ⏸ pause 3s

---

## 4

*The near-misses sound dismissive; "only the conjunction" is the answer landing.*

> One question to ClickHouse. Then the whole lattice is enumerated locally. The machine weighs
> the obvious answers — the edge alone — and rejects them. Only the conjunction separates the
> cohorts, at thirteen times lift.

## ⏸ pause 3s

---

## 5

*Stress "every flat tool" — you're pre-empting "isn't this just BubbleUp?". Matter-of-fact, not
defensive. Small pause before the number.*

> This is what every flat tool sees — BubbleUp, compare, Trace Patterns. Its best single
> predicate lands at precision zero point one seven. The fault needs two conditions at once.

## ⏸ pause 3s

---

## 6

*Open cold on "No model wrote this" — no run-up. Say the expression as "A implies B, and not C"
— never "equals greater than". **This is the tightest segment — keep it moving.***

> No model wrote this. It's compiled into SigNoz's own grammar — A implies B, and not C —
> then run back against the engine. Mined sixty-one. SigNoz returned sixty-one.

## ⏸ pause 3s

---

## 7

*Over the second hand-drawn sketch — the "why SigNoz" beat, and the judges' actual question.
An architectural fact, not a pitch. Drop the pitch slightly on the last sentence and stop.*

> And this is why it has to be SigNoz. Traces and logs live in one ClickHouse, so a single
> scan joins them by trace ID. On Tempo plus Loki, that join doesn't exist.

## ⏸ pause 3s

---

## 8

*"The real UI" is the point — this isn't a mock. Slow down on the last clause.*

> That permalink opens the machine-written query in SigNoz's own Trace Explorer — all three
> leaves and the operator, rendered in the real UI. The result set collapses to the matched
> traces. Open one, and the flame graph shows the shape: payment retries redis, and
> flag-service never ran.

## ⏸ pause 3s

---

## 9

*"The rule ID in that payload is the rule the command just created" is the proof it's real —
say it deliberately. The last sentence is the thesis; land it.*

> One flag arms it. The discriminator becomes a native v2alpha1 alert with warning and critical
> thresholds. Replay the fault, and at t plus one eighty-two seconds the webhook fires — the
> rule ID in that payload is the rule the command just created. Everyone else in this category
> stops at a panel. None of them hand you back a query, a dashboard, and an armed tripwire.

## ⏸ pause 3s

---

## 10

*The most important segment in the video. Deliver it plainly — no apology, no bragging. The
last sentence is the line judges remember.*

> Here's what matters more. Point it at a decoy — an attribute that tracks failure but doesn't
> cause it — and it abstains. Point it at a healthy system, it abstains again. Across six
> seeded faults, it never named a false culprit. And this one it first got wrong — it abstained
> where a real answer existed. I found the seam, fixed it, and left the original failure in the repo.

## ⏸ pause 3s

---

## 11

*"No LLM anywhere in the runtime" is the differentiator in an AI hackathon. Say the last
sentence as a disclosure, not a defence. **Lots of headroom — take this one slowly.***

> Run it twice. Same input, same seed, same verdict hash. There is no LLM anywhere in the
> runtime — this is deterministic. The corpus is synthetic and disclosed; ground truth comes
> from a manifest.

## ⏸ pause 3s

---

## 12

*"You don't need my machine" is the point — it answers "can I actually try this?".*

> And you don't need my machine to check any of it. The whole run is stepped through in the
> browser — the board, the compiled query, the receipt, the hash — hosted, no install.

## ⏸ pause 3s

---

## 13

*Slow down. This is the tagline; let it sit. Small beat of silence before "Everything's on
GitHub".*

> Everyone can show you the difference. Only SigNoz can arm it. Everything's on GitHub — one
> command reproduces the whole run, casting file and lock committed.

---

# ■ STOP RECORDING

*(let it run 3 seconds after your last word before you stop)*

---
---

## Then send it to me

Save the file and tell me where it is — e.g. *"recorded at `audio/full-take.m4a`"*.

I'll then:
1. Split it into 13 segments on the silence gaps
2. Verify each segment against its expected duration (so a bad split can't slip through)
3. If you re-took any segment, keep the last clean version
4. Lay each segment onto its beat at the right offset
5. Burn the captions and hand you the finished MP4

If any segment overruns its beat, I'll tell you which one rather than speeding your audio up —
a re-read of one segment is a 20-second fix.

---

### Pronunciation notes

| Written | Say |
|---|---|
| `A => B` | "A implies B" *(never "equals greater than")* |
| `NOT C` | "and not C" |
| `v2alpha1` | "v-two-alpha-one" |
| `clickhouse_sql` | "ClickHouse S-Q-L" |
| `0.17` | "zero point one seven" |
| `t+182s` | "t plus one eighty-two seconds" |
| `trace_id` | "trace ID" |
| DDx | "D-D-X" |
| FP-growth | "F-P growth" |
