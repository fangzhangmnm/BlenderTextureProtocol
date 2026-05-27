#!/usr/bin/env bash
# Shared config for BTP debug scripts.
# Source via: . "$(dirname "$0")/_common.sh"

set -euo pipefail

BTP_URL="${BTP_URL:-http://127.0.0.1:18765}"

# Fixtures (Windows paths work via WSL mount).
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CHECKER="$REPO_ROOT/fixtures/checker_512.png"
STRIPES="$REPO_ROOT/fixtures/stripes_512.png"

# Pretty-print JSON if python3 is available, else passthrough.
pp() {
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import sys,json; sys.stdout.write(json.dumps(json.load(sys.stdin), ensure_ascii=False, indent=2))"
    echo
  else
    cat
  fi
}

# Pretty-print just texture name list.
names() {
  python3 -c "import sys,json; [print(f'  {t[\"name\"]}') for t in json.load(sys.stdin)]"
}

# Call curl, print JSON body (pretty), then "HTTP <code>" on its own line.
# Avoids mixing curl -w status code into the response body (which breaks JSON parsing).
api() {
  local tmp
  tmp=$(mktemp)
  local code
  code=$(curl -s -o "$tmp" -w "%{http_code}" "$@")
  if [[ -s "$tmp" ]]; then
    pp < "$tmp" || cat "$tmp"
  fi
  echo "HTTP $code"
  rm -f "$tmp"
}
