"""SDP envelope: BTP1:<gzip+base64url> single-line format.

Compresses a ~1.3 KB SDP into ~800 chars so it fits comfortably in a
single clipboard paste / messenger line. Accepts raw SDP (v=0...) on the
input side so old PWA clients keep working during migration.

Format: `BTP1:` prefix + URL-safe base64 (no padding) of gzipped SDP UTF-8 bytes.
"""
import base64
import gzip


ENVELOPE_PREFIX = "BTP1:"


def encode(sdp: str) -> str:
    gz = gzip.compress(sdp.encode("utf-8"), compresslevel=9)
    b64 = base64.urlsafe_b64encode(gz).decode("ascii").rstrip("=")
    return ENVELOPE_PREFIX + b64


def decode(envelope: str) -> str:
    """Accept either a BTP1 envelope or raw SDP (v=0...). Returns raw SDP."""
    s = envelope.strip()
    if s.startswith("v=0"):
        return s
    if not s.startswith(ENVELOPE_PREFIX):
        raise ValueError(
            f"Unrecognized SDP envelope. Expected '{ENVELOPE_PREFIX}...' "
            f"or raw SDP starting with 'v=0'."
        )
    payload = s[len(ENVELOPE_PREFIX):]
    padded = payload + "=" * (-len(payload) % 4)
    gz = base64.urlsafe_b64decode(padded)
    return gzip.decompress(gz).decode("utf-8")


def is_envelope(s: str) -> bool:
    return s.strip().startswith(ENVELOPE_PREFIX)
