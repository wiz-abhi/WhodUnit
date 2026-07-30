#!/usr/bin/env bash
# verify-repro.sh — reproduce Whodunit's flagship verdict against a live SigNoz stack.
#
# What it does, end to end:
#   1. emits the disclosed demo corpus (deterministic under --seed) into SigNoz via OTLP,
#   2. waits for ingestion,
#   3. runs `whodunit explain` against the live engine,
#   4. asserts the verdict is a DISCRIMINATOR compiling to `(A => B) && NOT C`, verified
#      with recall 1.0 (the environment-independent guarantee — the compiled query
#      captures every labelled bad trace even on a shared/contaminated stack).
#
# Prerequisites (see README Quickstart):
#   pip install -e ".[corpus]"                 # engine + corpus emitter
#   a SigNoz stack running (foundryctl cast -f deploy/casting.yaml on a clean host)
#   export SIGNOZ_URL SIGNOZ_EMAIL SIGNOZ_PASSWORD SIGNOZ_ORG_ID
#
# Usage:  bash scripts/verify-repro.sh
# Tunables (env): SEED (778) FAULT (conditional_dep) TRACES (800)
#                 OTLP_ENDPOINT (http://localhost:4318) INGEST_WAIT (45 seconds)
set -euo pipefail

SEED="${SEED:-778}"
FAULT="${FAULT:-conditional_dep}"
TRACES="${TRACES:-800}"
OTLP_ENDPOINT="${OTLP_ENDPOINT:-http://localhost:4318}"
INGEST_WAIT="${INGEST_WAIT:-45}"

# repo root = parent of this script's dir, regardless of where it's invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

red() { printf '\033[31m%s\033[0m\n' "$1"; }
grn() { printf '\033[32m%s\033[0m\n' "$1"; }
step() { printf '\n\033[1m▸ %s\033[0m\n' "$1"; }

# --- 0. preconditions -------------------------------------------------------
step "0 · preconditions"
missing=0
for v in SIGNOZ_URL SIGNOZ_EMAIL SIGNOZ_PASSWORD SIGNOZ_ORG_ID; do
  if [ -z "${!v:-}" ]; then red "  missing env: $v"; missing=1; fi
done
[ "$missing" = 0 ] || { red "Set the SIGNOZ_* env vars first (see README Quickstart)."; exit 2; }
command -v whodunit >/dev/null || { red "'whodunit' not on PATH — run: pip install -e \".[corpus]\""; exit 2; }
python -c "import opentelemetry" 2>/dev/null || { red "corpus deps missing — run: pip install -e \".[corpus]\""; exit 2; }
grn "  env + install OK · target $SIGNOZ_URL"

# --- 1. emit the corpus -----------------------------------------------------
step "1 · emit corpus (seed $SEED, fault $FAULT, $TRACES traces) → $OTLP_ENDPOINT"
python -m corpus.generate --traces "$TRACES" --seed "$SEED" \
  --fault "$FAULT" --endpoint "$OTLP_ENDPOINT"

MANIFEST="$(ls -t corpus/out/manifest-${FAULT}-s${SEED}-n${TRACES}-*.json 2>/dev/null | head -1 || true)"
[ -n "$MANIFEST" ] || { red "No manifest written to corpus/out/ — did emission fail?"; exit 1; }
grn "  manifest: $MANIFEST"

# --- 2. wait for ingestion --------------------------------------------------
step "2 · wait ${INGEST_WAIT}s for SigNoz to ingest, then smoke-check"
sleep "$INGEST_WAIT"
python -m corpus.smoke --endpoint "$OTLP_ENDPOINT" || \
  red "  smoke check reported an issue — continuing; explain will show the truth"

# --- 3. explain against the live engine -------------------------------------
step "3 · whodunit explain (extract → mine → compile → verify)"
OUT="$(mktemp)"
whodunit explain --from-manifest "$MANIFEST" --json >"$OUT"

# --- 4. assert the invariants -----------------------------------------------
step "4 · verdict"
python - "$OUT" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
v = d.get("verification") or {}
verdict = d.get("verdict")
expr = (d.get("compiled") or {}).get("expression")
recall = v.get("recall")
mined, signoz = v.get("mined_count"), v.get("signoz_count")

print(f"  verdict      : {verdict}")
print(f"  compiled     : {expr}")
print(f"  receipt      : mined {mined} · SigNoz {signoz} · "
      f"recall {recall} · precision {v.get('precision')}")
print(f"  verdict_hash : {d.get('verdict_hash')}")

ok = (verdict == "discriminator"
      and expr == "(A => B) && NOT C"
      and isinstance(recall, (int, float)) and abs(recall - 1.0) < 1e-9)
if mined is not None and mined == signoz:
    print("  note         : mined == SigNoz exactly (clean single-corpus stack)")
elif mined != signoz:
    print("  note         : mined != SigNoz — expected on a shared/contaminated stack; "
          "recall==1.0 is the environment-independent guarantee")
print()
if ok:
    print("\033[32mPASS — reproduced the flagship discriminator, verified live.\033[0m")
    sys.exit(0)
print("\033[31mFAIL — verdict did not match the expected invariant.\033[0m")
sys.exit(1)
PY
