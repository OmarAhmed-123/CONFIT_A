#!/usr/bin/env bash
# Reproducible stylist load benchmark on PostgreSQL (docs/performance-test-report.md).
# Starts the watsonx double (5 s ± 1.5 s, 2 % 503, 1 % 429) and a 2-worker API on
# :8010 against confit_bench, runs scripts/load/stylist_load.py, then stops both.
# Takes ~6 minutes for 20 VUs (sign-up pacing is excluded from the timing window).
set -euo pipefail; source "$(dirname "$0")/_env.sh"; cd "$REPO_ROOT"
VUS="${VUS:-20}"; REQ="${REQ:-20}"; OUT="${OUT:-docs/qa/load/stylist_mocked_${VUS}vu_postgres_2workers_5s_$(date +%Y%m%d).json}"
export DATABASE_URL="${BENCH_DATABASE_URL:-postgresql://confit:confit@127.0.0.1:5432/confit_bench}"
"$PY" -m alembic -c backend/alembic.ini upgrade head >/dev/null
DOUBLE_LATENCY_MS=5000 DOUBLE_JITTER_MS=1500 DOUBLE_ERROR_RATE=0.02 DOUBLE_RATE_LIMIT_RATE=0.01 \
  "$PY" -m uvicorn scripts.load.watsonx_double:app --host 127.0.0.1 --port 8089 --log-level warning & DPID=$!
WARDROBE_STYLIST_PROVIDER=watsonx WATSONX_APIKEY=double-key WATSONX_PROJECT_ID=00000000-0000-0000-0000-000000000000 \
WATSONX_URL=http://127.0.0.1:8089 WATSONX_IAM_URL=http://127.0.0.1:8089/identity/token WATSONX_REASONING_MODEL_ID=ibm/granite-4-h-small \
  "$PY" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010 --workers 2 --log-level warning & APID=$!
trap 'kill $APID $DPID 2>/dev/null || true' EXIT
sleep 8
"$PY" scripts/load/stylist_load.py --base http://127.0.0.1:8010 --mode mocked --vus "$VUS" --requests "$REQ" --model-latency 5 --out "$OUT"
echo "[bench] report → $OUT"
