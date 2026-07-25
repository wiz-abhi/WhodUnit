# Whodunit — narration script

**This is the file you record from.** One block per on-screen segment, in order. Each
block gives you the window it has to fit inside, the exact words, and what to lean on.

- **Pace target: 145 wpm** (≈ 2.4 words/second). Every block below is word-counted
  against its window and lands 1–4 seconds *short* on purpose. Narration must never
  overrun its visual.
- **Start speaking 0.3 s after the cut**, not on it. The assembler places every audio
  file at `segment_start + 0.3 s`. Let the picture land first.
- **Record one file per block**: `audio/seg01.wav` … `audio/seg13.wav`. Do not attempt a
  single continuous take (see [Recording instructions](#recording-instructions)).
- Read it like you're explaining it to one engineer at their desk. No trailer voice, no
  "revolutionary", no rising inflection at the end of statements.

Segment map — intro `seg01–seg05` (69.000 s, measured), demo `seg06–seg13`
(2:50 target, `[SYNC-TO-MANIFEST]`). Planned total **≈ 3:59**, under the 5:00 cap.

| # | file | visual | window | words | est. speech |
|---|---|---|--:|--:|--:|
| seg01 | `audio/seg01.wav` | intro card 1 — title | 10.000 s ✅measured | 19 | 7.9 s |
| seg02 | `audio/seg02.wav` | intro card 2 — the problem | 15.000 s ✅measured | 32 | 13.2 s |
| seg03 | `audio/seg03.wav` | intro card 3 — pipeline + stack | 16.000 s ✅measured | 34 | 14.1 s |
| seg04 | `audio/seg04.wav` | intro card 4 — five SigNoz surfaces | 16.000 s ✅measured | 34 | 14.1 s |
| seg05 | `audio/seg05.wav` | intro card 5 — the numbers | 12.000 s ✅measured | 25 | 10.3 s |
| seg06 | `audio/seg06.wav` | b1 — the citation (#1957) | 12 s ⏳ | 23 | 9.5 s |
| seg07 | `audio/seg07.wav` | b2 — one scan + elimination board | 33 s ⏳ | 72 | 29.8 s |
| seg08 | `audio/seg08.wav` | b3 — the flat baseline fails | 20 s ⏳ | 36 | 14.9 s |
| seg09 | `audio/seg09.wav` | b4 — compiler + verification receipt | 30 s ⏳ | 62 | 25.7 s |
| seg10 | `audio/seg10.wav` | b5 — permalink in Trace Explorer | 25 s ⏳ | 46 | 19.0 s |
| seg11 | `audio/seg11.wav` | b6 — arm it, webhook fires | 25 s ⏳ | 52 | 21.5 s |
| seg12 | `audio/seg12.wav` | b7 — determinism | 15 s ⏳ | 34 | 14.1 s |
| seg13 | `audio/seg13.wav` | b8 — prior art + the cast | 10 s ⏳ | 17 | 7.0 s |

✅ = measured from rendered footage (`tools/video/intro/intro-manifest.json`).
⏳ = `[SYNC-TO-MANIFEST]` — target from `docs/DEMO-RUNBOOK.md`; re-check against
`tools/video/manifest.json` once the demo beats are recorded (see
[Syncing to the demo manifest](#syncing-to-the-demo-manifest)).

---

## Part 1 — Intro (69.000 s, measured)

### seg01 · intro card 1 — title

- **video:** `docs/video/intro/segments/card1.mp4`
- **window:** 10.000 s (measured) · **speak from** 0.3 s
- **words:** 19 → ≈ 7.9 s @ 145 wpm · **2.1 s of headroom**
- **emphasis:** hit `Only` and `arm`. Half-beat pause after "difference." — the tagline
  is a two-part sentence and the contrast is the whole pitch. Do not smile through it.

```text
This is Whodunit. Everyone can show you the difference between two sets of traces.
Only SigNoz can arm it.
```

### seg02 · intro card 2 — the problem

- **video:** `docs/video/intro/segments/card2.mp4`
- **window:** 15.000 s (measured) · **speak from** 0.3 s
- **words:** 32 → ≈ 13.2 s @ 145 wpm · **1.5 s of headroom**
- **emphasis:** "grinding" is the word that earns the card — say it slightly slower than
  the rest. Read the three product names flat and quick, like a list you're bored of.
  Land hard on the last four words: "you type the query yourself."

```text
Root cause at three a.m. is a human grinding filter permutations in a query builder.
BubbleUp, Trace Patterns, compare — they all show you the difference. Then you type
the query yourself.
```

### seg03 · intro card 3 — what it does, and the stack

- **video:** `docs/video/intro/segments/card3.mp4`
- **window:** 16.000 s (measured) · **speak from** 0.3 s
- **words:** 34 → ≈ 14.1 s @ 145 wpm · **1.6 s of headroom**
- **emphasis:** "one question" against "seven thousand eight hundred" is the contrast —
  the whole architecture is that asymmetry. Say the numbers as words, not digits.
  Final three words are flat and final: "No model involved."

```text
Whodunit asks ClickHouse one question, then ranks seven thousand eight hundred
candidate patterns locally in Python — polars, hand-rolled FP-growth — and compiles
the winner into a real SigNoz trace-operator query. No model involved.
```

### seg04 · intro card 4 — how it uses SigNoz

- **video:** `docs/video/intro/segments/card4.mp4`
- **window:** 16.000 s (measured) · **speak from** 0.3 s
- **words:** 34 → ≈ 14.1 s @ 145 wpm · **1.6 s of headroom**
- **emphasis:** "the same database" is the SigNoz-specific claim — put weight on *same*.
  Read the final four artifacts as a list with even spacing, one per checkmark; the
  viewer is reading along with you.
- **pronunciation:** "clickhouse-S-Q-L", "Perses v-six", "query-builder expression".

```text
It leans on five surfaces. One clickhouse-sql scan joins traces and logs in the same
database. The finding becomes a query-builder expression, a Trace Explorer link, a
Perses v6 panel, and an armed alert.
```

### seg05 · intro card 5 — the honest numbers

- **video:** `docs/video/intro/segments/card5.mp4`
- **window:** 12.000 s (measured) · **speak from** 0.3 s
- **words:** 25 → ≈ 10.3 s @ 145 wpm · **1.7 s of headroom**
- **emphasis:** "six out of six" gets a small pause in front of it, nothing after.
  "honest" and "abstain" carry the second half — the abstentions are a feature, so
  don't apologise for them with your tone.

```text
Six seeded faults, run live: six out of six. Three discriminators found at full
recall, and three where the only honest answer was to abstain.
```

---

## Part 2 — Demo beats `[SYNC-TO-MANIFEST]`

Windows below are the `docs/DEMO-RUNBOOK.md` targets. Once
`tools/video/manifest.json` exists, run the sync check in
[Syncing to the demo manifest](#syncing-to-the-demo-manifest) — if a measured beat is
shorter than its target, trim the marked optional clause rather than speeding up.

### seg06 · b1 — the citation

- **video:** `docs/video/raw/b1.mp4` (GitHub issue #1957)
- **window:** 12 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 23 → ≈ 9.5 s @ 145 wpm · **2.2 s of headroom**
- **emphasis:** "three and a half years" slow, "still open" slower. Frame it as
  authorship and longevity — **do not** say or imply community demand; the issue has
  zero reactions and a judge can check.

```text
SigNoz's co-founder opened this issue three and a half years ago. Compare two sets of
filtered spans. It's still open. Here's the implementation.
```

### seg07 · b2 — one scan, the elimination board

- **video:** `docs/video/raw/b2.mp4`
- **window:** 33 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 72 → ≈ 29.8 s @ 145 wpm · **2.9 s of headroom**
- **emphasis:** this is the longest block — breathe at every sentence break. The two
  near-misses should sound dismissive; the conjunction should sound like the answer.
  Time "Only the conjunction" to the moment the winning row highlights on screen.
- **optional trim** if the measured beat comes in short: drop the final sentence
  ("Sixty-one bad traces, zero healthy ones.") — costs 6 words / 2.5 s.
- **pronunciation:** "thirteen times lift"; say "sixty-one" clearly (matches screen).

```text
One question to ClickHouse. Then the whole lattice is enumerated locally. The
machine weighs the obvious answers — the edge alone — and rejects them. Only the
conjunction separates the cohorts, at thirteen times lift.
```

### seg08 · b3 — the honest baseline fails

- **video:** `docs/video/raw/b3.mp4`
- **window:** 20 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 36 → ≈ 14.9 s @ 145 wpm · **4.8 s of headroom**
- **emphasis:** "a proper BubbleUp-style z-test" — stress *proper*; you are pre-empting
  the strawman objection, and that only works if the tone is matter-of-fact rather
  than defensive. "zero point one seven" gets the pause.

```text
This is what every flat tool sees — BubbleUp, compare, Trace Patterns. Its best
single predicate lands at precision zero point one seven. The fault needs two
conditions at once.
```

### seg09 · b4 — the compiler and the verification receipt

- **video:** `docs/video/raw/b4.mp4`
- **window:** 30 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 62 → ≈ 25.7 s @ 145 wpm · **4.0 s of headroom**
- **emphasis:** open cold on "No model wrote this" — no run-up. Time "They agree" to
  the receipt snapping in. The last clause is the honesty mechanism; say it plainly,
  it's the strongest thing in the video.
- **pronunciation:** read the expression as "A implies B, and not C" — do not say
  "equals greater than".

```text
No model wrote this. It's compiled into SigNoz's own trace-operator grammar — A
implies B and not C — then run back against the engine. Mined sixty-one; SigNoz
returned sixty-one. They agree.
```

### seg10 · b5 — the permalink in Trace Explorer

- **video:** `docs/video/raw/b5.mp4`
- **window:** 25 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 46 → ≈ 19.0 s @ 145 wpm · **5.7 s of headroom**
- **emphasis:** "SigNoz's own Trace Explorer" — *own* is the point; this is not a
  screenshot of my UI. Slow down on the last clause and let the flame graph carry it:
  "the retry is there, flag-service isn't."

```text
That permalink opens the machine-written query in SigNoz's own Trace Explorer — all
three leaves and the operator, rendered in the real UI. The result set collapses to
the matched traces. Open one, and the flame graph shows the shape: the retry is
there, flag-service isn't.
```

### seg11 · b6 — arm it

- **video:** `docs/video/raw/b6.mp4` (stitched: arm command → webhook listener)
- **window:** 25 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 52 → ≈ 21.5 s @ 145 wpm · **3.5 s of headroom**
- **emphasis:** "One flag arms it" is the climax line — it should be the most confident
  four words in the recording. Time "the webhook fires" to the POST landing in the
  listener log. Then drop your energy for the competitive line; state it, don't sell it.
- **honesty note:** the alert genuinely fires at t+182s; the beat is stitched because
  the take is shorter than the fire delay. If asked, say so.

```text
One flag arms it. The discriminator becomes a native v2alpha1 alert with warn and
critical thresholds. Replay the fault, and at t plus one eighty-two seconds the
webhook fires. Everyone else in this category stops at a panel. None of them hand you
back a query, a dashboard, and an armed tripwire.
```

### seg12 · b7 — determinism

- **video:** `docs/video/raw/b7.mp4`
- **window:** 15 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 34 → ≈ 14.1 s @ 145 wpm · **0.6 s of headroom** — the tightest block in the demo
- **emphasis:** "no LLM anywhere in the runtime" is the Track-2 defence — say it once,
  clearly, and move on. The disclosure sentence is deliberately unglamorous; read it
  that way. It is a strength, not a confession.
- **optional trim** if the measured beat is under 14 s: drop the second sentence
  (the corpus disclosure) — it is also on card 5 — costs 12 words / 5.0 s.

```text
Run it twice. Same input, same seed, same verdict hash. There is no LLM anywhere in
the runtime — this is deterministic. The corpus is synthetic and disclosed; ground
truth comes from a manifest.
```

### seg13 · b8 — prior art and the cast

- **video:** `docs/video/raw/b8.mp4` (prior-art table → closing card)
- **window:** 10 s target `[SYNC-TO-MANIFEST]` · **speak from** 0.3 s
- **words:** 17 → ≈ 7.0 s @ 145 wpm · **2.7 s of headroom**
- **emphasis:** same tagline as seg01, same delivery — this is the bookend, so match
  the first read rather than escalating. Full stop after "arm it." Then the last
  sentence is dry and practical.

```text
Everyone can show you the difference. Only SigNoz can arm it. One command reproduces
the whole thing.
```

---

## Recording instructions

**Record segmented, not continuous.** Thirteen short files beat one four-minute take
for three reasons: a fluffed line costs you 10 seconds instead of 4 minutes; the
assembler places each file at its own manifest offset so your pauses never drift out
of sync with the picture; and if a demo beat gets re-recorded later, only one `.wav`
has to change.

**Room and mic**

- Quiet room, soft furnishings, door shut. Kill the fan, the fridge compressor if you
  can reach it, and anything with a coil whine. Phone on airplane mode, not silent.
- Mic roughly **20 cm** from your mouth, slightly off-axis (aim past your lips, not at
  them) so plosives miss the capsule. A sock or a folded tea towel in front of the mic
  works as a pop filter.
- Sit forward, don't lean back — chair creak is the single most common ruined take.
- Set input gain so normal speech peaks around **−12 to −6 dBFS**. If anything clips,
  the take is gone; redo it rather than fixing it later.

**Format**

- **WAV, 48 kHz, 16-bit, mono.** The assembler resamples to 48 kHz stereo AAC anyway,
  but record mono — a stereo take of one voice just doubles the file for nothing.
- Filenames exactly `seg01.wav` … `seg13.wav`, all in one directory (default `audio/`).

**Per take**

1. Read the block once silently to find the breath points.
2. Roll, wait **one full second** of silence, then speak. The leading silence gives the
   assembler and any noise-reduction pass something to work with — do not trim it to
   zero. (The 0.3 s lead-in is applied by the assembler on top of whatever silence you
   leave, so a little extra is harmless; a lot is not — keep it near 1 s.)
3. If you fluff a word, stop, breathe, and restart the whole block. Don't punch in.
4. After the last word, hold still for a second before you stop the recording.

**Check before you assemble**

- Read the block's word count. If your take is longer than the "est. speech" figure by
  more than a second, you're under 145 wpm — do it again slightly faster rather than
  letting captions and picture drift.
- `ffprobe -v error -show_entries format=duration -of csv=p=0 audio/seg07.wav` on the
  long ones. Anything longer than its window minus 0.5 s needs another take or the
  marked optional trim.

---

## Syncing to the demo manifest

The intro rows are measured. The demo rows (`seg06`–`seg13`) are runbook targets and
carry `[SYNC-TO-MANIFEST]` until `tools/video/manifest.json` lands with the real beat
durations. When it does:

```powershell
python tools/video/captions/build_captions.py --check
```

That prints, per segment, the measured window, the block's word count, the estimated
speech duration, and the headroom — and exits non-zero if any block would overrun its
beat. If a block overruns:

1. Take the **optional trim** noted in that block, if it has one.
2. Otherwise cut a clause — never speed up past ~160 wpm, it stops sounding like an
   engineer explaining something and starts sounding like a disclaimer.
3. Update both the words and the word count in this file; `build_captions.py` reads
   the fenced `text` blocks below each `##` heading as the single source of truth for
   caption content, so editing here is enough.
