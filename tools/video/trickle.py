"""Keep the armed rule's 5-minute rolling window fed with matching traces.

The alert evaluates a rolling 5m window every 30s, so the "it fired" beat needs
fresh traces that satisfy the compiled discriminator
``(A => B) && NOT C`` — i.e. a ``shop-payment`` span with a DIRECT ``redis-retry``
child and NO ``shop-flag-service`` span anywhere in the trace.

Emitted as raw OTLP/HTTP-JSON with stdlib only (the repo venv has no OTel SDK;
`corpus.generate` needs it). Same shape the materializer's live-fire test used
(`src/whodunit/materialize/NOTES.md` §3).

    uv run python tools/video/trickle.py --every 20 --batch 3
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request

ENDPOINT = os.environ.get("OTLP_ENDPOINT", "http://localhost:4318") + "/v1/traces"
ENV = "whodunit-demo"


def _res(service: str) -> dict:
    return {
        "attributes": [
            {"key": "service.name", "value": {"stringValue": service}},
            {"key": "deployment.environment", "value": {"stringValue": ENV}},
        ]
    }


def _span(name: str, tid: str, sid: str, parent: str | None, t0_ns: int, dur_ns: int) -> dict:
    s = {
        "traceId": tid,
        "spanId": sid,
        "name": name,
        "kind": 2,
        "startTimeUnixNano": str(t0_ns),
        "endTimeUnixNano": str(t0_ns + dur_ns),
        "attributes": [],
        "status": {},
    }
    if parent:
        s["parentSpanId"] = parent
    return s


def emit_batch(n: int) -> int:
    now_ns = int(time.time() * 1e9)
    resource_spans = []
    for i in range(n):
        tid = os.urandom(16).hex()
        root, pay, retry = (os.urandom(8).hex() for _ in range(3))
        t0 = now_ns - 2_000_000_000 + i * 1_000_000
        resource_spans.append(
            {
                "resource": _res("shop-checkout"),
                "scopeSpans": [
                    {
                        "scope": {"name": "whodunit.video.trickle"},
                        "spans": [_span("POST /checkout", tid, root, None, t0, 90_000_000)],
                    }
                ],
            }
        )
        resource_spans.append(
            {
                "resource": _res("shop-payment"),
                "scopeSpans": [
                    {
                        "scope": {"name": "whodunit.video.trickle"},
                        "spans": [
                            _span("POST /charge", tid, pay, root, t0 + 5_000_000, 70_000_000),
                            # the DIRECT child that makes (A => B) true
                            _span("redis-retry", tid, retry, pay, t0 + 20_000_000, 30_000_000),
                        ],
                    }
                ],
            }
        )
        # deliberately NO shop-flag-service resource -> NOT C holds.
    body = json.dumps({"resourceSpans": resource_spans}).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--every", type=float, default=20.0)
    p.add_argument("--batch", type=int, default=3)
    p.add_argument("--minutes", type=float, default=90.0)
    a = p.parse_args()
    deadline = time.time() + a.minutes * 60
    total = 0
    while time.time() < deadline:
        try:
            code = emit_batch(a.batch)
            total += a.batch
            print(
                f"[{time.strftime('%H:%M:%S')}] emitted {a.batch} matching traces "
                f"-> {code}  (total {total})",
                flush=True,
            )
        except Exception as exc:
            print(f"[{time.strftime('%H:%M:%S')}] emit failed: {exc}", flush=True)
        time.sleep(a.every)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
