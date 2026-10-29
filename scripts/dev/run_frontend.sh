#!/usr/bin/env bash
# Vite dev server on http://localhost:43123 ; /api is proxied to :8000 (vite.config.ts).
set -euo pipefail; cd "$(dirname "$0")/../../frontend"
[ -d node_modules ] || npm ci
exec npm run dev
