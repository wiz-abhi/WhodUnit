"""Webhook listener for the demo's "it fired" beat.

Listens on :9099 and logs every POST SigNoz delivers to the armed rule's
channel. The channel URL is ``http://host.docker.internal:9099/whodunit`` so the
``signoz-signoz-0`` container can reach the host.

Prints one compact, camera-legible block per delivery (timestamp, status,
severity/threshold tier, alertname, byte count) and appends the full JSON body
to ``docs/video/raw/webhook.log``.

    uv run python tools/video/webhook_listener.py
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / "docs" / "video" / "raw" / "webhook.log"
PORT = 9099


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

        ts = time.strftime("%H:%M:%S")
        try:
            body = json.loads(raw)
        except Exception:
            body = {}
        status = body.get("status", "?")
        alerts = body.get("alerts") or [{}]
        labels = alerts[0].get("labels") or {}
        colour = "\033[91m" if status == "firing" else "\033[92m"
        print(
            f"{colour}[{ts}]  POST {self.path}   status={status.upper()}   "
            f"{len(raw)} bytes\033[0m\n"
            f"          alertname = {labels.get('alertname','?')}\n"
            f"          severity  = {labels.get('severity','?')}   "
            f"threshold = {labels.get('threshold.name','?')}\n"
            f"          ruleId    = {labels.get('ruleId','?')}",
            flush=True,
        )
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(f"=== {ts} {self.path} {len(raw)}B ===\n")
            fh.write(json.dumps(body, indent=2) + "\n")

        # In the beat-6 take the listener is the last thing on screen, so it
        # stops itself on the climax instead of running past the shot.
        if status == "firing" and os.environ.get("WHODUNIT_EXIT_ON_FIRE"):
            print("\n  the compiled discriminator is now a live SigNoz alert.\n", flush=True)
            threading.Thread(target=lambda: (time.sleep(6), os._exit(0))).start()

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"whodunit webhook listener\n")

    def log_message(self, *_a: object) -> None:  # silence the default access log
        return


def main() -> int:
    print(
        f"whodunit webhook listener  ::  http://0.0.0.0:{PORT}/whodunit\n"
        f"channel URL (from the signoz container): "
        f"http://host.docker.internal:{PORT}/whodunit\n"
        f"waiting for SigNoz to deliver...\n",
        flush=True,
    )
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
