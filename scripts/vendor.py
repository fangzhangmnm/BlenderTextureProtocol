#!/usr/bin/env python3
"""Vendor aiortc + non-media deps into blender_addon/btp/vendor/<platform>/

Strategy:
1. Install aiortc with --no-deps (skips av/ffmpeg, ~30MB saved per platform).
2. Install non-media deps individually.
3. Write a tiny av stub module — satisfies aiortc's import-time references
   without shipping ffmpeg. DataChannel-only paths never invoke media
   classes at runtime; if they ever did, the stubs raise AttributeError
   immediately so failure is loud, not silent.

Run once per Blender major version update (e.g. Blender 5.0 → 6.0 if
the Python ABI changes). Run also when bumping aiortc.

Currently targets Windows x64 / cp311 only (Blender 5.x ships Py 3.11).
Add other platforms by appending to TARGETS.
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "blender_addon" / "btp" / "vendor"

PYTHON_VERSION = "311"

PACKAGES_NO_DEPS = ["aiortc"]
DEPS = [
    "aioice", "cffi", "cryptography", "dnspython",
    "google-crc32c", "ifaddr", "pyee", "pylibsrtp",
    "pyopenssl", "pycparser", "typing-extensions",
]

# (pip --platform tag, vendor dir name)
TARGETS = [
    ("win_amd64", "win-amd64-py311"),
]

AV_STUB = {
    "__init__.py": (
        '"""Stub av — satisfies aiortc imports without shipping ffmpeg.\n'
        'DataChannel-only paths never invoke these classes at runtime."""\n'
        "class AudioFrame: pass\n"
        "class VideoFrame: pass\n"
        "class AudioResampler: pass\n"
        "class CodecContext: pass\n"
        "class AudioCodecContext: pass\n"
    ),
    "frame.py": "class Frame: pass\n",
    "packet.py": "class Packet: pass\n",
    "audio/__init__.py": "class AudioStream: pass\n",
    "video/__init__.py": "",
    "video/codeccontext.py": "class VideoCodecContext: pass\n",
    "video/stream.py": "class VideoStream: pass\n",
}


def _pip_install(args, common):
    cmd = [sys.executable, "-m", "pip", "install", *args, *common]
    subprocess.check_call(cmd)


def install_target(target: Path, platform: str) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    common = [
        "--target", str(target),
        "--platform", platform,
        "--python-version", PYTHON_VERSION,
        "--only-binary=:all:",
        "--upgrade", "--quiet",
    ]
    _pip_install([*PACKAGES_NO_DEPS, "--no-deps"], common)
    _pip_install(DEPS, common)

    av_dir = target / "av"
    av_dir.mkdir(exist_ok=True)
    for rel_path, content in AV_STUB.items():
        full = av_dir / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)

    # Strip __pycache__ written by host Python during install. The .pyc files
    # carry the host's magic number / paths and are useless on the target.
    for pyc in target.rglob("__pycache__"):
        if pyc.is_dir():
            shutil.rmtree(pyc)


def _summarize(target: Path) -> None:
    files = sum(1 for f in target.rglob("*") if f.is_file())
    size_mb = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / (1024 * 1024)
    print(f"  {files} files, {size_mb:.1f} MB")


def main() -> int:
    for platform, dir_name in TARGETS:
        target = VENDOR_DIR / dir_name
        print(f"\n=== {platform} → {target.relative_to(ROOT)} ===")
        install_target(target, platform)
        _summarize(target)
    print(f"\nDone. Vendor root: {VENDOR_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
