#!/usr/bin/env python
"""Assemble the Whodunit submission video: intro + demo + narration + burned captions.

    docs/video/intro/intro.mp4        (rendered by tools/video/intro/render_intro.py)
  + docs/video/demo-silent.mp4        (assembled from the recorded beats)
  + audio/seg01.wav .. audio/seg13.wav (recorded by a human, per docs/video/NARRATION-SCRIPT.md)
  -> docs/video/whodunit-final.mp4    (1080p H.264 + AAC, captions burned in)

What it does, in order:

1. Normalises intro and demo to a common 1080p/30fps/yuv420p H.264 encode and
   concatenates them (re-encode, not stream copy — the two halves come from different
   pipelines and their encoder settings will not match).
2. Rebuilds ``docs/video/CAPTIONS.srt`` via ``tools/video/captions/build_captions.py``
   so the burned captions can never be stale relative to the narration script.
3. Places each ``segNN.wav`` at its segment's start offset + its lead-in (0.3s, or
   the demo manifest's own ``voice_lead_s`` for demo beats), mixes them into one
   track, and encodes to 48 kHz stereo AAC. Offsets come from the same timeline the
   caption builder uses, so voice and captions cannot drift apart.
4. Burns the captions: white text, semi-transparent black box, fontsize 27,
   bottom-centred.

Usage
-----
    python tools/video/final_assemble.py
    python tools/video/final_assemble.py --no-audio      # captions-burned silent cut
    python tools/video/final_assemble.py --audio-dir take2 --out docs/video/cut2.mp4

``--no-audio`` is the preview mode: it needs no ``.wav`` files at all, so you can check
caption timing and the intro/demo seam before you ever open a microphone.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent  # tools/video -> tools -> repo
sys.path.insert(0, str(HERE / "captions"))

from build_captions import load_timeline, parse_script  # noqa: E402

INTRO = REPO / "docs" / "video" / "intro" / "intro.mp4"
DEMO = REPO / "docs" / "video" / "demo-silent.mp4"
SRT = REPO / "docs" / "video" / "CAPTIONS.srt"
DEFAULT_OUT = REPO / "docs" / "video" / "whodunit-final.mp4"
DEFAULT_AUDIO_DIR = REPO / "audio"
WORK = REPO / "docs" / "video" / ".work"

WIDTH, HEIGHT, FPS = 1920, 1080, 30

# Caption style: white text (PrimaryColour &H00FFFFFF) on a semi-transparent black box
# (BorderStyle=4 + BackColour &H50000000 -> ~69% opaque; ASS alpha is inverted, 00 is
# fully opaque), bottom-centred (Alignment=2)
# with a 112px bottom margin so it clears both the intro cards' footer line and a
# terminal's last line.
#
# The style is applied by rewriting the ASS rather than via `subtitles=force_style`,
# because an SRT converts to an ASS whose PlayRes is 384x288 — libass then scales every
# FontSize by 1080/288 = 3.75x and a "27" renders at ~101px. Patching PlayRes to the
# real frame size makes FontSize mean pixels.
CAPTION_FONT = "Arial"
CAPTION_FONTSIZE = 27
ASS_STYLE = (
    f"Style: Default,{CAPTION_FONT},{CAPTION_FONTSIZE},"
    "&H00FFFFFF,&H000000FF,&H00000000,&H50000000,"  # primary, secondary, outline, back
    "0,0,0,0,"                                      # bold, italic, underline, strikeout
    "100,100,0,0,"                                  # scaleX, scaleY, spacing, angle
    "4,0,0,"                                        # borderstyle(box), outline, shadow
    "2,90,90,112,1"                                 # align, marginL, marginR, marginV, enc
)


def run(cmd: list[str], what: str) -> None:
    print(f"  $ {what}")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-6000:])
        raise SystemExit(f"ffmpeg failed during: {what}")


def probe(path: Path, entry: str = "format=duration") -> str:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", entry,
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip().splitlines()[0]


def escape_for_filter(path: Path) -> str:
    """Escape a Windows path for use inside an ffmpeg filtergraph argument.

    ``C:\\x\\y.srt`` must become ``C\\:/x/y.srt``: forward slashes, and the drive
    colon escaped so the filter parser does not read it as an option separator.
    """
    s = path.resolve().as_posix()
    return s.replace(":", r"\:").replace("'", r"\'").replace("[", r"\[").replace("]", r"\]")


def srt_to_styled_ass(srt: Path, dst: Path) -> Path:
    """Convert the SRT to ASS, pin PlayRes to the frame size, install the caption style."""
    raw = dst.with_suffix(".raw.ass")
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(srt), str(raw)],
        "convert captions to ass")

    out: list[str] = []
    seen_res = {"PlayResX": False, "PlayResY": False}
    in_script_info = False
    for line in raw.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            if in_script_info:
                for k, v in (("PlayResX", WIDTH), ("PlayResY", HEIGHT)):
                    if not seen_res[k]:
                        out.append(f"{k}: {v}")
                        seen_res[k] = True
            in_script_info = stripped.lower() == "[script info]"
        if in_script_info and stripped.startswith(("PlayResX:", "PlayResY:")):
            key = stripped.split(":", 1)[0]
            out.append(f"{key}: {WIDTH if key == 'PlayResX' else HEIGHT}")
            seen_res[key] = True
            continue
        if stripped.startswith("Style:"):
            out.append(ASS_STYLE)
            continue
        out.append(line)
    if in_script_info:
        for k, v in (("PlayResX", WIDTH), ("PlayResY", HEIGHT)):
            if not seen_res[k]:
                out.append(f"{k}: {v}")

    dst.write_text("\n".join(out) + "\n", encoding="utf-8")
    return dst


def normalise(src: Path, dst: Path, label: str) -> None:
    run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
            "-vf",
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"fps={FPS},format=yuv420p,setsar=1",
            "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-video_track_timescale", "30000",
            str(dst),
        ],
        f"normalise {label}",
    )


def build_audio(audio_dir: Path, segments, total: float, dst: Path) -> bool:
    """Mix the per-segment wavs onto one track at their manifest offsets.

    Returns False (and writes nothing) if no wav files are present.
    """
    present = []
    for seg in segments:
        wav = audio_dir / f"{seg.seg_id}.wav"
        if wav.exists():
            present.append((seg, wav))
        else:
            print(f"  ! missing {wav.relative_to(REPO) if wav.is_relative_to(REPO) else wav}"
                  f"  ({seg.seg_id} will be silent)")
    if not present:
        return False

    inputs: list[str] = []
    parts: list[str] = []
    labels: list[str] = []
    for i, (seg, wav) in enumerate(present):
        inputs += ["-i", str(wav)]
        delay_ms = round((seg.start + seg.lead_in) * 1000)
        parts.append(
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}[a{i}]"
        )
        labels.append(f"[a{i}]")
    graph = (
        ";".join(parts)
        + ";"
        + "".join(labels)
        + f"amix=inputs={len(present)}:duration=longest:normalize=0,"
        + f"apad,atrim=0:{total:.3f},asetpts=N/SR/TB[aout]"
    )
    run(
        ["ffmpeg", "-y", "-loglevel", "error", *inputs,
         "-filter_complex", graph, "-map", "[aout]",
         "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(dst)],
        f"mix {len(present)} narration segment(s)",
    )
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR,
                    help="directory holding seg01.wav .. segNN.wav")
    ap.add_argument("--no-audio", action="store_true",
                    help="captions-burned silent preview cut (no wavs needed)")
    ap.add_argument("--intro", type=Path, default=INTRO)
    ap.add_argument("--demo", type=Path, default=DEMO)
    ap.add_argument("--keep-work", action="store_true", help="keep intermediates in .work/")
    args = ap.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} not found on PATH")
    for src, name in ((args.intro, "intro"), (args.demo, "demo")):
        if not src.exists():
            raise SystemExit(
                f"missing {name} video: {src}\n"
                + ("  run tools/video/intro/render_intro.py" if name == "intro"
                   else "  assemble the recorded beats into docs/video/demo-silent.mp4 first")
            )

    WORK.mkdir(parents=True, exist_ok=True)

    # 1. captions, rebuilt from the narration script so they can never go stale
    print("captions")
    subprocess.run(
        [sys.executable, str(HERE / "captions" / "build_captions.py"), "--out", str(SRT)],
        check=True,
    )

    # 2. timeline (same source of truth the captions use)
    texts = parse_script(REPO / "docs" / "video" / "NARRATION-SCRIPT.md")
    segments, _ = load_timeline()
    for seg in segments:
        seg.text = texts.get(seg.seg_id, "")
        seg.words = seg.text.split()

    # 3. normalise + concat video
    print("video")
    n_intro, n_demo = WORK / "intro-n.mp4", WORK / "demo-n.mp4"
    normalise(args.intro, n_intro, "intro")
    normalise(args.demo, n_demo, "demo")
    listfile = WORK / "concat.txt"
    listfile.write_text(
        f"file '{n_intro.as_posix()}'\nfile '{n_demo.as_posix()}'\n", encoding="utf-8"
    )
    silent = WORK / "video-silent.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", str(listfile), "-c", "copy", str(silent)], "concat intro + demo")
    total = float(probe(silent))
    print(f"  concatenated video: {total:.3f}s")

    # 4. audio
    mixed: Path | None = None
    if not args.no_audio:
        print("audio")
        cand = WORK / "narration.wav"
        if build_audio(args.audio_dir, segments, total, cand):
            mixed = cand
        else:
            print(f"  no wavs found in {args.audio_dir} — producing a silent cut")

    # 5. burn captions and mux
    print("final encode")
    ass_path = srt_to_styled_ass(SRT, WORK / "captions.ass")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent)]
    if mixed:
        cmd += ["-i", str(mixed)]
    cmd += [
        "-vf", f"ass='{escape_for_filter(ass_path)}'",
        "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
        "-movflags", "+faststart",
    ]
    if mixed:
        cmd += ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-shortest"]
    else:
        cmd += ["-an"]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cmd.append(str(args.out))
    run(cmd, "burn captions + encode")

    if not args.keep_work:
        shutil.rmtree(WORK, ignore_errors=True)

    dur = float(probe(args.out))
    print(f"\n{args.out}")
    print(f"  {dur:.3f}s  ({int(dur // 60)}:{dur % 60:04.1f})"
          f"  {'with narration' if mixed else 'SILENT (preview)'}")
    if dur > 300:
        print("  ** over the 5:00 submission cap — trim a beat **")
    return 0


if __name__ == "__main__":
    sys.exit(main())
