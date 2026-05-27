#!/usr/bin/env bash
# 拉一张贴图的字节并计算 sha256 (可与 fixture hash 对比验证 round-trip)。
# Usage: ./get_hash.sh <name>
. "$(dirname "$0")/_common.sh"

NAME="${1:?usage: $0 <name>}"
echo "── /v1/textures/$NAME/data ──"
curl -s "$BTP_URL/v1/textures/$NAME/data" | sha256sum | awk '{print "sha256: " $1}'
echo "── 对比 fixture hashes ──"
echo "checker:  $(sha256sum "$CHECKER" | awk '{print $1}')"
echo "stripes:  $(sha256sum "$STRIPES" | awk '{print $1}')"
