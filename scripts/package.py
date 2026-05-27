#!/usr/bin/env python3
"""Package the BTP Blender addon as a versioned zip.

Reads `version` from `blender_addon/btp/blender_manifest.toml`,
writes `dist/btp-{version}.zip` with the `btp/` folder at zip top-level
(so Blender's "Install from Disk" picks it up correctly).

Run manually or via the auto-package hook (PostToolUse Edit|Write on
files under `blender_addon/btp/`).
"""
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parent.parent
ADDON_DIR = ROOT / "blender_addon" / "btp"
DIST_DIR = ROOT / "dist"


def read_version() -> str:
    manifest = ADDON_DIR / "blender_manifest.toml"
    if not manifest.exists():
        sys.exit(f"ERROR: manifest not found at {manifest}")
    text = manifest.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        sys.exit('ERROR: no `version = "..."` field in manifest')
    return match.group(1)


def main() -> None:
    if not ADDON_DIR.is_dir():
        sys.exit(f"ERROR: addon dir not found at {ADDON_DIR}")
    version = read_version()
    DIST_DIR.mkdir(exist_ok=True)
    out = DIST_DIR / f"btp-{version}.zip"
    if out.exists():
        out.unlink()
    files = 0
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ADDON_DIR.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts:
                continue
            arc = path.relative_to(ADDON_DIR.parent)
            zf.write(path, arc)
            files += 1
    size_kb = out.stat().st_size / 1024
    print(f"[BTP package] {out.relative_to(ROOT)}  ({files} files, {size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
