#!/usr/bin/env bash
# 完整状态快照: scene + textures (含全 metadata) + selection。
. "$(dirname "$0")/_common.sh"

echo "── /v1/scene ──"
curl -s "$BTP_URL/v1/scene" | pp
echo
echo "── /v1/textures ──"
curl -s "$BTP_URL/v1/textures" | pp
echo
echo "── /v1/selection ──"
curl -s "$BTP_URL/v1/selection" | pp
