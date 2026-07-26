"""Align a single-take narration recording to the 13 script segments.

Global alignment: the whole script (tokenised, with each token tagged by its
segment) is aligned against the whole Whisper transcript with SequenceMatcher.
Matching blocks give a script-index -> transcript-index map; each segment's
[start, end) is then the timestamp span of its own mapped tokens.

This beats a greedy per-segment scan, where one over-long window cascades into
every later segment.
"""
from __future__ import annotations

import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "docs" / "NARRATION-SCRIPT-v3.md"
TRANSCRIPT = REPO / "audio" / "transcript.json"
OUT = REPO / "audio" / "alignment.json"

WORD = re.compile(r"[a-z0-9]+")

# ASR reliably mangles these proper nouns; fold them so they still match.
FOLD = {
    "houdhanit": "whodunit", "hoodunit": "whodunit", "hudunit": "whodunit",
    "whodhanit": "whodunit", "whodunnit": "whodunit",
    "signals": "signoz", "signos": "signoz", "signose": "signoz",
    "babalap": "bubbleup", "bubblap": "bubbleup", "bubble": "bubbleup",
    "clickhouse": "clickhouse", "click": "clickhouse",
}


def toks(text: str) -> list[str]:
    return [FOLD.get(t, t) for t in WORD.findall(text.lower())]


def script_segments() -> list[str]:
    md = SCRIPT.read_text(encoding="utf-8")
    return [b.strip() for b in re.findall(r"```text\n(.*?)```", md, re.S)]


def transcript_words() -> list[dict]:
    words: list[dict] = []
    for seg in json.loads(TRANSCRIPT.read_text(encoding="utf-8")):
        for w in seg.get("words") or []:
            for t in toks(w["w"]):
                words.append({"w": t, "s": w["s"], "e": w["e"]})
    return words


def main() -> int:
    segs = script_segments()
    if len(segs) != 13:
        print(f"!! expected 13 script segments, parsed {len(segs)}")
        return 1
    words = transcript_words()

    # flat script tokens, each tagged with its 1-based segment number
    s_toks: list[str] = []
    s_seg: list[int] = []
    for i, raw in enumerate(segs, 1):
        for t in toks(raw):
            s_toks.append(t)
            s_seg.append(i)

    t_toks = [w["w"] for w in words]
    print(f"script tokens: {len(s_toks)}   transcript tokens: {len(t_toks)}")

    sm = SequenceMatcher(None, s_toks, t_toks, autojunk=False)
    ratio = sm.ratio()
    print(f"global match ratio: {ratio:.3f}\n")

    # script index -> transcript index, for matching blocks only
    m: dict[int, int] = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            m[a + k] = b + k

    results = []
    prev_end = 0.0
    for seg_no in range(1, 14):
        idxs = [m[i] for i in range(len(s_toks)) if s_seg[i] == seg_no and i in m]
        n_tok = sum(1 for x in s_seg if x == seg_no)
        if not idxs:
            print(f"seg{seg_no:02d}  !! no tokens aligned")
            return 1
        lo, hi = min(idxs), max(idxs)
        start, end = words[lo]["s"], words[hi]["e"]
        cov = len(idxs) / n_tok
        results.append({
            "seg": seg_no, "start": round(start, 2), "end": round(end, 2),
            "dur": round(end - start, 2), "coverage": round(cov, 3),
            "tokens": n_tok, "text": segs[seg_no - 1].replace("\n", " ")[:52],
        })
        gap = start - prev_end
        prev_end = end
        warn = "  <-- LOW COVERAGE" if cov < 0.7 else ""
        print(f"seg{seg_no:02d}  {start:7.2f} -> {end:7.2f}  ({end - start:5.2f}s)"
              f"  gap_before={gap:5.2f}s  cov={cov:.2f}{warn}")

    # sanity: strictly increasing, non-overlapping
    bad = [r for i, r in enumerate(results[1:], 1) if r["start"] < results[i - 1]["end"]]
    OUT.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(REPO)}")
    print(f"overlaps: {len(bad)}   low-coverage: {sum(1 for r in results if r['coverage'] < 0.7)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
