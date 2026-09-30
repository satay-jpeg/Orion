#!/usr/bin/env bash
# ORION local demo (macOS / Linux). Needs Python 3.10+ and Node.js 20+.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
python3 -m pip install --quiet -r "$ROOT/engine/requirements.txt"
python3 "$ROOT/demo/generate_demo_data.py"
python3 "$ROOT/demo/mock_supabase.py" & MOCK=$!
trap 'kill $MOCK 2>/dev/null' EXIT
cd "$ROOT/web"
[ -d node_modules ] || npm install --no-audit --no-fund
echo "Open http://localhost:3000  (admin: /login, any email/password)"
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 NEXT_PUBLIC_SUPABASE_ANON_KEY=demo NEXT_PUBLIC_DEMO_MODE=1 \
  NEXT_TELEMETRY_DISABLED=1 npm run dev
