#!/usr/bin/env bash
# Reproducible stylist load benchmark on PostgreSQL (docs/performance-test-report.md).
# Starts the watsonx double (defaults 5 s ± 1.5 s, 2 % 503, 1 % 429, faults after
# latency; override via DOUBLE_* / MODEL_LATENCY_S — see docs/performance/) and a 2-worker API on
# :8010 against confit_bench, runs scripts/load/stylist_load.py, then stops both.
# Takes ~6 minutes for 20 VUs (sign-up pacing is excluded from the timing window).
set -euo pipefail; source "$(dirname "$0")/_env.sh"; cd "$REPO_ROOT"
VUS="${VUS:-20}"; REQ="${REQ:-20}"; OUT="${OUT:-docs/qa/load/stylist_mocked_${VUS}vu_postgres_2workers_5s_$(date +%Y%m%d).json}"
export DATABASE_URL="$BENCH_DATABASE_URL"
"$PY" -m alembic -c backend/alembic.ini upgrade head >/dev/null
DOUBLE_LATENCY_MS="${DOUBLE_LATENCY_MS:-5000}" DOUBLE_JITTER_MS="${DOUBLE_JITTER_MS:-1500}" DOUBLE_ERROR_RATE="${DOUBLE_ERROR_RATE:-0.02}" DOUBLE_RATE_LIMIT_RATE="${DOUBLE_RATE_LIMIT_RATE:-0.01}" DOUBLE_FAULT_TIMING="${DOUBLE_FAULT_TIMING:-after}" \
  "$PY" -m uvicorn scripts.load.watsonx_double:app --host 127.0.0.1 --port 8089 --log-level warning & DPID=$!
WARDROBE_STYLIST_PROVIDER=watsonx WATSONX_APIKEY=double-key WATSONX_PROJECT_ID=00000000-0000-0000-0000-000000000000 \
WATSONX_URL=http://127.0.0.1:8089 WATSONX_IAM_URL=http://127.0.0.1:8089/identity/token WATSONX_REASONING_MODEL_ID=ibm/granite-4-h-small \
  "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010 --workers 2 --log-level warning & APID=$!
trap 'kill $APID $DPID 2>/dev/null || true' EXIT
sleep 8
"$PY" scripts/load/stylist_load.py --base http://127.0.0.1:8010 --mode mocked --vus "$VUS" --requests "$REQ" --model-latency "${MODEL_LATENCY_S:-5}" --out "$OUT" || LOAD_STATUS=$?
LOAD_STATUS="${LOAD_STATUS:-0}"
# Attach the double's fault counters and the harness knobs so the report says
# how many requests were retried (injected 429/503 = retried-once requests;
# WATSONX_MAX_RETRIES bounds the amplification) and under which timing rule.
"$PY" - "$OUT" <<'PYEOF'
import json, sys, os, urllib.request
out = sys.argv[1]
try:
    stats = json.load(urllib.request.urlopen("http://127.0.0.1:8089/__stats", timeout=5))
except Exception as exc:  # the report is still valid without the counters
    stats = {"unavailable": str(exc)[:120]}
d = json.load(open(out))
d["double_stats"] = stats
d["double_knobs"] = {k: os.environ.get(k) for k in ("DOUBLE_LATENCY_MS", "DOUBLE_JITTER_MS", "DOUBLE_ERROR_RATE", "DOUBLE_RATE_LIMIT_RATE", "DOUBLE_FAULT_TIMING")}
json.dump(d, open(out, "w"), indent=2)
PYEOF
echo "[bench] report → $OUT (load exit=$LOAD_STATUS)"
exit "$LOAD_STATUS"
