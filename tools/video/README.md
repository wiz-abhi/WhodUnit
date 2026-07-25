# tools/video — the submission video pipeline

Everything here is *tooling*: no product behaviour lives in this directory, and
nothing here is imported by `src/whodunit`.

Two halves, one output. **Shape of the finished video — target ≈ 3:59, cap 5:00:**

```
docs/video/intro/intro.mp4     69.000 s   5 title cards  (intro/,   rendered)
docs/video/demo-silent.mp4    ~170    s   8 demo beats   (capture pipeline)
                              --------
docs/video/whodunit-final.mp4 ~239    s   + narration + burned captions
```

- **Capture half** — `record_*.py`, `beats/`, `trims.json`, `make_manifest.py`,
  `assemble.py` → `docs/video/demo-silent.mp4` + `manifest.json`. Documented below.
- **Presentation half** — `intro/`, `captions/`, `final_assemble.py`, and
  `docs/video/NARRATION-SCRIPT.md`. Documented in
  [Intro, narration, captions, final cut](#intro-narration-captions-final-cut).

---

## Demo footage pipeline

Re-runnable capture + assembly for the submission video's demo segment (≤ 2:50).

```
beats.json           what each terminal beat actually types and runs
run_beat.py          runs a beat LIVE, stores its raw ANSI + measured elapsed
record_termcast.py   renders a stored beat offscreen (headless chromium) -> raw/<beat>.mp4
record_browser.py    headless Playwright chromium @1920x1080             -> raw/<beat>.mp4
_console.py          rich Console factory (colour when captured through a pipe)
demo_explain.py      the on-camera `whodunit explain`, trace-id scoped
demo_baseline.py     the on-camera flat BubbleUp-style baseline
show_readme.py       README render for the closing beat
webhook_listener.py  :9099 listener that logs the fired alert POST
trickle.py           keeps the alert's 5m rolling window fed with matching traces
trims.json           EDITABLE spec: which segments of each raw take to keep
make_manifest.py     trims.json + ffprobe + the cached live run -> manifest.json
assemble.py          manifest.json -> docs/video/demo-silent.mp4 (0.3s crossfades)
```

## Pre-flight (why `demo_explain.py` exists)

The shared stack holds several overlapping `whodunit-demo` corpora and
`clickhouse_sql` ignores the envelope time window (`benchmark/ISSUES.md` #1), so
a plain time-scoped `whodunit explain` pulls other runs into the healthy cohort.
`demo_explain.py` is `benchmark/pipeline_scoped.py`'s driver: it reconstructs one
run's exact trace-id set from `(seed, index)` and hands explicit bad + healthy
sets to the *real* engines, then renders with `whodunit.cli.render` verbatim.

Two things have to line up for a clean on-camera receipt:

1. **A never-used seed.** `python -m corpus.generate --traces 800 --seed 777
   --fault conditional_dep --fault-rate 0.11 --duration-hours 0.01` (needs the
   OTel interpreter, see `benchmark/README.md`).
2. **A window that ends before any later traffic.** The scan is id-scoped, but
   differential *verification* is a builder query and DOES honour the window —
   so `WHODUNIT_WINDOW_END_MS` is pinned just after the corpus and before
   `trickle.py` starts feeding the alert beat. Otherwise `mined` and `SigNoz`
   diverge on camera for a reason that has nothing to do with the product.

Dry-run until `verdict = discriminator`, `match = true`, `precision = 1.0`:

```bash
uv run python tools/video/demo_explain.py --latest conditional_dep --json
```

## Recording

```bash
export SIGNOZ_URL=... SIGNOZ_EMAIL=... SIGNOZ_PASSWORD=... SIGNOZ_ORG_ID=...
export WHODUNIT_WINDOW_END_MS=...        # see above

# 1. run the beat for real; store the bytes it printed + how long it took
uv run python tools/video/run_beat.py b2 b3 b4 b7 b8

# 2. render those stored bytes to 1080p, offscreen
python tools/video/record_termcast.py b2      # OTel/Playwright interpreter
python tools/video/record_browser.py b1       # browser beats
```

**Why the terminal beats are rendered rather than screen-grabbed.** A desktop
`gdigrab` capture needs the terminal held on top for the whole take, which makes
the machine unusable while a ~12-minute `explain` runs — and anything its owner
does lands in the footage. `run_beat.py` therefore executes the real command and
keeps its exact stdout bytes; `record_termcast.py` replays those bytes in a
terminal-styled page. What you see is the program's own output, byte for byte,
with two disclosed presentation changes: `_console.py` makes `rich` emit ANSI
through a pipe, and the minutes-long mine plays back as a few seconds of spinner
whose counter ramps to — and then prints — the true elapsed time.

Credentials are read from the environment and typed into the live login form;
they are never written into a committed file.

## Assembling

```bash
uv run python tools/video/make_manifest.py    # measures every raw take
uv run python tools/video/assemble.py         # -> docs/video/demo-silent.mp4
```

`assemble.py` exits non-zero if the cut runs over 2:50.

---

## Intro, narration, captions, final cut

### The one command

Once `docs/video/demo-silent.mp4` exists and the narration is recorded:

```powershell
python tools/video/final_assemble.py
```

That single command rebuilds the captions from the narration script, normalises and
concatenates intro + demo, places each `audio/segNN.wav` at its manifest offset, burns
the captions, and writes `docs/video/whodunit-final.mp4` — H.264 high@4.1, yuv420p,
1920x1080@30, AAC 192k stereo 48 kHz, `+faststart`.

**Preview without recording anything:**

```powershell
python tools/video/final_assemble.py --no-audio
```

Same picture, same burned captions, no audio track and no `.wav` files required — use
it to check caption timing and the intro→demo seam before you open a microphone.

Other flags: `--audio-dir take2`, `--out docs/video/cut2.mp4`, `--intro`, `--demo`,
`--keep-work` (leaves intermediates in `docs/video/.work/`).

### Full sequence, from nothing

```powershell
# 1. Render the intro (HTML cards -> PNG -> MP4). ~1 minute.
#    Needs the interpreter that carries playwright + chromium:
C:/Users/abhis/Desktop/OSS/Signoz/warmup-agent/.venv/Scripts/python.exe `
    tools/video/intro/render_intro.py

# 2. Record and assemble the demo beats (see the section above).
uv run python tools/video/make_manifest.py
uv run python tools/video/assemble.py

# 3. Check every narration block still fits, now that the beats are measured.
python tools/video/captions/build_captions.py --check

# 4. Record audio/seg01.wav .. seg13.wav following docs/video/NARRATION-SCRIPT.md.

# 5. Assemble.
python tools/video/final_assemble.py
```

Step 3 exits non-zero if any narration block would overrun its beat, and prints a
per-segment window / word count / estimated speech / headroom table. Fix the script
before recording, not after.

### What lives where

| Path | What it is |
|---|---|
| `intro/cards/*.html` | The five intro cards. Self-contained: system fonts, no CDN, no external assets. Open one in a browser to edit it. |
| `intro/render_intro.py` | Cards → PNG (Chromium @2x) → per-card MP4 (fade in/out) → `intro.mp4`, and writes the measured manifest. |
| `intro/intro-manifest.json` | **Measured** per-card durations and start offsets (ffprobe, not intent). |
| `docs/video/intro/` | Rendered output: `cards/*.png`, `segments/*.mp4`, `intro.mp4`. |
| `docs/video/NARRATION-SCRIPT.md` | **The human deliverable.** One block per segment with the exact words, target duration, and emphasis notes — and the single source of truth for caption text. |
| `captions/build_captions.py` | Narration markdown + both manifests → `docs/video/CAPTIONS.srt`. `--check` for the timing report only. |
| `final_assemble.py` | intro + demo + `audio/seg*.wav` + captions → `docs/video/whodunit-final.mp4`. |
| `audio/segNN.wav` | Your recordings. Not in git. |

### How timing works

One timeline, three consumers, so nothing can drift:

1. `intro/intro-manifest.json` gives the **measured** duration of each intro card.
2. `manifest.json` gives each demo beat's **measured** `cut_duration_s` and its
   `timeline_start_s` — the beats crossfade, so their starts are deliberately *not*
   the running sum of their durations, and the caption builder uses the manifest's
   own offsets rather than re-deriving them. Until `manifest.json` exists it falls
   back to the `docs/DEMO-RUNBOOK.md` targets and labels those rows
   `SYNC-TO-MANIFEST`.
3. Voice and captions are both placed at `segment_start + lead_in` — 0.3 s, or the
   manifest's `voice_lead_s` for demo beats. The voice starts a beat after its visual
   lands, never on the cut. Cues within a segment are spread across the block's
   estimated speech duration (words ÷ 145 wpm) and hard-clamped inside the segment, so
   a cue can never bleed into the next beat.

### Caption style

White text on a semi-transparent black box, bottom-centred, `FontSize=27`, 112 px
bottom margin (clears both the intro cards' footer line and a terminal's last line).
At most **2 lines of 42 characters**; cues break at sentence ends where they can, and a
bare connector is never left stranded at a cue boundary.

Style lives in `ASS_STYLE` in `final_assemble.py`. One non-obvious detail documented
there: an SRT converts to an ASS with `PlayRes 384x288`, so libass would scale
`FontSize=27` up by 3.75× to ~101 px. The assembler rewrites `PlayResX/Y` to 1920x1080
before burning, which makes `FontSize` mean pixels. Don't switch back to
`subtitles=...:force_style=...` without re-checking the rendered size.

### Editing the intro

Card content is plain HTML + CSS in `intro/cards/`. `_base.css` holds the shared dark
palette and typography; each card adds its own layout. To change durations, edit the
`CARDS` tuple in `render_intro.py` — the manifest records what actually rendered, so
the caption builder follows automatically (re-run `build_captions.py --check` after).
`render_intro.py --png-only` renders just the PNGs: the fast loop while adjusting
layout.

Cards render as a static hold with a 0.6 s fade in and out. A Ken Burns push was tried
and abandoned: measured on this machine, ffmpeg's `zoompan` costs ~1 s of wall-clock per
output frame on a 4K still — a ~45-minute render for a 69-second segment — and the
cards are dense enough that motion hurts readability anyway.

### Requirements

- `ffmpeg` / `ffprobe` on `PATH` (built and tested against 8.1.2).
- Python 3.11+ for `build_captions.py` and `final_assemble.py` (stdlib only).
- Playwright + Chromium for `render_intro.py` only.

`final_assemble.py` fails fast with a useful message if `intro.mp4` or
`demo-silent.mp4` is missing, and degrades to a silent cut (warning per missing file)
if some or all `segNN.wav` are absent — so a partial voice-over still assembles.
