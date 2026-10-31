#!/usr/bin/env bash
# Liveness + schema + capability snapshot of a running local API.
set -euo pipefail
BASE="${1:-http://127.0.0.1:8000}"
curl -fsS "$BASE/health" | python3 -c '
import json,sys; h=json.load(sys.stdin)
print("status      :", h["status"]); print("ready       :", h["ready"])
print("db          :", h["checks"]["database"]); print("schema      :", h["checks"]["schema"]["verdict"], h["checks"]["schema"]["database_revision"])
print("blocking    :", h["blocking_capabilities"]); print("degraded    :", h["degraded_capabilities"])'
curl -fsS "$BASE/api/v1/wardrobe/stylist/status" 2>/dev/null && echo
