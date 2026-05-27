#!/usr/bin/env bash
# Rename a texture.
# Usage: ./rename.sh <old_name> <new_name>
. "$(dirname "$0")/_common.sh"

OLD="${1:?usage: $0 <old_name> <new_name>}"
NEW="${2:?usage: $0 <old_name> <new_name>}"

echo "── rename $OLD → $NEW ──"
api -X POST "$BTP_URL/v1/textures/$OLD/rename" \
  -H "Content-Type: application/json" \
  -d "{\"new_name\":\"$NEW\"}"
