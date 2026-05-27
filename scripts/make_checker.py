#!/usr/bin/env python3
"""Generate a checkerboard PNG fixture for testing PUT /textures/*/data.

Stdlib only — no PIL / numpy. Writes RGBA8 PNG.
"""
import struct
import sys
import zlib
from pathlib import Path


def make_checker(size: int = 512, cells: int = 8, color_a=(255, 0, 128, 255), color_b=(32, 32, 32, 255)) -> bytes:
    cell = size // cells
    rows = []
    for y in range(size):
        row = bytearray([0])  # PNG filter byte = 0 (None)
        for x in range(size):
            on = ((x // cell) + (y // cell)) % 2 == 0
            row.extend(color_a if on else color_b)
        rows.append(bytes(row))
    raw = b"".join(rows)
    idat = zlib.compress(raw, 6)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data)
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", idat)
    png += chunk(b"IEND", b"")
    return png


def main() -> int:
    out_dir = Path(__file__).resolve().parent.parent / "fixtures"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "checker_512.png"
    out.write_bytes(make_checker(512, 8))
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
