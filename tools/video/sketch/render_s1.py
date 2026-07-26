"""S1 — "the fault, drawn": an animated hand-drawn explainer of the conjunction.

Two trace trees side by side. The healthy one draws in, then the failing one,
then the two *individually useless* signals get circled on **both** sides, and
only at the end does the pair get boxed on the failing side alone. That is the
whole thesis of the project in one picture: neither condition separates the
cohorts, the conjunction does.

Every number on screen is the seed-778 run: lift 13.1x, support_bad 61,
support_healthy 0 (``docs/video/raw/explain-result.json``).

    uv run --with matplotlib python tools/video/sketch/render_s1.py

Writes ``docs/video/raw/s1.mp4`` (1920x1080 @ 30fps, ~23.7s).
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from _style import (
    AMBER,
    BLUE,
    GREEN,
    GREY,
    RAW,
    box_mark,
    card,
    cross,
    divider,
    elbow,
    fade,
    fade_dim,
    label,
    render_sequence,
    ring,
)

DURATION = 23.70

# ------------------------------------------------------------------ layout (px)
# Nothing is drawn below y=230: final_assemble.py burns the narration captions
# bottom-centred with a 112 px margin, so the bottom band of the frame belongs
# to them.
#
# left column                                right column
L_CHECKOUT = (170, 841, 300, 58)
L_PAYMENT = (240, 741, 280, 58)
L_REDIS = (310, 641, 260, 58)
L_FLAG = (240, 531, 300, 58)

R_CHECKOUT = (1055, 841, 300, 58)
R_PAYMENT = (1125, 741, 280, 58)
R_REDIS = (1195, 641, 280, 58)
R_GHOST = (1125, 531, 300, 58)

# the two "circle it" marks
L_RING_RETRY = (416, 670, 380, 104)
R_RING_RETRY = (1311, 670, 400, 104)
L_RING_FLAG = (390, 560, 350, 100)
R_RING_FLAG = (1275, 560, 350, 100)

# the final "both at once" box, on the failing side only
R_BOTH = (1085, 460, 452, 270)


# ------------------------------------------------------------------ timeline (s)
def state(t: float) -> dict[str, float]:
    return {
        "title": fade(t, 0.00, 0.35),
        "divider": fade(t, 0.30, 0.60),
        "h_healthy": fade(t, 0.45),
        "l_checkout": fade(t, 0.70),
        "l_payment": fade(t, 1.05),
        "l_redis": fade(t, 1.40),
        "l_flag": fade(t, 1.80),
        "h_failing": fade(t, 4.20),
        "r_checkout": fade(t, 4.45),
        "r_payment": fade(t, 4.80),
        "r_redis": fade(t, 5.15),
        "r_ghost": fade(t, 5.60),
        "r_ghost_x": fade(t, 5.95),
        "r_ghost_label": fade(t, 6.20),
        "ring_retry": fade_dim(t, 8.60, t_dim=13.10, dim_to=0.42),
        "cap_retry": fade_dim(t, 8.90, t_dim=13.40, dim_to=0.45),
        "ring_flag": fade_dim(t, 13.10, t_dim=17.60, dim_to=0.42),
        "cap_flag": fade_dim(t, 13.40, t_dim=17.95, dim_to=0.45),
        "both": fade(t, 17.60, 0.55),
        "cap_final": fade(t, 17.95, 0.55),
    }


# ------------------------------------------------------------------ frame
def draw(ax, s) -> None:
    label(ax, 58, 1040, "the fault, drawn", GREY, s["title"], size=21, ha="left")
    divider(ax, 812, 425, 992, s["divider"])

    # ---- healthy ---------------------------------------------------------
    label(ax, 320, 962, "healthy", GREEN, s["h_healthy"], size=23)
    card(ax, L_CHECKOUT, "checkout", GREEN, s["l_checkout"])
    elbow(ax, L_CHECKOUT, L_PAYMENT, GREY, min(s["l_checkout"], s["l_payment"]))
    card(ax, L_PAYMENT, "payment", GREEN, s["l_payment"])
    elbow(ax, L_PAYMENT, L_REDIS, GREY, min(s["l_payment"], s["l_redis"]))
    card(ax, L_REDIS, "redis", GREEN, s["l_redis"])
    elbow(ax, L_CHECKOUT, L_FLAG, GREY, min(s["l_checkout"], s["l_flag"]))
    card(ax, L_FLAG, "flag-service", GREEN, s["l_flag"])

    # ---- failing ---------------------------------------------------------
    label(ax, 1205, 962, "failing", AMBER, s["h_failing"], size=23)
    card(ax, R_CHECKOUT, "checkout", GREY, s["r_checkout"])
    elbow(ax, R_CHECKOUT, R_PAYMENT, GREY, min(s["r_checkout"], s["r_payment"]))
    card(ax, R_PAYMENT, "payment", GREY, s["r_payment"])
    # the retry edge is the thing that is different — amber, both edge and node
    elbow(ax, R_PAYMENT, R_REDIS, AMBER, min(s["r_payment"], s["r_redis"]), lw=3.0)
    card(ax, R_REDIS, "redis-retry", AMBER, s["r_redis"])
    elbow(ax, R_CHECKOUT, R_GHOST, GREY, min(s["r_checkout"], s["r_ghost"]) * 0.5)
    card(ax, R_GHOST, "flag-service", GREY, s["r_ghost"] * 0.55, dashed=True)
    gx, gy, gw, gh = R_GHOST
    cross(ax, gx + gw - 40, gy + gh / 2, 15, GREY, s["r_ghost_x"])
    label(ax, gx + gw / 2, 488, "flag-service missing", GREY,
          s["r_ghost_label"], size=17, style="italic")

    # ---- reveal 1: the retry alone ---------------------------------------
    ring(ax, *L_RING_RETRY, AMBER, s["ring_retry"])
    ring(ax, *R_RING_RETRY, AMBER, s["ring_retry"])
    label(ax, 960, 396, "the retry alone?  also in healthy traces.", AMBER,
          s["cap_retry"], size=21)

    # ---- reveal 2: the missing flag alone --------------------------------
    ring(ax, *L_RING_FLAG, BLUE, s["ring_flag"], ls=(0, (7, 5)))
    ring(ax, *R_RING_FLAG, BLUE, s["ring_flag"], ls=(0, (7, 5)))
    label(ax, 960, 328, "no flag-service alone?  also in healthy traces.", BLUE,
          s["cap_flag"], size=21)

    # ---- the conjunction -------------------------------------------------
    box_mark(ax, R_BOTH, GREEN, s["both"], lw=3.4)
    label(ax, 960, 252, "only both at once  —  13.1x lift,  61 bad / 0 healthy",
          GREEN, s["cap_final"], size=25)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=RAW / "s1.mp4")
    ap.add_argument("--frames", type=Path,
                    default=Path(tempfile.gettempdir()) / "whodunit-s1-frames")
    a = ap.parse_args()
    print(f"s1 'the fault, drawn' — {DURATION}s")
    render_sequence(state, draw, DURATION, a.out, a.frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
