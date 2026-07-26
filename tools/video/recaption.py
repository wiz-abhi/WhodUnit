"""Rebuild the burned captions from REAL speech timings, single-line, film-styled.

The first pass estimated cue times from word counts, so captions drifted against
the voice. This transcribes the *final mixed audio* (so timings are already in
final-video time), aligns those words back onto the script text (Whisper mangles
proper nouns -- "Houdhanit", "signals" -- and we want the script's spelling),
then emits one-line cues timed to when the words are actually spoken.

Style is broadcast subtitle: white, soft outline + shadow, no opaque box, so it
reads as part of the picture rather than something pasted on top.

    python tools/video/recaption.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SILENT = REPO / "docs" / "video" / "demo-silent.mp4"
NARRATED = REPO / "docs" / "video" / "whodunit-final.mp4"   # source of the mixed audio
SCRIPT = REPO / "docs" / "NARRATION-SCRIPT-v3.md"
WORK = REPO / "docs" / "video" / "_recap"
SRT = REPO / "docs" / "video" / "CAPTIONS.srt"
OUT = REPO / "docs" / "video" / "whodunit-final.mp4"

MAX_CHARS = 44          # single line only
MIN_CUE = 1.10
MAX_CUE = 5.00
WORD = re.compile(r"[a-z0-9]+")

FOLD = {
    "houdhanit": "whodunit", "hoodunit": "whodunit", "hudunit": "whodunit",
    "whodhanit": "whodunit", "whodunnit": "whodunit", "houdunit": "whodunit",
    "signals": "signoz", "signos": "signoz", "signose": "signoz",
    "babalap": "bubbleup", "bubblap": "bubbleup",
}

# BorderStyle=1 -> outline + shadow, NO filled box. Reads as part of the film.
ASS_STYLE = (
    "Style: Default,Inter,30,&H00FFFFFF,&H000000FF,&H00101010,&H64000000,"
    "-1,0,0,0,100,100,0.4,0,1,2.6,1.4,2,80,80,66,1"
)


def run(cmd: list[str], what: str) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(f"!! {what}\n{(p.stderr or '')[-1500:]}")
        raise SystemExit(1)


def toks(t: str) -> list[str]:
    return [FOLD.get(x, x) for x in WORD.findall(t.lower())]


def script_words() -> list[str]:
    md = SCRIPT.read_text(encoding="utf-8")
    blocks = re.findall(r"```text\n(.*?)```", md, re.S)
    words: list[str] = []
    for b in blocks:
        words += b.split()
    return words


def ts(sec: float) -> str:
    if sec < 0:
        sec = 0.0
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    ms = int(round((s - int(s)) * 1000))
    if ms == 1000:
        s, ms = int(s) + 1, 0
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    audio = WORK / "final-audio.wav"
    nocap = WORK / "narrated-nocap.mp4"

    print("extract mixed audio")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(NARRATED), "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)], "extract audio")

    print("mux narrated, caption-free master")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(SILENT), "-i", str(NARRATED),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
         "-shortest", str(nocap)], "mux")

    print("transcribe final audio (word timings in final-video time)")
    from faster_whisper import WhisperModel
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    segs, _ = model.transcribe(str(audio), word_timestamps=True, vad_filter=False)
    heard: list[dict] = []
    for s in segs:
        for w in (s.words or []):
            for t in toks(w["word"] if isinstance(w, dict) else w.word):
                st = w["start"] if isinstance(w, dict) else w.start
                en = w["end"] if isinstance(w, dict) else w.end
                heard.append({"w": t, "s": float(st), "e": float(en)})
    print(f"  heard {len(heard)} words")

    disp = script_words()                 # display spelling, with punctuation
    norm = [toks(d) for d in disp]        # normalised tokens per display word
    flat: list[str] = []
    owner: list[int] = []
    for i, ts_ in enumerate(norm):
        for t in ts_:
            flat.append(t)
            owner.append(i)

    sm = SequenceMatcher(None, flat, [h["w"] for h in heard], autojunk=False)
    print(f"  alignment ratio {sm.ratio():.3f}")
    tmap: dict[int, tuple[float, float]] = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            di = owner[a + k]
            hw = heard[b + k]
            if di not in tmap:
                tmap[di] = (hw["s"], hw["e"])
            else:
                st, en = tmap[di]
                tmap[di] = (min(st, hw["s"]), max(en, hw["e"]))

    # interpolate any display word Whisper missed
    times: list[tuple[float, float] | None] = [tmap.get(i) for i in range(len(disp))]
    known = [i for i, v in enumerate(times) if v]
    if not known:
        print("!! nothing aligned")
        return 1
    for i in range(len(times)):
        if times[i]:
            continue
        prev = max([k for k in known if k < i], default=None)
        nxt = min([k for k in known if k > i], default=None)
        if prev is not None and nxt is not None:
            a, b = times[prev][1], times[nxt][0]
            frac = (i - prev) / (nxt - prev)
            t0 = a + (b - a) * frac
            times[i] = (t0, t0 + 0.18)
        elif prev is not None:
            t0 = times[prev][1]
            times[i] = (t0, t0 + 0.18)
        else:
            t0 = times[nxt][0]
            times[i] = (max(0.0, t0 - 0.18), t0)

    # chunk into single-line cues, breaking at punctuation where possible
    cues: list[tuple[float, float, str]] = []
    cur: list[int] = []

    def flush() -> None:
        if not cur:
            return
        text = " ".join(disp[i] for i in cur).strip()
        st = times[cur[0]][0]
        en = times[cur[-1]][1]
        if en - st < MIN_CUE:
            en = st + MIN_CUE
        cues.append((st, min(en, st + MAX_CUE), text))
        cur.clear()

    for i, w in enumerate(disp):
        trial = len(" ".join(disp[j] for j in cur + [i]))
        if cur and trial > MAX_CHARS:
            flush()
        cur.append(i)
        if w.endswith((".", "!", "?", "—")) and len(" ".join(disp[j] for j in cur)) > 18:
            flush()
    flush()

    # never let a cue overlap the next
    for i in range(len(cues) - 1):
        s0, e0, t0 = cues[i]
        s1 = cues[i + 1][0]
        if e0 > s1 - 0.04:
            cues[i] = (s0, max(s0 + 0.4, s1 - 0.04), t0)

    lines = []
    for n, (st, en, text) in enumerate(cues, 1):
        lines += [str(n), f"{ts(st)} --> {ts(en)}", text, ""]
    SRT.write_text("\n".join(lines), encoding="utf-8")
    over = [c for c in cues if len(c[2]) > MAX_CHARS]
    print(f"  {len(cues)} single-line cues -> {SRT.name}  (over {MAX_CHARS} chars: {len(over)})")

    print("convert + restyle ass")
    raw = WORK / "cap.raw.ass"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(SRT), str(raw)], "srt->ass")
    out_lines = []
    for ln in raw.read_text(encoding="utf-8").splitlines():
        if ln.startswith("PlayResX:"):
            ln = "PlayResX: 1920"
        elif ln.startswith("PlayResY:"):
            ln = "PlayResY: 1080"
        elif ln.startswith("Style: Default"):
            ln = ASS_STYLE
        out_lines.append(ln)
    ass = WORK / "cap.ass"
    ass.write_text("\n".join(out_lines), encoding="utf-8")

    print("burn")
    esc = str(ass).replace("\\", "/").replace(":", "\\:")
    run(["ffmpeg", "-y", "-v", "error", "-i", str(nocap),
         "-vf", f"ass='{esc}'", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", str(OUT)], "burn")

    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(OUT)], capture_output=True, text=True).stdout.strip()
    print(f"\n{OUT}\n  {float(dur):.2f}s  {len(cues)} cues, single-line, outline style")
    return 0


if __name__ == "__main__":
    sys.exit(main())
