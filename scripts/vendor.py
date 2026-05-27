#!/usr/bin/env python3
"""Vendor aiortc + non-media deps as Blender Extension wheels.

Strategy:
1. `pip download` aiortc + explicit non-av deps as `.whl` files into
   blender_addon/btp/wheels/. No flat sys.path mess — Blender 4.2+ has a
   `wheels = [...]` field in blender_manifest.toml that installs these
   into a per-extension isolated environment (no top-level module pollution
   warning).
2. Build a tiny `av` stub wheel (~1 KB) — satisfies aiortc's hard import
   of `av.AudioFrame` etc. without shipping the 30+ MB ffmpeg-backed
   PyAV. DataChannel-only paths never call into these classes.
3. Auto-update `blender_manifest.toml`'s `wheels = [...]` field with the
   resulting wheel paths so the addon manifest stays in sync.

Currently targets Windows x64 / cp311 only (Blender 5.x ships Py 3.11).
Add other platforms by appending to TARGETS; pip will fetch the right
platform wheels for each entry.
"""
import base64
import hashlib
import io
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WHEELS_DIR = ROOT / "blender_addon" / "btp" / "wheels"
MANIFEST = ROOT / "blender_addon" / "btp" / "blender_manifest.toml"

PYTHON_VERSION = "311"

# aiortc downloaded with --no-deps; av deliberately excluded; rest pulled
# explicitly to bypass aiortc's `av >= 14` requirement (we satisfy it
# with the stub wheel below, declared as av 14.0.0).
PACKAGES_NO_DEPS = ["aiortc"]
EXPLICIT_DEPS = [
    "aioice", "cffi", "cryptography", "dnspython",
    "google-crc32c", "ifaddr", "pyee", "pylibsrtp",
    "pyopenssl", "pycparser", "typing-extensions",
]

# (pip --platform tag, comment for readability)
TARGETS = [
    ("win_amd64", "Windows x64"),
]

# av stub: claim version 14.0.0 so aiortc 1.14's "av (>=14,<17)"
# Requires-Dist constraint is satisfied at install time.
AV_STUB_VERSION = "14.0.0"
AV_STUB_FILES = {
    "av/__init__.py": (
        '"""Stub av module — satisfies aiortc import targets without shipping\n'
        "ffmpeg. DataChannel-only paths never invoke these classes at runtime.\n"
        'Raises AttributeError loudly if media codepaths are ever exercised."""\n'
        "class AudioFrame: pass\n"
        "class VideoFrame: pass\n"
        "class AudioResampler: pass\n"
        "class CodecContext: pass\n"
        "class AudioCodecContext: pass\n"
    ),
    "av/frame.py": "class Frame: pass\n",
    "av/packet.py": "class Packet: pass\n",
    "av/audio/__init__.py": "class AudioStream: pass\n",
    "av/video/__init__.py": "",
    "av/video/codeccontext.py": "class VideoCodecContext: pass\n",
    "av/video/stream.py": "class VideoStream: pass\n",
}


def _pip_download(args, dest: Path, platform: str) -> None:
    cmd = [
        sys.executable, "-m", "pip", "download",
        *args,
        "--dest", str(dest),
        "--platform", platform,
        "--python-version", PYTHON_VERSION,
        "--only-binary=:all:",
        "--no-cache-dir",
        "--quiet",
    ]
    subprocess.check_call(cmd)


def _wheel_record_entry(name: str, content: bytes) -> str:
    digest = hashlib.sha256(content).digest()
    b64 = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"{name},sha256={b64},{len(content)}"


def build_av_stub_wheel(out_dir: Path) -> str:
    """Construct a minimal PEP 427 wheel for our av stub."""
    name = f"av-{AV_STUB_VERSION}-py3-none-any.whl"
    out_path = out_dir / name

    dist_info_dir = f"av-{AV_STUB_VERSION}.dist-info"
    metadata = (
        "Metadata-Version: 2.1\n"
        "Name: av\n"
        f"Version: {AV_STUB_VERSION}\n"
        "Summary: Local stub of PyAV for aiortc DataChannel-only use; no ffmpeg.\n"
        "License: MIT\n"
    )
    wheel_meta = (
        "Wheel-Version: 1.0\n"
        "Generator: btp-vendor 0.2.1\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n"
    )

    record_lines: list[str] = []
    payload: dict[str, bytes] = {}
    for rel, text in AV_STUB_FILES.items():
        data = text.encode("utf-8")
        payload[rel] = data
        record_lines.append(_wheel_record_entry(rel, data))

    md_bytes = metadata.encode("utf-8")
    wm_bytes = wheel_meta.encode("utf-8")
    record_lines.append(_wheel_record_entry(f"{dist_info_dir}/METADATA", md_bytes))
    record_lines.append(_wheel_record_entry(f"{dist_info_dir}/WHEEL", wm_bytes))
    record_lines.append(f"{dist_info_dir}/RECORD,,")
    record = ("\n".join(record_lines) + "\n").encode("utf-8")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in payload.items():
            zf.writestr(rel, data)
        zf.writestr(f"{dist_info_dir}/METADATA", md_bytes)
        zf.writestr(f"{dist_info_dir}/WHEEL", wm_bytes)
        zf.writestr(f"{dist_info_dir}/RECORD", record)

    return name


def update_manifest_wheels(wheel_filenames: list[str]) -> None:
    """Surgical update of the `wheels = [...]` block in blender_manifest.toml."""
    text = MANIFEST.read_text(encoding="utf-8")
    wheels_lines = ",\n".join(f'    "./wheels/{w}"' for w in sorted(wheel_filenames))
    block = f"wheels = [\n{wheels_lines},\n]\n"

    pattern = re.compile(r"^wheels\s*=\s*\[[\s\S]*?\]\s*\n", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(block, text)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "\n" + block

    MANIFEST.write_text(text, encoding="utf-8")


def main() -> int:
    if WHEELS_DIR.exists():
        shutil.rmtree(WHEELS_DIR)
    WHEELS_DIR.mkdir(parents=True)

    for platform, label in TARGETS:
        print(f"\n=== {platform} ({label}) ===")
        _pip_download([*PACKAGES_NO_DEPS, "--no-deps"], WHEELS_DIR, platform)
        _pip_download(EXPLICIT_DEPS, WHEELS_DIR, platform)

    # Some explicit deps' transitive pure-python pulls (e.g. cryptography
    # pulls cffi which pulls pycparser) are listed explicitly above so
    # they're always downloaded. Any stray .whl from a later pip change
    # still ends up in WHEELS_DIR and is picked up by the manifest update.

    print("\n=== build av stub wheel ===")
    av_wheel = build_av_stub_wheel(WHEELS_DIR)
    print(f"  wrote {av_wheel}")

    wheels = sorted(p.name for p in WHEELS_DIR.glob("*.whl"))
    total_kb = sum(p.stat().st_size for p in WHEELS_DIR.glob("*.whl")) / 1024
    print(f"\n=== {len(wheels)} wheels, {total_kb / 1024:.1f} MB total ===")
    for w in wheels:
        print(f"  {w}")

    update_manifest_wheels(wheels)
    print(f"\nblender_manifest.toml `wheels = [...]` updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
