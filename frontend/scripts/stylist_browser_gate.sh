#!/usr/bin/env bash
# Focused browser gate for the StyleList drawer (spec 009, T029).
#
# Runs the two drawer-scoped probes against a served production build:
#   1. stylist_drawer_a11y_probe.mjs   — axe (WCAG 2.x A/AA, 2.2 AA), colour
#      contrast enabled; fails on serious/critical violations only. axe
#      "incomplete" results are reported, never counted as passes.
#   2. stylist_drawer_keyboard_probe.mjs — real key presses: Tab order, visible
#      focus, Escape, focus restoration, accessible names; en + ar (RTL).
#
# Deliberately NOT included: browser_a11y_rtl.py. Its exit code also counts
# catalogue copy that is English inside the Arabic bundle (cross-workstream
# T030/T031) and so is not a drawer regression signal.
#
# No backend and no provider calls are needed: the probes stop at the drawer.
#
# Usage (from frontend/, after `npm ci` and `npm run build`):
#   bash scripts/stylist_browser_gate.sh
# Env: GATE_PORT (default 43123), GATE_OUT (default ./gate-artifacts).
set -uo pipefail

cd "$(dirname "$0")/.."
PORT="${GATE_PORT:-43123}"
OUT="${GATE_OUT:-$PWD/gate-artifacts}"
BASE_URL="http://127.0.0.1:${PORT}"
mkdir -p "$OUT"

if [ ! -f dist/index.html ]; then
  echo "gate: dist/ missing — run 'npm run build' first" >&2
  exit 2
fi

# Run the vite binary directly: via `npx` the recorded PID is a wrapper and the
# server would survive the trap below as an orphan.
./node_modules/.bin/vite preview --host 127.0.0.1 --port "$PORT" --strictPort > "$OUT/preview-server.log" 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null; wait "$SERVER_PID" 2>/dev/null; }
trap cleanup EXIT

for _ in $(seq 1 60); do
  if curl -fsS "$BASE_URL/" >/dev/null 2>&1; then break; fi
  sleep 1
done
if ! curl -fsS "$BASE_URL/" >/dev/null 2>&1; then
  echo "gate: preview server did not answer on $BASE_URL" >&2
  exit 2
fi

status=0
BASE_URL="$BASE_URL" PROBE_JSON="$OUT/a11y-probe.json" node scripts/stylist_drawer_a11y_probe.mjs \
  > "$OUT/a11y-probe.log" 2>&1
a11y=$?
echo "gate: axe drawer probe exit=$a11y"
[ "$a11y" -eq 0 ] || status=1

BASE_URL="$BASE_URL" PROBE_JSON="$OUT/keyboard-probe.json" node scripts/stylist_drawer_keyboard_probe.mjs \
  > "$OUT/keyboard-probe.log" 2>&1
kbd=$?
echo "gate: keyboard/focus probe exit=$kbd"
[ "$kbd" -eq 0 ] || status=1

# Show the actionable part of any failure in the job log.
if [ "$status" -ne 0 ]; then
  echo "--- a11y probe output (tail)"; tail -n 60 "$OUT/a11y-probe.log" || true
  echo "--- keyboard probe output (tail)"; tail -n 60 "$OUT/keyboard-probe.log" || true
fi
echo "gate: result=$([ "$status" -eq 0 ] && echo PASS || echo FAIL)"
exit "$status"
