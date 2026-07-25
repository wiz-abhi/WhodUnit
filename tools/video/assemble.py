"""Cut the raw beat captures down to the timeline and stitch them together.

Reads ``tools/video/manifest.json`` (produced by ``make_manifest.py``), which
carries, per beat, the source file and the list of segments to keep. A beat's
segments are hard-cut together (beat 2's take is a real ~7-minute mine, so the
dead wait between "command entered" and "board rendered" is cut out); the beats
themselves are joined with 0.3 s crossfades.

    uv run python tools/video/assemble.py

Writes ``docs/video/demo-silent.mp4`` and prints the measured total, which must
come in at or under 2:50.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "tools" / "video" / "manifest.json"
OUT = REPO / "docs" / "video" / "demo-silent.mp4"
CAP_S = 170.0  # 2:50
XFADE = 0.3
FPS = 30


def probe(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def cut(src: Path, start: float, end: float, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src),
         "-vf", f"scale=1920:1080:flags=lanczos,fps={FPS},setsar=1",
         "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", str(dst)],
        check=True,
    )


def concat(parts: list[Path], dst: Path, tmp: Path) -> None:
    if len(parts) == 1:
        parts[0].replace(dst)
        return
    lst = tmp / f"{dst.stem}.txt"
    lst.write_text(
        "\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8"
    )
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dst)],
        check=True,
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()

    man = json.loads(a.manifest.read_text(encoding="utf-8"))
    beats = man["beats"]
    tmp = Path(tempfile.mkdtemp(prefix="whodunit-asm-"))

    clips: list[Path] = []
    print(f"{'beat':6} {'source':>9} {'kept':>8}   segments")
    for b in beats:
        parts = []
        for i, seg in enumerate(b["segments"]):
            src = REPO / seg.get("source", b["file"])
            if not src.exists():
                raise SystemExit(f"missing capture: {src}")
            dst = tmp / f"{b['id']}_{i}.mp4"
            cut(src, float(seg["start"]), float(seg["end"]), dst)
            parts.append(dst)
        clip = tmp / f"{b['id']}.mp4"
        concat(parts, clip, tmp)
        d = probe(clip)
        b["cut_duration_s"] = round(d, 2)
        clips.append(clip)
        segs = ", ".join(f"{s['start']:.1f}-{s['end']:.1f}" for s in b["segments"])
        print(f"{b['id']:6} {b['source_duration_s']:>8.1f}s {d:>7.2f}s   {segs}")

    # xfade chain
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    durs = [probe(c) for c in clips]
    filt, prev, offset = [], "0:v", 0.0
    for i in range(1, len(clips)):
        offset += durs[i - 1] - XFADE if i > 1 else durs[0] - XFADE
        label = f"v{i}"
        filt.append(
            f"[{prev}][{i}:v]xfade=transition=fade:duration={XFADE}:"
            f"offset={offset:.3f}[{label}]"
        )
        prev = label
    a.out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs]
    if filt:
        cmd += ["-filter_complex", ";".join(filt), "-map", f"[{prev}]"]
    cmd += ["-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(FPS), str(a.out)]
    subprocess.run(cmd, check=True)

    total = probe(a.out)
    naive = sum(durs) - XFADE * (len(durs) - 1)
    print(f"\n-> {a.out}")
    print(f"   measured total {total:.2f}s  ({int(total // 60)}:{total % 60:05.2f})"
          f"   [expected {naive:.2f}s]")
    if total > CAP_S:
        over = total - CAP_S
        print(f"   OVER the 2:50 cap by {over:.2f}s - trim the manifest segments")
        return 1
    print(f"   under the 2:50 cap by {CAP_S - total:.2f}s")

    # persist the measured cut durations back into the manifest
    man["assembled"] = {
        "file": (
            str(a.out.relative_to(REPO)).replace("\\", "/")
            if a.out.is_relative_to(REPO) else str(a.out)
        ),
        "measured_total_s": round(total, 2),
        "crossfade_s": XFADE,
        "cap_s": CAP_S,
    }
    a.manifest.write_text(json.dumps(man, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
