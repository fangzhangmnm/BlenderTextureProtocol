#!/usr/bin/env bash
# POST 新建贴图（默认 checker，名字必填）。
# Usage: ./post.sh <name> [stripes|checker]
. "$(dirname "$0")/_common.sh"

NAME="${1:?usage: $0 <name> [stripes|checker]}"
PATTERN="${2:-checker}"
case "$PATTERN" in
  stripes) FIXTURE="$STRIPES" ;;
  checker) FIXTURE="$CHECKER" ;;
  *) echo "unknown pattern: $PATTERN (use stripes or checker)" >&2; exit 1 ;;
esac

echo "── POST $NAME ($PATTERN) ──"
api -X POST "$BTP_URL/v1/textures" \
  -H "Content-Type: image/png" \
  -H "X-BTP-Name: $NAME" \
  --data-binary "@$FIXTURE"
