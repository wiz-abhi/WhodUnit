"""Build ``tools/video/manifest.json`` — the MEASURED timeline for the demo cut.

Inputs
  * ``tools/video/trims.json``          the editable spec: per beat, which
                                        segments of the raw capture to keep and
                                        what the narrator is talking about;
  * ``docs/video/raw/*.mp4``            the raw captures (ffprobe'd for the real
                                        source duration);
  * ``docs/video/raw/explain-result.json``  the cached LIVE run — every number
                                        quoted in the manifest is read out of
                                        this, never typed by hand.

Output: ``tools/video/manifest.json`` with, per beat, the file, the measured
source duration, the kept segments and their summed length, the real on-screen
numbers, and a narration window (voice starts 0.3 s after the beat's visual, so
a crossfade never lands on the first syllable).

    uv run python tools/video/make_manifest.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "docs" / "video" / "raw"
TRIMS = REPO / "tools" / "video" / "trims.json"
OUT = REPO / "tools" / "video" / "manifest.json"
XFADE = 0.3
VOICE_LEAD = 0.3


def probe(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def real_numbers() -> dict:
    """The on-screen numbers, read straight out of the cached live run."""
    p = RAW / "explain-result.json"
    if not p.exists():
        return {}
    r = json.loads(p.read_text(encoding="utf-8"))
    v = r.get("verification") or {}
    c = r.get("cost") or {}
    ch = r.get("chosen_finding") or {}
    comp = r.get("compiled") or {}
    leaves = {leaf["name"]: leaf["filters"]["expression"] for leaf in comp.get("leaf_queries", [])}
    return {
        "verdict": r.get("verdict"),
        "expression": comp.get("expression"),
        "return_spans_from": comp.get("return_spans_from"),
        "leaves": leaves,
        "family_size": c.get("family_size"),
        "n_features": c.get("n_features"),
        "n_survivors": len(r.get("mine_result_findings") or []),
        "n_near_misses": len(r.get("near_misses") or []),
        "winner_lift": ch.get("lift"),
        "winner_ci": [ch.get("ci_low"), ch.get("ci_high")],
        "support_bad": ch.get("support_bad"),
        "support_healthy": ch.get("support_healthy"),
        "mined": v.get("mined_count"),
        "signoz": v.get("signoz_count"),
        "match": v.get("match"),
        "precision": v.get("precision"),
        "recall": v.get("recall"),
        "scan_rows_scanned": c.get("scan_rows_scanned"),
        "verify_rows_scanned": v.get("rows_scanned"),
        "verdict_hash": r.get("verdict_hash"),
        "verdict_hash_prefix": (r.get("verdict_hash") or "")[:8],
    }


def main() -> int:
    spec = json.loads(TRIMS.read_text(encoding="utf-8"))
    nums = real_numbers()
    beats, t = [], 0.0
    for b in spec["beats"]:
        default_src = b["source"]
        segs = []
        for s in b["segments"]:
            # ["start", "end"] or ["start", "end", "other-source.mp4"]
            name = s[2] if len(s) > 2 else default_src
            segs.append({
                "source": f"docs/video/raw/{name}",
                "start": float(s[0]),
                "end": float(s[1]),
                "seconds": round(float(s[1]) - float(s[0]), 2),
            })
        sources = sorted({s["source"] for s in segs})
        source_duration = round(
            sum(probe(REPO / p) for p in sources if (REPO / p).exists()), 2
        )
        kept = round(sum(s["seconds"] for s in segs), 2)
        start = round(t, 2)
        end = round(t + kept, 2)
        beats.append({
            "id": b["id"],
            "title": b["title"],
            "file": f"docs/video/raw/{b['source']}",
            "sources": sources,
            "source_duration_s": source_duration,
            "segments": segs,
            "cut_duration_s": kept,
            "timeline_start_s": start,
            "timeline_end_s": end,
            "on_screen": {k: nums.get(k) for k in b.get("on_screen", [])},
            "narration": {
                "window_start_s": round(start + VOICE_LEAD, 2),
                "window_end_s": end,
                "seconds_available": round(kept - VOICE_LEAD, 2),
                "beat": b["narration"],
            },
            "notes": b.get("notes", ""),
        })
        t = end - XFADE  # the next beat overlaps by one crossfade

    total = round(beats[-1]["timeline_end_s"] - XFADE * (len(beats) - 1), 2)
    doc = {
        "generated_by": "tools/video/make_manifest.py",
        "corpus": spec.get("corpus"),
        "stack": spec.get("stack"),
        "crossfade_s": XFADE,
        "voice_lead_s": VOICE_LEAD,
        "cap_s": 170.0,
        "predicted_total_s": total,
        "real_numbers": nums,
        "beats": beats,
    }
    OUT.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    print(f"-> {OUT}")
    for b in beats:
        print(f"  {b['id']:4} {b['cut_duration_s']:6.2f}s  "
              f"[{b['timeline_start_s']:6.2f} -> {b['timeline_end_s']:6.2f}]  {b['title']}")
    print(f"  {'TOTAL':4} {total:6.2f}s  ({int(total // 60)}:{total % 60:05.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
