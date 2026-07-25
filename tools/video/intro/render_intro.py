#!/usr/bin/env python
"""Render the Whodunit intro segment: HTML cards -> PNG -> MP4 -> docs/video/intro/intro.mp4.

Self-contained: the cards live in ``cards/`` and reference no external assets, fonts,
or CDNs. Chromium (via Playwright) screenshots each card at 2x device scale, then
ffmpeg turns each PNG into a fixed-length 1080p segment with a fade in and out, and
concatenates the segments.

Durations are declared in CARDS below but the manifest records the *measured*
duration of every rendered segment (ffprobe), so the narration script and the caption
builder are always synced to real footage rather than intent.

Usage
-----
    <playwright-python> tools/video/intro/render_intro.py            # full render
    <playwright-python> tools/video/intro/render_intro.py --png-only # cards only

On this machine the interpreter carrying playwright + chromium is:
    C:/Users/abhis/Desktop/OSS/Signoz/warmup-agent/.venv/Scripts/python.exe
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent  # tools/video/intro -> tools/video -> tools -> repo
CARDS_DIR = HERE / "cards"
OUT_DIR = REPO / "docs" / "video" / "intro"
PNG_DIR = OUT_DIR / "cards"
SEG_DIR = OUT_DIR / "segments"
MANIFEST = HERE / "intro-manifest.json"

WIDTH, HEIGHT, FPS = 1920, 1080, 30
SCALE = 2  # screenshot at 3840x2160; downscaled to 1080p with lanczos for crisp text


@dataclass(frozen=True)
class Card:
    key: str
    html: str
    seconds: float
    zoom: str  # "in" or "out"
    label: str


# Total declared: 10 + 15 + 16 + 16 + 12 = 69s.
CARDS: tuple[Card, ...] = (
    Card("card1", "card1-title.html", 10.0, "in", "Title / tagline"),
    Card("card2", "card2-problem.html", 15.0, "out", "ABOUT — the problem"),
    Card("card3", "card3-pipeline.html", 16.0, "in", "ABOUT + TECH STACK — what it does"),
    Card("card4", "card4-signoz.html", 16.0, "out", "HOW IT USES SIGNOZ — five surfaces"),
    Card("card5", "card5-numbers.html", 12.0, "in", "The honest numbers"),
)

FADE = 0.6  # seconds of fade in and fade out on every segment


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-4000:])
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd[:3])} ...")


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    return round(float(out.stdout.strip()), 3)


def shoot_cards() -> None:
    from playwright.sync_api import sync_playwright

    PNG_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(
            viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=SCALE
        )
        for card in CARDS:
            src = CARDS_DIR / card.html
            if not src.exists():
                raise SystemExit(f"missing card html: {src}")
            page.goto(src.as_uri())
            page.wait_for_timeout(250)
            page.screenshot(path=str(PNG_DIR / f"{card.key}.png"))
            print(f"  png  {card.key}.png")
        browser.close()


def card_filter(card: Card) -> str:
    """Static 1080p card with a fade in and a fade out.

    The cards are dense, text-heavy reference frames — a static hold reads better
    than motion, and (measured on this machine) ffmpeg's ``zoompan`` costs ~1s of
    wall-clock per output frame on a 4K still, which makes a Ken Burns push a
    45-minute render for a 69-second segment. Static + fade renders in seconds and
    keeps every glyph crisp. ``card.zoom`` is retained for a future motion pass.
    """
    fade_out_at = max(0.0, card.seconds - FADE)
    return (
        f"scale={WIDTH}:{HEIGHT}:flags=lanczos,"
        f"fade=t=in:st=0:d={FADE},fade=t=out:st={fade_out_at}:d={FADE},"
        f"format=yuv420p"
    )


def build_segments() -> list[dict]:
    SEG_DIR.mkdir(parents=True, exist_ok=True)
    segments: list[dict] = []
    cursor = 0.0
    for card in CARDS:
        png = PNG_DIR / f"{card.key}.png"
        seg = SEG_DIR / f"{card.key}.mp4"
        _run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", str(FPS), "-t", f"{card.seconds}", "-i", str(png),
            "-vf", card_filter(card),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            str(seg),
        ])
        measured = probe_duration(seg)
        segments.append({
            "key": card.key,
            "label": card.label,
            "html": f"tools/video/intro/cards/{card.html}",
            "png": f"docs/video/intro/cards/{card.key}.png",
            "segment": f"docs/video/intro/segments/{card.key}.mp4",
            "declared_seconds": card.seconds,
            "measured_seconds": measured,
            "start_seconds": round(cursor, 3),
            "end_seconds": round(cursor + measured, 3),
        })
        cursor += measured
        print(f"  mp4  {card.key}.mp4  {measured:.3f}s")
    return segments


def concat(segments: list[dict]) -> Path:
    listfile = SEG_DIR / "concat.txt"
    listfile.write_text(
        "".join(f"file '{(REPO / s['segment']).as_posix()}'\n" for s in segments),
        encoding="utf-8",
    )
    out = OUT_DIR / "intro.mp4"
    _run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-c", "copy", str(out),
    ])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--png-only", action="store_true", help="render the PNG cards and stop")
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise SystemExit("ffmpeg/ffprobe not found on PATH")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("rendering cards ->", PNG_DIR)
    shoot_cards()
    if args.png_only:
        return 0

    print("building segments ->", SEG_DIR)
    segments = build_segments()
    intro = concat(segments)
    total = probe_duration(intro)

    MANIFEST.write_text(
        json.dumps(
            {
                "generated_by": "tools/video/intro/render_intro.py",
                "video": "docs/video/intro/intro.mp4",
                "width": WIDTH,
                "height": HEIGHT,
                "fps": FPS,
                "fade_seconds": FADE,
                "total_measured_seconds": total,
                "segments": segments,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nintro.mp4  {total:.3f}s  ->  {intro}")
    print(f"manifest   {MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
