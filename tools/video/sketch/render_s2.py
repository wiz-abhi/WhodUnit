"""S2 — "one store, not three": why the join only exists on SigNoz.

Three disconnected drums on the left (Tempo / Loki / Prometheus) with the joins
between them struck out; one drum on the right holding all three signals, with a
`JOIN ON trace_id` arrow that can only be drawn because they share a store.

    uv run --with matplotlib python tools/video/sketch/render_s2.py

Writes ``docs/video/raw/s2.mp4`` (1920x1080 @ 30fps, ~15.4s).
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from _style import (
    GREEN,
    GREY,
    INK,
    RAW,
    RED,
    arrow,
    cross,
    cylinder,
    divider,
    fade,
    fade_dim,
    label,
    render_sequence,
)

DURATION = 15.40

# ------------------------------------------------------------------ layout (px)
# Nothing below y=230 — the burned narration captions own that band.
LX = 470                 # left column centre
LW, LH, LEH = 420, 115, 48
L1, L2, L3 = 830, 625, 420   # cylinder floors, top to bottom

RX = 1440                # right column centre
RW, RH, REH = 620, 320, 76
R1 = 470

DIM_AT = 12.30           # the left column steps back once the answer is on screen


# ------------------------------------------------------------------ timeline (s)
def state(t: float) -> dict[str, float]:
    def left(t_in: float, dur: float = 0.45) -> float:
        return fade_dim(t, t_in, t_dim=DIM_AT, dim_to=0.45, dur=dur, dim_dur=0.7)

    return {
        "title": fade(t, 0.00, 0.35),
        "divider": fade(t, 0.30, 0.60),
        "h_three": left(0.45),
        "cyl1": left(0.60),
        "cyl2": left(0.95),
        "cyl3": left(1.30),
        "gaps": left(2.30),
        "crosses": left(2.70),
        "nojoin": left(3.05),
        "h_one": fade(t, 5.30),
        "drum": fade(t, 5.50),
        "contents": fade(t, 6.05),
        "join": fade(t, 6.65),
        "onescan": fade(t, 7.25),
        "cap_final": fade(t, 9.60, 0.55),
    }


# ------------------------------------------------------------------ frame
def draw(ax, s) -> None:
    label(ax, 58, 1040, "one store, not three", GREY, s["title"], size=21, ha="left")
    divider(ax, 960, 300, 992, s["divider"])

    # ---- three stores, no join -------------------------------------------
    label(ax, LX, 1000, "three stores", GREY, s["h_three"], size=23)
    for ybot, key, name, sig in (
        (L1, "cyl1", "Tempo", "traces"),
        (L2, "cyl2", "Loki", "logs"),
        (L3, "cyl3", "Prometheus", "metrics"),
    ):
        a = s[key]
        cylinder(ax, LX, ybot, LW, LH, GREY, a, eh=LEH)
        label(ax, LX, ybot + 76, name, INK, a, size=22)
        label(ax, LX, ybot + 36, sig, GREY, a, size=17)

    for y0, y1, ymid in ((L1 - 4, L1 - 80, L1 - 42), (L2 - 4, L2 - 80, L2 - 42)):
        arrow(ax, (LX, y0), (LX, y1), GREY, s["gaps"], ls=(0, (5, 4)), lw=2.2)
        cross(ax, LX, ymid, 18, RED, s["crosses"])
    label(ax, LX, 348, "no join", RED, s["nojoin"], size=21)

    # ---- one store, one scan ---------------------------------------------
    label(ax, RX, 1000, "one store", GREEN, s["h_one"], size=23)
    cylinder(ax, RX, R1, RW, RH, GREEN, s["drum"], eh=REH)
    label(ax, RX, R1 + 258, "SigNoz · ClickHouse", INK, s["drum"], size=23)
    label(ax, RX, R1 + 198, "traces + logs + metrics", GREY, s["contents"], size=18)
    arrow(ax, (RX - 190, R1 + 118), (RX + 190, R1 + 118), GREEN, s["join"],
          rad=-0.32, lw=2.8, scale=20)
    label(ax, RX, R1 + 58, "JOIN ON trace_id", GREEN, s["join"], size=18)
    label(ax, RX, 348, "one scan", GREEN, s["onescan"], size=21)

    # ---- the line -------------------------------------------------------
    label(ax, 960, 258,
          "one clickhouse_sql scan joins traces ⋈ logs  —  impossible on three stores",
          GREEN, s["cap_final"], size=22)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=RAW / "s2.mp4")
    ap.add_argument("--frames", type=Path,
                    default=Path(tempfile.gettempdir()) / "whodunit-s2-frames")
    a = ap.parse_args()
    print(f"s2 'one store, not three' — {DURATION}s")
    render_sequence(state, draw, DURATION, a.out, a.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
