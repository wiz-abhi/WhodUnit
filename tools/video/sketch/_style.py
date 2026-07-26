"""Hand-drawn (matplotlib ``plt.xkcd()``) sketch frames — the shared kit.

This is the render pattern behind ``docs/assets/flow-pipeline.png`` and
``docs/assets/flow-signoz.png``, generalised into an *animated* form: a script
declares (a) a ``state(t)`` function returning one alpha per named element and
(b) a ``draw(ax, state)`` function, and :func:`render_sequence` turns that into a
30 fps PNG frame sequence which ffmpeg encodes to 1920x1080 H.264.

Two things matter for matching the existing diagrams:

* **Font.** ``plt.xkcd()`` asks for ``xkcd Script`` / ``Humor Sans`` / ``Comic
  Neue`` and falls through to **Comic Sans MS**, which is what the two committed
  PNGs actually rendered with. ``DejaVu Sans`` is appended as a *fallback family*
  (matplotlib >= 3.6 does glyph-level fallback) purely so the few symbols Comic
  Sans lacks — ``⋈``, ``✗`` — do not render as tofu.
* **No white halo.** xkcd mode installs a 4 px white ``withStroke`` path effect
  on everything, which on a dark card turns every glyph into a smeared outline.
  Re-installing it at ``linewidth=0`` kills it without disabling the sketch
  wiggle on the paths themselves.

Frame caching: consecutive frames whose alpha vector is unchanged (i.e. a hold)
are *copied*, never re-rendered. Two wins — the render is ~3x faster, and the
xkcd path jitter cannot "boil" during a hold, because the held frames are
literally the same bytes.

    uv run --with matplotlib python tools/video/sketch/render_s1.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import patheffects as pe
from matplotlib.lines import Line2D
from matplotlib.patches import (
    Arc,
    Ellipse,
    FancyArrowPatch,
    FancyBboxPatch,
    Rectangle,
)

REPO = Path(__file__).resolve().parents[3]
RAW = REPO / "docs" / "video" / "raw"

W, H, FPS, DPI = 1920, 1080, 30, 100

# The palette of docs/assets/flow-*.png. Those two PNGs are transparent-backed;
# a video frame cannot be, so the page sits on a near-black that is still a shade
# darker than the cards, and the cards keep reading as cards.
BG = "#080d13"
CARD = "#0f1720"
GREEN = "#10b981"
AMBER = "#f59e0b"
BLUE = "#38bdf8"
INK = "#e5e7eb"
GREY = "#9ca3af"
RED = "#f87171"


# ------------------------------------------------------------------ style / canvas

def setup() -> None:
    plt.xkcd(scale=1.0, length=100, randomness=2)
    plt.rcParams.update({
        "font.family": ["Comic Sans MS", "DejaVu Sans"],
        # xkcd() sets a 4px white stroke on every artist; linewidth=0 kills the
        # halo while leaving the sketch distortion alone.
        "path.effects": [pe.withStroke(linewidth=0, foreground=BG)],
        "figure.facecolor": BG,
        "savefig.facecolor": BG,
        # ...and the figure patch's own (white, sketch-wobbled) edge.
        "figure.edgecolor": BG,
        "savefig.edgecolor": BG,
        "text.color": INK,
        "axes.unicode_minus": False,
    })


def new_frame():
    fig = plt.figure(figsize=(W / DPI, H / DPI), dpi=DPI)
    # The figure's own background patch is a Patch too: even at linewidth 0 the
    # sketch filter renders its outline as a hairline scribble around all four
    # edges of the frame. Opt it out of the wiggle.
    fig.patch.set_linewidth(0)
    fig.patch.set_sketch_params(None)
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    # The axes' own background rectangle is a Patch, so xkcd's path.sketch
    # wobbles its outline into a dashed scribble around the frame edge. Hide it
    # and let the figure facecolor be the page.
    ax.patch.set_visible(False)
    ax.set_frame_on(False)
    return fig, ax


# ------------------------------------------------------------------ easing

def fade(t: float, t_in: float, dur: float = 0.45) -> float:
    """Smoothstep 0 -> 1 starting at ``t_in``."""
    if t < t_in:
        return 0.0
    x = min(1.0, (t - t_in) / dur)
    return x * x * (3.0 - 2.0 * x)


def fade_dim(t: float, t_in: float, t_dim: float | None = None,
             dim_to: float = 0.5, dur: float = 0.45, dim_dur: float = 0.6) -> float:
    """Fade in at ``t_in``; later ease down to ``dim_to`` at ``t_dim``."""
    a = fade(t, t_in, dur)
    if t_dim is not None and t > t_dim:
        k = fade(t, t_dim, dim_dur)
        a = a * (1.0 - k) + dim_to * k
    return a


# ------------------------------------------------------------------ primitives

def card(ax, box, text, color, a, *, sub=None, dashed=False, size=19,
         sub_size=15, fill=CARD, lw=2.6, radius=14, zorder=3):
    """A rounded dark card with a coloured hand-drawn border."""
    if a <= 0.004:
        return
    x, y, w, h = box
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=color, facecolor=fill, alpha=a,
        linestyle=(0, (6, 5)) if dashed else "solid", zorder=zorder,
    ))
    if text:
        cy = y + h / 2 + (11 if sub else 0)
        ax.text(x + w / 2, cy, text, ha="center", va="center",
                fontsize=size, color=INK, alpha=a, zorder=zorder + 1)
    if sub:
        ax.text(x + w / 2, y + h / 2 - 15, sub, ha="center", va="center",
                fontsize=sub_size, color=GREY, alpha=a, zorder=zorder + 1)


def elbow(ax, parent, child, color, a, *, lw=2.2, stub=22, zorder=2):
    """Trace-tree connector: down the parent's left rail, then into the child."""
    if a <= 0.004:
        return
    px, py, _pw, _ph = parent
    cx, cy, _cw, ch = child
    x = px + stub
    ymid = cy + ch / 2
    ax.add_line(Line2D([x, x, cx - 24], [py + 4, ymid, ymid], color=color, lw=lw,
                       alpha=a, zorder=zorder, solid_capstyle="round"))
    ax.add_patch(FancyArrowPatch((cx - 26, ymid), (cx - 3, ymid),
                                 arrowstyle="-|>", mutation_scale=15,
                                 color=color, lw=lw, alpha=a, zorder=zorder))


def ring(ax, cx, cy, w, h, color, a, *, lw=3.0, ls="solid", zorder=6):
    """The 'circle it' mark."""
    if a <= 0.004:
        return
    ax.add_patch(Ellipse((cx, cy), w, h, fill=False, edgecolor=color, lw=lw,
                         alpha=a, linestyle=ls, zorder=zorder))


def box_mark(ax, box, color, a, *, lw=3.2, radius=22, zorder=6):
    """A rounded box drawn *around* something already on screen."""
    if a <= 0.004:
        return
    x, y, w, h = box
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=color, facecolor="none", alpha=a, zorder=zorder,
    ))


def cross(ax, cx, cy, s, color, a, *, lw=3.4, zorder=8):
    """A hand-drawn ✗ (two strokes — no glyph, so no font dependency)."""
    if a <= 0.004:
        return
    for dx in (1, -1):
        ax.add_line(Line2D([cx - s * dx, cx + s * dx], [cy - s, cy + s],
                           color=color, lw=lw, alpha=a, zorder=zorder,
                           solid_capstyle="round"))


def label(ax, x, y, s, color, a, *, size=20, ha="center", va="center",
          style="normal", zorder=9):
    if a <= 0.004:
        return
    ax.text(x, y, s, ha=ha, va=va, fontsize=size, color=color, alpha=a,
            style=style, zorder=zorder)


def divider(ax, x, y0, y1, a, *, color=GREY, lw=1.6):
    if a <= 0.004:
        return
    ax.add_line(Line2D([x, x], [y0, y1], color=color, lw=lw, alpha=a * 0.35,
                       linestyle=(0, (5, 9)), zorder=1))


def arrow(ax, p0, p1, color, a, *, lw=2.6, rad=0.0, ls="solid", scale=18, zorder=5):
    if a <= 0.004:
        return
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle="-|>", mutation_scale=scale, color=color, lw=lw,
        alpha=a, linestyle=ls, zorder=zorder,
        connectionstyle=f"arc3,rad={rad}",
    ))


def cylinder(ax, cx, ybot, w, h, color, a, *, eh=52, fill=CARD, lw=2.6, zorder=3):
    """A datastore drum: filled body, front bottom arc, two rails, top ellipse."""
    if a <= 0.004:
        return
    ax.add_patch(Ellipse((cx, ybot), w, eh, facecolor=fill, edgecolor="none",
                         alpha=a, zorder=zorder))
    ax.add_patch(Rectangle((cx - w / 2, ybot), w, h, facecolor=fill,
                           edgecolor="none", alpha=a, zorder=zorder))
    ax.add_patch(Arc((cx, ybot), w, eh, theta1=180, theta2=360, edgecolor=color,
                     lw=lw, alpha=a, zorder=zorder + 1))
    for x in (cx - w / 2, cx + w / 2):
        ax.add_line(Line2D([x, x], [ybot, ybot + h], color=color, lw=lw, alpha=a,
                           zorder=zorder + 1))
    ax.add_patch(Ellipse((cx, ybot + h), w, eh, facecolor=fill, edgecolor=color,
                         lw=lw, alpha=a, zorder=zorder + 2))


# ------------------------------------------------------------------ driver

def encode(frames_dir: Path, out: Path, fps: int = FPS) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-framerate", str(fps), "-i", str(frames_dir / "f%05d.png"),
         "-vf", "scale=1920:1080:flags=lanczos,setsar=1",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18",
         "-pix_fmt", "yuv420p", "-r", str(fps), str(out)],
        check=True,
    )


def probe(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def render_sequence(state, draw, duration: float, out: Path, frames_dir: Path,
                    fps: int = FPS) -> float:
    """Render ``duration`` seconds of ``draw(ax, state(t))`` and encode to ``out``."""
    setup()
    frames_dir.mkdir(parents=True, exist_ok=True)
    for stale in frames_dir.glob("f*.png"):
        stale.unlink()

    n = round(duration * fps)
    prev_key = None
    prev_path: Path | None = None
    rendered = 0
    for i in range(n):
        st = state(i / fps)
        key = tuple(round(v, 3) for v in st.values())
        path = frames_dir / f"f{i:05d}.png"
        if key == prev_key and prev_path is not None:
            shutil.copyfile(prev_path, path)
            continue
        fig, ax = new_frame()
        draw(ax, st)
        fig.savefig(path, dpi=DPI, facecolor=BG, edgecolor=BG)
        plt.close(fig)
        prev_key, prev_path = key, path
        rendered += 1

    encode(frames_dir, out, fps)
    measured = probe(out)
    print(f"  {n} frames ({rendered} rendered, {n - rendered} held) -> {out}")
    print(f"  measured {measured:.2f}s")
    return measured
