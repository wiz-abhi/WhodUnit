"""Render a recorded terminal beat to 1080p video, entirely offscreen.

Pairs with `run_beat.py`, which already ran the beat for real and stored the raw
ANSI bytes plus the measured wall-clock time. This module converts those bytes
to HTML, lays them out in a terminal-styled page, animates the typing and the
wait, and records the page with headless Chromium at 1920x1080.

Why not grab the screen: this machine is in active use. A desktop capture puts
whatever its owner is doing into the footage and needs the terminal held on top
for the whole take. Rendering offscreen removes both problems, and what ends up
on screen is still the program's own output, byte for byte.

Honest compression: a real `explain` run mines the whole itemset lattice and
takes minutes. The spinner is played back in a few seconds with its counter
ramping to the TRUE elapsed time, which is then printed. No output is edited,
reordered, or invented.

    python tools/video/record_termcast.py b2 --spin 4.0

Writes docs/video/raw/<beat>.mp4.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "docs" / "video" / "raw"
CASTS = RAW / "casts"

# 16-colour + bright palette, matched to the Windows Terminal "Campbell" scheme
# so the rendered frames look like the terminal these commands are run in.
BASE = [
    "#0c0c0c", "#c50f1f", "#13a10e", "#c19c00", "#0037da", "#881798",
    "#3a96dd", "#cccccc", "#767676", "#e74856", "#16c60c", "#f9f1a5",
    "#3b78ff", "#b4009e", "#61d6d6", "#f2f2f2",
]
CSI = re.compile(r"\x1b\[([0-9;]*)m")
# Everything that is NOT an SGR sequence: OSC strings, cursor/erase CSIs
# (final byte a-l or n-z, i.e. anything but "m"), charset selects, and CRs.
OTHER_ESC = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[a-lA-Zn-z]|\x1b[=>]|\r"
)


def _xterm256(n: int) -> str:
    if n < 16:
        return BASE[n]
    if n < 232:
        n -= 16
        r, g, b = (n // 36) % 6, (n // 6) % 6, n % 6
        f = [0, 95, 135, 175, 215, 255]
        return f"#{f[r]:02x}{f[g]:02x}{f[b]:02x}"
    v = 8 + (n - 232) * 10
    return f"#{v:02x}{v:02x}{v:02x}"


def ansi_to_html(text: str) -> list[str]:
    """Convert SGR-coloured text into one HTML string per line."""
    state = {"fg": None, "bg": None, "bold": False, "dim": False, "italic": False,
             "underline": False}
    lines: list[str] = []
    cur: list[str] = []
    open_span = False

    def style() -> str:
        parts = []
        fg = state["fg"]
        if state["bold"] and fg is None:
            fg = "#f2f2f2"
        if fg:
            parts.append(f"color:{fg}")
        if state["bg"]:
            parts.append(f"background:{state['bg']}")
        if state["bold"]:
            parts.append("font-weight:700")
        if state["dim"]:
            parts.append("opacity:.62")
        if state["italic"]:
            parts.append("font-style:italic")
        if state["underline"]:
            parts.append("text-decoration:underline")
        return ";".join(parts)

    def emit(chunk: str) -> None:
        nonlocal open_span
        if not chunk:
            return
        st = style()
        if st:
            cur.append(f'<span style="{st}">{html.escape(chunk)}</span>')
            open_span = True
        else:
            cur.append(html.escape(chunk))

    def apply(codes: list[int]) -> None:
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                state.update(fg=None, bg=None, bold=False, dim=False,
                             italic=False, underline=False)
            elif c == 1:
                state["bold"] = True
            elif c == 2:
                state["dim"] = True
            elif c == 3:
                state["italic"] = True
            elif c == 4:
                state["underline"] = True
            elif c in (22, 21):
                state["bold"] = state["dim"] = False
            elif c == 23:
                state["italic"] = False
            elif c == 24:
                state["underline"] = False
            elif 30 <= c <= 37:
                state["fg"] = BASE[c - 30]
            elif 90 <= c <= 97:
                state["fg"] = BASE[c - 90 + 8]
            elif 40 <= c <= 47:
                state["bg"] = BASE[c - 40]
            elif 100 <= c <= 107:
                state["bg"] = BASE[c - 100 + 8]
            elif c == 39:
                state["fg"] = None
            elif c == 49:
                state["bg"] = None
            elif c in (38, 48):
                key = "fg" if c == 38 else "bg"
                if i + 1 < len(codes) and codes[i + 1] == 5:
                    state[key] = _xterm256(codes[i + 2]); i += 2  # noqa: E702
                elif i + 1 < len(codes) and codes[i + 1] == 2:
                    r, g, b = codes[i + 2], codes[i + 3], codes[i + 4]
                    state[key] = f"#{r:02x}{g:02x}{b:02x}"; i += 4  # noqa: E702
            i += 1

    text = OTHER_ESC.sub("", text)
    pos = 0
    for m in CSI.finditer(text):
        chunk = text[pos:m.start()]
        for j, piece in enumerate(chunk.split("\n")):
            if j:
                lines.append("".join(cur) or "&nbsp;")
                cur = []
            emit(piece)
        codes = [int(x) if x else 0 for x in (m.group(1) or "0").split(";")]
        apply(codes)
        pos = m.end()
    tail = text[pos:]
    for j, piece in enumerate(tail.split("\n")):
        if j:
            lines.append("".join(cur) or "&nbsp;")
            cur = []
        emit(piece)
    lines.append("".join(cur) or "&nbsp;")
    while lines and lines[-1] == "&nbsp;":
        lines.pop()
    _ = open_span
    return lines


PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;padding:0;background:#0c0c0c;width:1920px;height:1080px;overflow:hidden}
  #chrome{height:44px;background:#1f1f1f;display:flex;align-items:center;
          padding:0 18px;color:#9a9a9a;font:500 20px/1 "Segoe UI",sans-serif;
          border-bottom:1px solid #2b2b2b}
  #chrome b{color:#d8d8d8;font-weight:600}
  #dots{display:flex;gap:9px;margin-right:16px}
  #dots i{width:13px;height:13px;border-radius:50%;display:block}
  #wrap{padding:16px 24px;transform-origin:top left}
  pre{margin:0;color:#cccccc;white-space:pre;
      font:__FS__px/1.34 "Cascadia Mono","Consolas","DejaVu Sans Mono",monospace;
      font-variant-ligatures:none}
  .cursor{background:#cccccc;color:#0c0c0c}
</style></head><body>
<div id="chrome"><div id="dots"><i style="background:#ff5f57"></i>
<i style="background:#febc2e"></i><i style="background:#28c840"></i></div>
<span><b>whodunit</b>&nbsp;&nbsp;__TITLE__</span></div>
<div id="wrap"><pre id="t"></pre></div>
<script>
const STEPS = __STEPS__, SPIN = __SPIN__, TYPE_MS = __TYPE__;
const t = document.getElementById('t'), wrap = document.getElementById('wrap');
let buf = [];
const sleep = ms => new Promise(r => setTimeout(r, ms));
function paint(extra){
  t.innerHTML = buf.join('\\n') + (extra === undefined ? '' : (buf.length ? '\\n' : '') + extra);
  const h = wrap.scrollHeight, avail = 1080 - 44 - 28;
  wrap.style.transform = h > avail ? 'scale(' + (avail / h) + ')' : 'none';
}
const PROMPT = '<span style="color:#767676">PS </span>'
             + '<span style="color:#3a96dd">whodunit</span>'
             + '<span style="color:#767676">&gt; </span>';
async function typeCmd(cmd){
  for (let i = 1; i <= cmd.length; i++){
    paint(PROMPT + '<span style="color:#f2f2f2">' + cmd.slice(0,i)
          .replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</span><span class="cursor">&nbsp;</span>');
    await sleep(TYPE_MS);
  }
  buf.push(PROMPT + '<span style="color:#f2f2f2">' + cmd
        .replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</span>');
  paint(); await sleep(320);
}
async function spin(label, real){
  const frames = ['\\u280b','\\u2819','\\u2839','\\u2838','\\u283c','\\u2834','\\u2826','\\u2827','\\u2807','\\u280f'];
  const t0 = performance.now(); let i = 0;
  while (performance.now() - t0 < SPIN){
    const p = (performance.now() - t0) / SPIN;
    paint('<span style="color:#3a96dd">' + frames[i++ % frames.length] + '</span> '
        + '<span style="color:#61d6d6">' + label + '</span>'
        + '<span style="color:#767676">   ' + (p * real).toFixed(1) + 's</span>');
    await sleep(80);
  }
  buf.push('<span style="color:#767676">elapsed ' + real.toFixed(1) + 's</span>');
  paint(); await sleep(260);
}
(async () => {
  await sleep(900);
  for (const s of STEPS){
    await typeCmd(s.cmd);
    if (s.spinner) await spin(s.spinner, s.elapsed);
    if (s.note){
      buf.push('<span style="color:#767676">  # ' + s.note + '</span>');
      paint(); await sleep(400);
    }
    for (const ln of s.lines){ buf.push(ln); }
    paint();
    await sleep(s.hold * 1000);
    if (s !== STEPS[STEPS.length-1]){ buf.push('&nbsp;'); paint(); }
  }
  await sleep(500);
  window.__done = true;
})();
</script></body></html>"""


def build_page(cast: dict, spin: float, type_ms: int, font_px: int) -> str:
    steps = []
    for st in cast["steps"]:
        steps.append({
            "cmd": st["cmd"],
            "spinner": st.get("spinner"),
            "elapsed": st.get("elapsed_s", 0.0),
            "note": st.get("note") or "",
            "hold": st.get("hold", 5.0),
            "lines": ansi_to_html(st.get("ansi", "")),
        })
    return (
        PAGE.replace("__STEPS__", json.dumps(steps))
        .replace("__SPIN__", str(int(spin * 1000)))
        .replace("__TYPE__", str(type_ms))
        .replace("__TITLE__", html.escape(cast["title"]))
        .replace("__FS__", str(font_px))
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("beat")
    ap.add_argument("--spin", type=float, default=4.0,
                    help="Seconds of playback for a step's real wait.")
    ap.add_argument("--type-ms", type=int, default=24)
    ap.add_argument("--font", type=int, default=24)
    ap.add_argument("--max-s", type=float, default=180.0)
    a = ap.parse_args()

    cast = json.loads((CASTS / f"{a.beat}.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="whodunit-cast-"))
    page = tmp / "page.html"
    page.write_text(build_page(cast, a.spin, a.type_ms, a.font), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True,
                                     args=["--force-device-scale-factor=1"])
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(tmp), record_video_size={"width": 1920, "height": 1080},
        )
        pg = ctx.new_page()
        pg.goto(page.as_uri())
        pg.wait_for_function("window.__done === true", timeout=int(a.max_s * 1000))
        pg.wait_for_timeout(400)
        ctx.close()
        browser.close()

    webm = next(tmp.glob("*.webm"))
    out = RAW / f"{a.beat}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(webm),
         "-vf", "scale=1920:1080:flags=lanczos,fps=30", "-c:v", "libx264",
         "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(out)],
        check=True,
    )
    shutil.rmtree(tmp, ignore_errors=True)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    print(f"{a.beat}: {out}  {float(dur):.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
