#!/usr/bin/env python3
"""Unit + cross-language test for BTP framing.

Verifies blender_addon/btp/frame.py round-trips, and that it is wire-compatible
with protocol/v1/frame.js in BOTH directions (Python frames -> JS reassembles,
JS frames -> Python reassembles). The realistic payload mirrors a BTP envelope:
a short possibly-non-ASCII metadata field plus a large ASCII base64 body that
crosses many chunk boundaries.

    python3 scripts/test_frame_python.py        (node must be on PATH for the
                                                 cross-language half)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "blender_addon", "btp"))

import frame as framing  # noqa: E402

CLI = os.path.join(HERE, "_frame_cli.mjs")

failures = 0


def check(name, cond):
    global failures
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}")
    if not cond:
        failures += 1


def reassemble_all(frames):
    r = framing.Reassembler()
    out = None
    for f in frames:
        e = r.accept(f)
        if e is not None:
            out = e
    return out


# Envelope-shaped payload: short non-ASCII metadata + large ASCII body that
# spans several 16 KB chunks.
big_body = ("QWxhZGRpbjpvcGVuIHNlc2FtZQ" * 9000)  # ~234 KB of base64-ish ASCII
PAYLOAD = {"id": "r1", "path": "/v1/textures/贴图 测试.png/data", "body_b64": big_body}


def main():
    s = json.dumps(PAYLOAD)
    frames = list(framing.frames("r1", s))

    print("[1] python self round-trip (multi-frame)")
    check("more than one frame", len(frames) > 1)
    check("reassembles to original", reassemble_all(frames) == PAYLOAD)

    print("[2] single-frame and raw-envelope passthrough")
    small = list(framing.frames("r2", json.dumps({"id": "r2", "ok": True})))
    check("single frame for small payload", len(small) == 1)
    check("single frame reassembles", reassemble_all(small) == {"id": "r2", "ok": True})
    raw = json.dumps({"id": "r3", "method": "GET", "path": "/v1/scene"})
    check("raw (un-framed) envelope passes through",
          framing.Reassembler().accept(raw) == {"id": "r3", "method": "GET", "path": "/v1/scene"})

    print("[3] out-of-order frame delivery still reassembles")
    r = framing.Reassembler()
    out = None
    for f in reversed(frames):
        e = r.accept(f)
        if e is not None:
            out = e
    check("reversed order reassembles", out == PAYLOAD)

    have_node = _have_node()
    if not have_node:
        print("[4/5] SKIP cross-language (node not found on PATH)")
    else:
        print("[4] python frames -> JS reassembles")
        js_out = _node(["reassemble"], json.dumps(frames))
        check("JS reassembled python frames to original", js_out == PAYLOAD)

        print("[5] JS frames -> python reassembles")
        js_frames = _node(["emit"], json.dumps({"id": "r1", "obj": PAYLOAD}))
        check("python reassembled JS frames to original", reassemble_all(js_frames) == PAYLOAD)

    print("\nALL OK" if failures == 0 else f"\n{failures} FAILURE(S)")
    sys.exit(1 if failures else 0)


def _have_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def _node(args, stdin_str):
    p = subprocess.run(["node", CLI, *args], input=stdin_str,
                       capture_output=True, text=True, check=True)
    return json.loads(p.stdout)


if __name__ == "__main__":
    main()
