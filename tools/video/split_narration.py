"""Cut the one-take recording into audio/seg01.wav .. seg13.wav.

For each aligned window: extract with a small pad, trim leading/trailing
near-silence, then check it against its beat window from the video manifest.
If a segment still overruns, apply a gentle atempo (<= 1.08, imperceptible on
speech) rather than clipping words or letting the voice bleed over the cut.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "audio" / "full-take.wav"
ALIGN = REPO / "audio" / "alignment.json"
MANIFEST = REPO / "tools" / "video" / "manifest.json"
OUTDIR = REPO / "audio"

LEAD = 0.30      # assembler places voice this far into the beat
PAD_S = 0.18     # pad before the first detected word
PAD_E = 0.35     # pad after the last detected word
MAX_TEMPO = 1.10


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return (p.stdout or "") + (p.stderr or "")


def dur(path: Path) -> float:
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)]).strip().splitlines()[-1]
    return float(out)


def beat_windows() -> list[float]:
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    beats = m["beats"] if isinstance(m, dict) else m
    return [float(b.get("cut_duration_s") or b.get("duration_s")) for b in beats]


def main() -> int:
    align = json.loads(ALIGN.read_text(encoding="utf-8"))
    windows = beat_windows()
    if len(align) != len(windows):
        print(f"!! {len(align)} audio segments vs {len(windows)} video beats")
        return 1

    print(f"{'seg':>4} {'audio':>7} {'window':>7} {'budget':>7} {'tempo':>6}  status")
    problems = 0
    for a, win in zip(align, windows, strict=True):
        n = a["seg"]
        raw = OUTDIR / f"_raw{n:02d}.wav"
        out = OUTDIR / f"seg{n:02d}.wav"
        start = max(0.0, a["start"] - PAD_S)
        length = (a["end"] + PAD_E) - start

        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}",
             "-i", str(SRC), "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(raw)])
        # trim near-silence at both ends, normalise level
        run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
             "-af", ("silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB:"
                     "detection=peak,areverse,"
                     "silenceremove=start_periods=1:start_silence=0.05:start_threshold=-40dB:"
                     "detection=peak,areverse,loudnorm=I=-17:TP=-1.5:LRA=11"),
             "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(out)])

        budget = win - LEAD
        d = dur(out)
        tempo = 1.0
        if d > budget:
            tempo = min(MAX_TEMPO, d / budget)
            tmp = OUTDIR / f"_t{n:02d}.wav"
            run(["ffmpeg", "-y", "-v", "error", "-i", str(out), "-af", f"atempo={tempo:.4f}",
                 "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(tmp)])
            tmp.replace(out)
            d = dur(out)

        raw.unlink(missing_ok=True)
        ok = d <= budget + 0.05
        if not ok:
            problems += 1
        print(f"{n:>4} {d:>6.2f}s {win:>6.2f}s {budget:>6.2f}s {tempo:>6.3f}  "
              f"{'ok' if ok else 'STILL OVER'}")

    print(f"\nwrote seg01..seg{len(align):02d}.wav   over-budget: {problems}")
    return 0 if problems == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
