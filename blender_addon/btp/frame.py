"""
BTP DataChannel framing (Blender side). Byte-compatible mirror of
protocol/v1/frame.js — keep the two in sync.

A logical envelope (request or response) is split into chunk frames so large
bodies survive the DataChannel max-message-size. Wire frame is JSON text:

    { "id", "i", "n", "p" }   (i=chunk index, n=count, p=slice of envelope JSON)

No bpy import here on purpose, so it is unit-testable outside Blender
(see scripts/test_frame_python.py).
"""
import json
import math

# 16 KB per chunk — matches frame.js CHUNK_SIZE.
CHUNK_SIZE = 16384


def frames(msg_id, s):
    """Yield wire-frame JSON strings for a serialized envelope `s`."""
    n = max(1, math.ceil(len(s) / CHUNK_SIZE))
    for i in range(n):
        yield json.dumps({
            "id": msg_id,
            "i": i,
            "n": n,
            "p": s[i * CHUNK_SIZE:(i + 1) * CHUNK_SIZE],
        })


class Reassembler:
    """Reassembles inbound frames into envelopes. One per channel."""

    def __init__(self):
        self._partial = {}  # id -> {parts, got, n}

    def accept(self, raw):
        """Feed one DataChannel message. Returns the reassembled envelope dict
        when the last frame arrives, else None."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        f = json.loads(raw)

        # Raw (un-framed) envelope — backward compat.
        if "n" not in f or "p" not in f:
            return f

        if f["n"] == 1:
            return json.loads(f["p"])

        entry = self._partial.get(f["id"])
        if entry is None:
            entry = {"parts": [None] * f["n"], "got": 0, "n": f["n"]}
            self._partial[f["id"]] = entry
        if entry["parts"][f["i"]] is None:
            entry["parts"][f["i"]] = f["p"]
            entry["got"] += 1
        if entry["got"] == entry["n"]:
            del self._partial[f["id"]]
            return json.loads("".join(entry["parts"]))
        return None
