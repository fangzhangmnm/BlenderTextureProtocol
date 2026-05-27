#!/usr/bin/env bash
# 列出当前所有贴图。
. "$(dirname "$0")/_common.sh"

echo "── textures ──"
curl -s "$BTP_URL/v1/textures" | names
