#!/usr/bin/env python
"""Build CAPTIONS.srt from docs/NARRATION-SCRIPT-v3.md + the measured timelines.

The narration markdown is the single source of truth for caption *text*: every
``## segNN · ...`` heading owns one fenced ``text`` block, and that block's words are
what gets burned on screen. Timing comes from the two manifests:

* ``tools/video/intro/intro-manifest.json`` — measured intro segment durations (mine).
* ``tools/video/manifest.json``             — measured demo beat durations (recorded by
  the demo-capture tooling). If it is absent, the runbook target durations in
  ``FALLBACK_BEATS`` are used and every affected row is flagged SYNC-TO-MANIFEST.

Within a segment the words are chunked into caption cues of at most two lines of
<= 42 characters, and the cues are spread evenly across the segment's *estimated
speech duration* (word count / 145 wpm), starting ``LEAD_IN`` seconds after the
segment's own start. That matches how the narration is recorded and how
``final_assemble.py`` places the audio, so captions, voice and picture agree.

Usage
-----
    python tools/video/captions/build_captions.py            # write CAPTIONS.srt
    python tools/video/captions/build_captions.py --check    # timing report, no write
    python tools/video/captions/build_captions.py --out X.srt
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent  # tools/video/captions -> tools/video -> tools -> repo

SCRIPT_MD = REPO / "docs" / "NARRATION-SCRIPT-v3.md"
INTRO_MANIFEST = REPO / "tools" / "video" / "intro" / "intro-manifest.json"
DEMO_MANIFEST = REPO / "tools" / "video" / "manifest.json"
DEFAULT_OUT = REPO / "docs" / "video" / "CAPTIONS.srt"

WPM = 145.0
LEAD_IN = 0.3          # voice starts this long after its visual
MAX_LINE = 42          # characters per caption line
MAX_LINES = 2
MIN_CUE = 1.2          # seconds; never flash a cue shorter than this
GAP = 0.08             # seconds between consecutive cues
# em dash, en dash, hyphen, and clause punctuation: never left alone at a cue boundary
DANGLERS = {"—", "–", "-", ":", ";", ","}  # noqa: RUF001

# Segment order. Intro segments are keyed by intro-manifest card key; demo segments by
# the beat id the capture tooling uses.
#
# v3 sketch cut: the five static intro cards stay RETIRED — the trimmed landing-page beat
# (b9t) opens the film — so INTRO_SEGMENTS is empty and every segNN maps to a beat.
# Keeping the intro machinery (rather than deleting it) means an intro can be reinstated
# by listing its card keys here again. s1/s2 are rendered sketch beats
# (tools/video/sketch/), not captures, but they are beats like any other here.
INTRO_SEGMENTS: list[str] = []
DEMO_SEGMENTS = ["b9t", "b1", "s1", "b2", "b3", "b4", "s2",
                 "b5", "b6", "b10", "b7", "b11", "b8"]

# docs/DEMO-RUNBOOK.md timing budget — used only until tools/video/manifest.json exists.
FALLBACK_BEATS: dict[str, float] = {
    "b1": 12.0, "b2": 33.0, "b3": 20.0, "b4": 30.0,
    "b5": 25.0, "b6": 25.0, "b7": 15.0, "b8": 10.0,
    "b9": 46.0, "b9t": 44.6, "b10": 32.0, "b11": 18.0,
    "s1": 23.7, "s2": 15.4,
}


@dataclass
class Segment:
    seg_id: str            # "seg01"
    key: str               # "card1" / "b2"
    kind: str              # "intro" / "demo"
    start: float = 0.0
    duration: float = 0.0
    measured: bool = False
    text: str = ""
    words: list[str] = field(default_factory=list)
    lead_in: float = LEAD_IN   # demo beats may carry the capture tooling's own lead

    @property
    def speech_seconds(self) -> float:
        return len(self.words) / WPM * 60.0

    @property
    def headroom(self) -> float:
        return self.duration - self.lead_in - self.speech_seconds


# --------------------------------------------------------------------------- parsing

HEADING_RE = re.compile(r"^#{2,4}\s+(seg\d{2})\s*[·|-]\s*(.+?)\s*$", re.MULTILINE)
FENCE_RE = re.compile(r"^```text\n(.*?)^```", re.MULTILINE | re.DOTALL)


def parse_script(md_path: Path) -> dict[str, str]:
    """Return {seg_id: narration text} from the narration markdown."""
    if not md_path.exists():
        raise SystemExit(f"narration script not found: {md_path}")
    md = md_path.read_text(encoding="utf-8")
    headings = list(HEADING_RE.finditer(md))
    if not headings:
        raise SystemExit(f"no '## segNN · ...' headings found in {md_path}")

    out: dict[str, str] = {}
    for i, h in enumerate(headings):
        end = headings[i + 1].start() if i + 1 < len(headings) else len(md)
        body = md[h.end():end]
        fence = FENCE_RE.search(body)
        if not fence:
            raise SystemExit(f"{h.group(1)}: no ```text block under its heading")
        text = " ".join(fence.group(1).split())
        out[h.group(1)] = text
    return out


def load_timeline() -> tuple[list[Segment], list[str]]:
    """Build the ordered segment list with start offsets. Returns (segments, warnings)."""
    warnings: list[str] = []

    intro_by_key: dict[str, dict] = {}
    if INTRO_SEGMENTS:
        if not INTRO_MANIFEST.exists():
            raise SystemExit(
                f"{INTRO_MANIFEST} missing — run tools/video/intro/render_intro.py first"
            )
        intro = json.loads(INTRO_MANIFEST.read_text(encoding="utf-8"))
        intro_by_key = {s["key"]: s for s in intro["segments"]}

    demo_by_key: dict[str, tuple[float, float | None]] = {}
    demo_lead: float | None = None
    if DEMO_MANIFEST.exists():
        demo = json.loads(DEMO_MANIFEST.read_text(encoding="utf-8"))
        if isinstance(demo, dict) and isinstance(demo.get("voice_lead_s"), (int, float)):
            demo_lead = float(demo["voice_lead_s"])
        demo_by_key = _extract_demo_timeline(demo)
        missing = [b for b in DEMO_SEGMENTS if b not in demo_by_key]
        if missing:
            warnings.append(
                "manifest.json present but has no duration for: "
                + ", ".join(missing)
                + " — using runbook targets for those [SYNC-TO-MANIFEST]"
            )
    else:
        warnings.append(
            "tools/video/manifest.json not found — all demo beats use the "
            "docs/DEMO-RUNBOOK.md target durations [SYNC-TO-MANIFEST]"
        )

    segments: list[Segment] = []
    cursor = 0.0
    n = 0
    for key in INTRO_SEGMENTS:
        n += 1
        dur = float(intro_by_key[key]["measured_seconds"])
        segments.append(Segment(f"seg{n:02d}", key, "intro", cursor, dur, True))
        cursor += dur

    intro_end = cursor
    for key in DEMO_SEGMENTS:
        n += 1
        measured = key in demo_by_key
        dur, rel_start = demo_by_key.get(key, (FALLBACK_BEATS[key], None))
        # The demo assembler crossfades consecutive beats, so beat starts are NOT the
        # running sum of their durations. When the manifest tells us where a beat
        # actually sits on the demo timeline, use that; otherwise fall back to a sum.
        start = intro_end + rel_start if rel_start is not None else cursor
        seg = Segment(f"seg{n:02d}", key, "demo", start, dur, measured)
        if demo_lead is not None:
            seg.lead_in = demo_lead
        segments.append(seg)
        cursor = start + dur
    return segments, warnings


def _extract_demo_timeline(demo: object) -> dict[str, tuple[float, float | None]]:
    """Pull {beat_id: (duration, timeline_start | None)} out of the demo manifest.

    The demo manifest is written by sibling tooling, so this reads defensively: it
    accepts a top-level list, a {"beats": [...]} / {"segments": [...]} wrapper, or a
    plain {beat_id: seconds} / {beat_id: {...}} mapping, and recognises any of the
    common duration and start-offset key spellings.
    """
    dur_keys = ("cut_duration_s", "measured_seconds", "duration_s", "duration",
                "duration_seconds", "seconds", "length")
    start_keys = ("timeline_start_s", "start_seconds", "start_s", "start", "offset_s")
    id_keys = ("id", "beat", "key", "name")

    def _num(entry: dict, keys: tuple[str, ...]) -> float | None:
        for k in keys:
            if isinstance(entry.get(k), (int, float)):
                return float(entry[k])
        return None

    rows: list[dict] = []
    if isinstance(demo, dict):
        for wrapper in ("beats", "segments", "clips"):
            if isinstance(demo.get(wrapper), list):
                rows = [r for r in demo[wrapper] if isinstance(r, dict)]
                break
        else:
            out: dict[str, tuple[float, float | None]] = {}
            for k, v in demo.items():
                if not isinstance(k, str) or not re.fullmatch(r"b\d+", k):
                    continue
                if isinstance(v, (int, float)):
                    out[k] = (float(v), None)
                elif isinstance(v, dict) and (d := _num(v, dur_keys)) is not None:
                    out[k] = (d, _num(v, start_keys))
            return out
    elif isinstance(demo, list):
        rows = [r for r in demo if isinstance(r, dict)]

    out = {}
    for row in rows:
        bid = next((str(row[k]) for k in id_keys if isinstance(row.get(k), str)), None)
        d = _num(row, dur_keys)
        if bid and d is not None:
            out[bid.split(".")[0]] = (d, _num(row, start_keys))
    return out


# --------------------------------------------------------------------------- chunking

def wrap_lines(words: list[str]) -> list[str]:
    """Greedy-wrap words into <= MAX_LINE character lines."""
    lines: list[str] = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip()
        if len(cand) <= MAX_LINE or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def chunk_text(text: str) -> list[str]:
    """Split narration into cues of at most MAX_LINES lines of MAX_LINE chars.

    Prefers to break at sentence ends, so a cue rarely ends mid-thought, and never
    leaves a dangling connector (a lone dash) as the final token of a cue.
    """
    words = text.split()
    cues: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if cur:
            cues.append("\n".join(wrap_lines(cur)))
            cur.clear()

    for w in words:
        cur.append(w)
        lines = wrap_lines(cur)
        if len(lines) > MAX_LINES:
            cur.pop()
            flush()
            cur.append(w)
            continue
        # Break at a sentence end once the cue is reasonably full, so a cue rarely
        # ends mid-thought. Only sentence-final punctuation counts: breaking on a
        # dash or colon strands it as the last glyph on screen.
        if len(lines) == MAX_LINES and w.endswith((".", "?", "!")) and len(w) > 1:
            flush()
    flush()

    # Post-pass: a bare connector must never be the last thing left on screen. Drop it
    # at cue boundaries — an em dash carries no meaning a caption reader needs, and
    # re-flowing it into a neighbouring cue risks pushing that cue to three lines.
    fixed: list[str] = []
    for cue in cues:
        parts = [p for p in cue.split() if p]
        while len(parts) > 1 and parts[-1] in DANGLERS:
            parts.pop()
        while len(parts) > 1 and parts[0] in DANGLERS:
            parts.pop(0)
        if parts and not all(p in DANGLERS for p in parts):
            fixed.append("\n".join(wrap_lines(parts)))
    return fixed


# ----------------------------------------------------------------------------- output

def srt_time(t: float) -> str:
    t = max(0.0, t)
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_cues(segments: list[Segment]) -> list[tuple[float, float, str]]:
    cues: list[tuple[float, float, str]] = []
    for seg in segments:
        if not seg.text:
            continue
        chunks = chunk_text(seg.text)
        if not chunks:
            continue
        # Distribute the estimated speech time across chunks by word share, then clamp
        # the whole run inside the segment so a cue can never bleed into the next beat.
        span = min(seg.speech_seconds, max(0.5, seg.duration - seg.lead_in - 0.15))
        weights = [max(1, len(c.split())) for c in chunks]
        total_w = sum(weights)
        t = seg.start + seg.lead_in
        for chunk, w in zip(chunks, weights, strict=True):
            dur = max(MIN_CUE, span * w / total_w)
            end = min(t + dur, seg.start + seg.duration - 0.05)
            if end <= t:
                end = t + 0.4
            cues.append((t, end, chunk))
            t = end + GAP
    return cues


def write_srt(cues: list[tuple[float, float, str]], out: Path) -> None:
    blocks = [
        f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{txt}\n"
        for i, (a, b, txt) in enumerate(cues, start=1)
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(blocks), encoding="utf-8")


def report(segments: list[Segment], warnings: list[str]) -> int:
    print(f"{'seg':<6}{'src':<8}{'window':>9}{'words':>7}{'speech':>9}{'head':>8}  status")
    print("-" * 72)
    overruns = 0
    for s in segments:
        status = "measured" if s.measured else "SYNC-TO-MANIFEST"
        if s.headroom < 0:
            status += "  ** OVERRUN **"
            overruns += 1
        elif s.headroom < 0.5:
            status += "  (tight)"
        print(
            f"{s.seg_id:<6}{s.key:<8}{s.duration:>8.2f}s{len(s.words):>7}"
            f"{s.speech_seconds:>8.1f}s{s.headroom:>7.1f}s  {status}"
        )
    # Beats overlap by one crossfade, so the film is the last segment's END, not
    # the sum of the segment durations.
    total = max((s.start + s.duration for s in segments), default=0.0)
    print("-" * 72)
    print(f"total video {total:.2f}s  ({int(total // 60)}:{total % 60:04.1f})")
    for w in warnings:
        print(f"warning: {w}")
    if overruns:
        print(f"\n{overruns} segment(s) would overrun their beat — trim the narration.")
    return 1 if overruns else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output .srt path")
    ap.add_argument("--check", action="store_true", help="print the timing report only")
    args = ap.parse_args()

    texts = parse_script(SCRIPT_MD)
    segments, warnings = load_timeline()
    for seg in segments:
        seg.text = texts.get(seg.seg_id, "")
        seg.words = seg.text.split()
        if not seg.text:
            warnings.append(f"{seg.seg_id}: no narration block in {SCRIPT_MD.name}")

    rc = report(segments, warnings)
    if args.check:
        return rc

    cues = build_cues(segments)
    write_srt(cues, args.out)
    print(f"\nwrote {len(cues)} cues -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
