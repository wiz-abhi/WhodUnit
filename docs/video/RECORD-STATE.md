# Recording state — the three new beats (v2 cut)

Resumable checklist for the second footage round. **Read this first.** Skip every
phase marked DONE; resume at the first PENDING one. Each phase is committed and
pushed before the next one starts, so an interruption costs at most one phase.

| phase | beat | what | target | measured | status |
|---|---|---|--:|--:|---|
| 1 | `b9`  | landing page scroll (`replay/index.html`) | ~46s | **46.10s** | **DONE** |
| 2 | `b10` | abstention + the one it first got wrong (termcast) | ~32s | **32.93s** | **DONE** |
| 3 | `b11` | the replay app (`replay/app.html`) | ~18s | **18.00s** | **DONE** |
| 4 | —     | re-cut: trims/manifest/assemble/script/captions | — | **251.63s** | **DONE** |

New beat order for the v2 cut: `b1, b9, b2, b3, b4, b5, b6, b10, b7, b11, b8`.
The static intro cards (`docs/video/intro/intro.mp4`) are **retired** — b9 replaces them.

## Phase 1 — `docs/video/raw/b9.mp4`, 46.10s

`record_browser.py b9`: one unbroken programmatic crawl down `replay/index.html`
at 1920x1080/30 — hero (headline, `13.1x` / `61 = 61` / `6 / 6` / `0` chips, the
honest banner) → the "nobody hands you the query" competitor table → the five
deterministic stages → the five SigNoz surfaces → a hold on the proof/receipt
section (the compiled `(A => B) && NOT C`, the verdict hash, the 6/6 table and
the `cache_bypass` loss-then-fix note). Scroll offsets are measured off the
rendered page; the fades are the site's own `animation-timeline: view()` reveal.
Raw take 47.43s, ffmpeg-trimmed to `[0.4, 46.5]` to drop the white pre-paint
frames at the head and the trailing slack.

## Phase 2 — `docs/video/raw/b10.mp4`, 32.93s

A termcast, so it matches b2/b3/b4 exactly: `tools/video/demo_abstention.py`
(new) renders straight out of `benchmark/results.json` — the machine-readable
record of the 946.5s live run behind `REPORT.md` — and `run_beat.py b10`
captures its real ANSI bytes into `docs/video/raw/casts/b10.json`.

Two typed steps: `--board` (the six-scenario table, with the two ABSTAIN rows
and the PARTIAL row marked `>` and coloured, then `6/6 pass · 0 false culprits
across all six`) and `--miss cache_bypass` (the original ABSTAIN, the
absence-only compiler refusal quoted verbatim from the run's `refusals`, the MDL
dominance prune that dropped the compilable superset, the `_select_finding` fix,
and the re-run: `(A => B) && NOT (C => D)`, recall 1.0, precision 1.0,
160/160 live match, original failure kept in `benchmark/ISSUES.md` #2).

Rendered at `--font 22`: at 24 the 150-column rich panels land exactly on the
1872 px content width and the last glyph column clips.

## Phase 3 — `docs/video/raw/b11.mp4`, 18.00s

`record_browser.py b11`: land on the app shell (step 1/7, top bar + left rail
+ footer progress), then `ArrowRight` x3 to the elimination board (2/7), the
compiled trace-operator (3/7) and the verification receipt (4/7), where
`#btnVerify` is pressed so the cells snap in — **mined 61 · SigNoz 61 · MATCH**,
precision 1.00 / recall 1.00, 46,805 rows — and held for ~4s.

The viewport never moves: `app.html` is a fixed 100vh shell whose
`document.scrollHeight` equals `innerHeight` (probed: 1080 == 1080), and only
`#panel` scrolls, so the frame is nailed while the panel swaps underneath.
No pointer is used for navigation, so no cursor is in frame. Raw take 19.43s,
ffmpeg-trimmed to `[0.4, 18.4]`.

## Phase 4 — the re-cut, `docs/video/demo-silent.mp4` at 251.63s (4:11.6)

| seg | beat | starts | window |
|---|---|--:|--:|
| 01 | b1 citation | 0.00 | 12.00 |
| 02 | **b9 landing** | 11.70 | **46.10** |
| 03 | b2 board | 57.50 | 16.27 |
| 04 | b3 baseline | 73.46 | 13.83 |
| 05 | b4 receipt | 86.99 | 12.57 |
| 06 | b5 permalink | 99.25 | 28.30 |
| 07 | b6 arm it | 127.25 | 30.97 |
| 08 | **b10 abstention** | 157.91 | **32.93** |
| 09 | b7 determinism | 190.54 | 25.40 |
| 10 | **b11 replay** | 215.64 | **18.00** |
| 11 | b8 close | 233.34 | 18.23 |

Every duration is ffprobe-measured. What changed beyond the trims:

- `assemble.py` / `make_manifest.py` cap raised 170s -> **270s** (4:30): the demo cut is
  now the whole film, so the cap guards the 5:00 submission limit with ~30s of margin
  instead of the old intro+demo split's 2:50. Assembled cut lands 18.37s under it.
- `make_manifest.py` `predicted_total_s` no longer subtracts the crossfades twice
  (beat starts already back off one crossfade), so it now agrees with the assembled
  measurement: predicted 251.57s vs measured 251.63s.
- `build_captions.py` reads `docs/NARRATION-SCRIPT-v2.md`, `INTRO_SEGMENTS` is empty
  (intro manifest no longer required) and `DEMO_SEGMENTS` is the new 11-beat order.
- `final_assemble.py` no longer requires an intro half; `--intro FILE` puts one back.
- `docs/video/NARRATION-SCRIPT.md` (v1) carries a SUPERSEDED banner.

**Captions: 41 cues, no overruns.** Tightest is seg05/b4 at +0.3s headroom and seg04/b3
at +1.1s — both pre-existing and already flagged in the script. No narration copy needed
trimming, so every real number in it survives. Silent captioned preview:
`docs/video/demo-captioned-preview.mp4`, **251.633s (4:11.6)**.

## Notes

- Raw mp4s are gitignored by `docs/video/.gitignore`; b9/b10/b11 are force-added
  (`git add -f`) because they are new source footage.
- The landing/app beats are recorded against a **local** `python -m http.server 8099`
  serving `replay/`, byte-identical to the deployed Space.
- Do not touch `b1`–`b8`.
