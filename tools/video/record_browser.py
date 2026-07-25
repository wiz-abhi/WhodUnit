"""Record the browser beats with Playwright's own 1920x1080 video capture.

Headless on purpose: the terminal beats are captured off the real screen with
`gdigrab`, and a headless browser never touches the desktop, so a browser beat
can be recorded while a terminal beat is still running.

Credentials come from the environment (SIGNOZ_EMAIL / SIGNOZ_PASSWORD) and are
typed into the live login form — nothing is ever written to a committed file.

    python tools/video/record_browser.py b1     # the GitHub issue
    python tools/video/record_browser.py b5     # the permalink in Trace Explorer
    python tools/video/record_browser.py b6ui   # the armed rule in Alerts
    python tools/video/record_browser.py b8ui   # the repo README

Needs the OTel/Playwright interpreter:
    C:\\Users\\abhis\\Desktop\\OSS\\Signoz\\warmup-agent\\.venv\\Scripts\\python.exe
Writes docs/video/raw/<name>.mp4 (the .webm Playwright emits is transcoded).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "docs" / "video" / "raw"
SIGNOZ = os.environ.get("SIGNOZ_URL", "http://localhost:8080")
VIEWPORT = {"width": 1920, "height": 1080}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def smooth_scroll(page: Page, to: int, seconds: float, steps: int = 60) -> None:
    """Ease a scroll to `to` px over `seconds` so the footage reads on camera."""
    page.evaluate(
        """([to, ms, steps]) => new Promise(res => {
            const from = window.scrollY, d = to - from; let i = 0;
            const id = setInterval(() => {
                i++;
                const t = i / steps, e = t < .5 ? 2*t*t : -1 + (4 - 2*t) * t;
                window.scrollTo(0, from + d * e);
                if (i >= steps) { clearInterval(id); res(); }
            }, ms / steps);
        })""",
        [to, int(seconds * 1000), steps],
    )


def signoz_login(page: Page) -> None:
    email = os.environ.get("SIGNOZ_EMAIL") or ""
    password = os.environ.get("SIGNOZ_PASSWORD") or ""
    if not email or not password:
        raise SystemExit("set SIGNOZ_EMAIL / SIGNOZ_PASSWORD in the environment")
    page.goto(f"{SIGNOZ}/login", wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    try:
        page.fill("input#loginEmail, input[type='email'], input[name='email']", email)
        page.click("button:has-text('Next')")
        page.wait_for_timeout(1500)
    except Exception:
        pass
    try:
        page.fill("input[type='password'], input#currentPassword", password)
        page.click("button[type='submit'], button:has-text('Login')")
    except Exception:
        pass
    page.wait_for_timeout(6000)


def transcode(webm: Path, name: str) -> Path:
    out = RAW / f"{name}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(webm),
         "-vf", "scale=1920:1080:flags=lanczos,fps=30",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", str(out)],
        check=True,
    )
    return out


# --------------------------------------------------------------------------- #
# beats
# --------------------------------------------------------------------------- #
def beat_b1(page: Page) -> None:
    """The citation: SigNoz/signoz#1957, still open since Jan 2023."""
    page.goto(
        "https://github.com/SigNoz/signoz/issues/1957", wait_until="domcontentloaded"
    )
    page.wait_for_timeout(4000)
    smooth_scroll(page, 260, 3.0)
    page.wait_for_timeout(2500)
    smooth_scroll(page, 0, 1.5)
    page.wait_for_timeout(2000)


def beat_b5(page: Page) -> None:
    """The permalink: paste the generated URL, run it, open one trace."""
    url = (RAW / "permalink.txt").read_text(encoding="utf-8").strip()
    signoz_login(page)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(6000)          # builder + operator render, query fires
    # Dismiss the "Edit your quick filters" onboarding tooltip - it is a product
    # tour bubble that happens to sit on top of leaf A. (Not a consent banner.)
    page.evaluate(
        """() => {
            for (const el of document.querySelectorAll('div,section,aside')) {
              if (/Edit your quick filters/.test(el.textContent || '')
                  && (el.textContent || '').length < 400) { el.remove(); return; }
            }
        }"""
    )
    page.wait_for_timeout(3500)
    smooth_scroll(page, 420, 2.5)        # reveal the three leaves + the operator
    page.wait_for_timeout(3500)
    smooth_scroll(page, 900, 2.0)        # the result list
    page.wait_for_timeout(2500)
    for sel in (
        "a[href*='/trace/']",
        "td a",
        "[data-testid='trace-id'] a",
    ):
        try:
            page.click(sel, timeout=4000)
            break
        except Exception:
            continue
    page.wait_for_timeout(9000)          # flame graph
    smooth_scroll(page, 500, 2.0)
    page.wait_for_timeout(3000)


def beat_b6ui(page: Page) -> None:
    """The armed rule in SigNoz's own Alerts UI."""
    signoz_login(page)
    page.goto(f"{SIGNOZ}/alerts", wait_until="domcontentloaded")
    page.wait_for_timeout(7000)
    try:
        page.click("a:has-text('whodunit'), td:has-text('whodunit')", timeout=6000)
        page.wait_for_timeout(8000)
        smooth_scroll(page, 700, 2.5)
        page.wait_for_timeout(5000)
    except Exception:
        page.wait_for_timeout(6000)


def beat_b8ui(page: Page) -> None:
    """The close: the public repo README."""
    page.goto(
        "https://github.com/wiz-abhi/WhodUnit", wait_until="domcontentloaded"
    )
    page.wait_for_timeout(4000)
    smooth_scroll(page, 700, 3.5)
    page.wait_for_timeout(3000)


BEATS = {"b1": beat_b1, "b5": beat_b5, "b6ui": beat_b6ui, "b8ui": beat_b8ui}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("beat", choices=sorted(BEATS))
    p.add_argument("--headed", action="store_true")
    a = p.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="whodunit-brow-"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not a.headed, args=["--force-device-scale-factor=1"]
        )
        ctx = browser.new_context(
            viewport=VIEWPORT,
            record_video_dir=str(tmp),
            record_video_size=VIEWPORT,
            ignore_https_errors=True,
        )
        page = ctx.new_page()
        t0 = time.time()
        try:
            BEATS[a.beat](page)
        finally:
            elapsed = time.time() - t0
            ctx.close()
            browser.close()
    webm = next(tmp.glob("*.webm"))
    out = transcode(webm, a.beat)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"{a.beat}: {out}  (~{elapsed:.1f}s of interaction)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
