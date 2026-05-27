#!/usr/bin/env python3
"""Claude Code PostToolUse hook on Edit|Write.

Reads the tool-call JSON from stdin. If the edited file lives inside the
BTP addon folder, re-runs the packager. Silent on success; only emits
output (and non-zero exit) when packaging actually fails.
"""
import json
import subprocess
import sys
from pathlib import Path


ADDON_DIR = Path("/mnt/d/JupyterLocal/20260524 WebPaint/BlenderTextureProtocol/blender_addon/btp").resolve()
PACKAGE_SCRIPT = Path("/mnt/d/JupyterLocal/20260524 WebPaint/BlenderTextureProtocol/scripts/package.py")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    candidate = (
        (payload.get("tool_input") or {}).get("file_path")
        or (payload.get("tool_response") or {}).get("filePath")
    )
    if not candidate:
        return 0

    try:
        resolved = Path(candidate).resolve()
    except (OSError, RuntimeError):
        return 0

    try:
        resolved.relative_to(ADDON_DIR)
    except ValueError:
        return 0

    result = subprocess.run(
        ["python3", str(PACKAGE_SCRIPT)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr or result.stdout)
        return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
