# Recording state — the three new beats (v2 cut)

Resumable checklist for the second footage round. **Read this first.** Skip every
phase marked DONE; resume at the first PENDING one. Each phase is committed and
pushed before the next one starts, so an interruption costs at most one phase.

| phase | beat | what | target | measured | status |
|---|---|---|--:|--:|---|
| 1 | `b9`  | landing page scroll (`replay/index.html`) | ~46s | **46.10s** | **DONE** |
| 2 | `b10` | abstention + the one it first got wrong (termcast) | ~32s | — | PENDING |
| 3 | `b11` | the replay app (`replay/app.html`) | ~18s | — | PENDING |
| 4 | —     | re-cut: trims/manifest/assemble/script/captions | — | — | PENDING |

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

## Notes

- Raw mp4s are gitignored by `docs/video/.gitignore`; b9/b10/b11 are force-added
  (`git add -f`) because they are new source footage.
- The landing/app beats are recorded against a **local** `python -m http.server 8099`
  serving `replay/`, byte-identical to the deployed Space.
- Do not touch `b1`–`b8`.
