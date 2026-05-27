#!/usr/bin/env bash
# PUT checker 到指定贴图（默认 T_test）。
# Usage: ./put_checker.sh [name]
. "$(dirname "$0")/_common.sh"

NAME="${1:-T_test}"
echo "── PUT checker → $NAME ──"
api -X PUT "$BTP_URL/v1/textures/$NAME/data" \
  -H "Content-Type: image/png" \
  --data-binary "@$CHECKER"
