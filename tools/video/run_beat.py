"""Run a terminal beat for real and record exactly what it printed.

This is the capture half of the offscreen terminal pipeline: it executes the
beat's commands against the LIVE stack with colour forced on and a fixed
terminal width, and stores, per step, the raw ANSI bytes the program wrote plus
the measured wall-clock time. `record_termcast.py` renders that recording into
a video without ever touching the desktop — the machine stays usable while the
footage is produced, and no window of the operator's can wander into frame.

Nothing here re-implements or re-formats program output: the stored bytes are
the bytes `whodunit` wrote to its stdout.

    uv run python tools/video/run_beat.py b2
    uv run python tools/video/run_beat.py b2 b3 b4 b8

Writes docs/video/raw/casts/<beat>.json.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CASTS = REPO / "docs" / "video" / "raw" / "casts"
BEATS = REPO / "tools" / "video" / "beats.json"
COLUMNS = 150


def run_step(step: dict) -> dict:
    cmd = step["cmd"]
    if step.get("type_only"):
        return {"cmd": cmd, "ansi": "", "elapsed_s": 0.0, "typed_only": True,
                "note": step.get("note", "")}
    env = dict(os.environ)
    env.update({
        "FORCE_COLOR": "1",
        "COLUMNS": str(COLUMNS),
        "LINES": "40",
        "PYTHONIOENCODING": "utf-8",
        "TERM": "xterm-256color",
        # rich falls back to the legacy-console renderer (ASCII box drawing, no
        # truecolor) unless it believes it is inside Windows Terminal. These two
        # only change how rich EMITS its own output; they change nothing about
        # what the pipeline computes.
        "WT_SESSION": "whodunit-video",
        "TERM_PROGRAM": "WindowsTerminal",
        "WHODUNIT_CAPTURE": "1",  # see tools/video/_console.py
    })
    env.update(step.get("env") or {})
    t0 = time.time()
    proc = subprocess.run(
        cmd, shell=True, cwd=REPO, env=env, capture_output=True,
        timeout=step.get("timeout", 2400),
    )
    elapsed = time.time() - t0
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        print(f"  !! exit {proc.returncode}\n{err[-2000:]}", file=sys.stderr)

    # `display_cmd` re-renders the SAME result object the timed command just
    # produced (a `--replay` of its cache), purely so the frames carry rich's
    # colour output. The command shown on screen, the elapsed time and every
    # number stay those of the real timed run; only the bytes' colour changes.
    disp = step.get("display_cmd")
    if disp and proc.returncode == 0:
        p2 = subprocess.run(disp, shell=True, cwd=REPO, env=env,
                            capture_output=True, timeout=300)
        if p2.returncode == 0:
            out = p2.stdout.decode("utf-8", "replace")

    return {
        "cmd": cmd,
        "ansi": out + (err if proc.returncode != 0 else ""),
        "elapsed_s": round(elapsed, 2),
        "returncode": proc.returncode,
        "note": step.get("note", ""),
        "spinner": step.get("spinner"),
        "hold": step.get("hold", 5.0),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("beats", nargs="+")
    ap.add_argument(
        "--recolor-only",
        action="store_true",
        help=(
            "Do not re-run the timed command; only refresh each step's stored "
            "bytes by re-running its display_cmd. Use after a beat was captured "
            "without colour - the numbers and the elapsed time are kept."
        ),
    )
    a = ap.parse_args()
    spec = json.loads(BEATS.read_text(encoding="utf-8"))["beats"]
    CASTS.mkdir(parents=True, exist_ok=True)
    rc = 0
    if a.recolor_only:
        for bid in a.beats:
            path = CASTS / f"{bid}.json"
            cast = json.loads(path.read_text(encoding="utf-8"))
            for step, orig in zip(cast["steps"], spec[bid]["steps"], strict=False):
                disp = orig.get("display_cmd")
                if not disp:
                    continue
                step["ansi"] = run_step({"cmd": disp, "hold": step.get("hold", 5)})["ansi"]
                print(f"  recoloured {bid}: {len(step['ansi'])} bytes", flush=True)
            path.write_text(json.dumps(cast, indent=2), encoding="utf-8")
        return 0
    for bid in a.beats:
        b = spec[bid]
        print(f"=== {bid}: {b['title']}", flush=True)
        steps = []
        for st in b["steps"]:
            print(f"  $ {st['cmd']}", flush=True)
            r = run_step(st)
            print(f"    -> {r['elapsed_s']}s, {len(r['ansi'])} bytes", flush=True)
            if r.get("returncode"):
                rc = 1
            steps.append(r)
        (CASTS / f"{bid}.json").write_text(
            json.dumps({"id": bid, "title": b["title"], "columns": COLUMNS,
                        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "steps": steps}, indent=2),
            encoding="utf-8",
        )
        print(f"  -> {CASTS / f'{bid}.json'}", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
