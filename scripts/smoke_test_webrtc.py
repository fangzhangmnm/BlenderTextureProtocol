#!/usr/bin/env python3
"""End-to-end smoke test for BTP WebRTC DataChannel transport.

Requires aiortc on the test machine's Python (separate from vendored
copy in the addon, since vendor wheels target Windows). Either:
  python3 -m venv /tmp/btp-test-venv
  /tmp/btp-test-venv/bin/pip install aiortc
  /tmp/btp-test-venv/bin/python3 scripts/smoke_test_webrtc.py

or just use `/tmp/venv-test` if vendor.py was run earlier in this session.

Steps:
  1. Create a PeerConnection + DataChannel
  2. Generate offer SDP, wait for ICE gather complete
  3. POST to BTP /v1/exec webrtc.set_remote_offer, receive answer SDP
  4. Apply answer; wait for DataChannel open
  5. Send a JSON envelope: GET /v1/textures
  6. Validate response, compare against HTTP path's response
  7. Close
"""
import asyncio
import base64
import json
import sys
import urllib.request

from aiortc import RTCPeerConnection, RTCSessionDescription


BTP_BASE = "http://127.0.0.1:18765"


def http_post_json(url, body, timeout=30):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def http_get_json(url, timeout=10):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read())


async def wait_gather(pc):
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.05)


async def main():
    print("=== BTP WebRTC smoke test ===")

    # Sanity check: HTTP path alive (we'll compare results)
    http_textures = http_get_json(f"{BTP_BASE}/v1/textures")
    http_names = sorted(t["name"] for t in http_textures)
    print(f"[0] HTTP /v1/textures: {http_names}")

    # 1. PeerConnection + DataChannel
    pc = RTCPeerConnection()
    dc = pc.createDataChannel("btp")

    opened = asyncio.Event()
    response_q: asyncio.Queue = asyncio.Queue()

    @dc.on("open")
    def on_open():
        opened.set()

    @dc.on("message")
    def on_message(msg):
        response_q.put_nowait(msg)

    # 2. Generate offer
    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    await wait_gather(pc)
    print(f"[1] offer SDP gathered ({len(pc.localDescription.sdp)} bytes)")

    # 3. Send to Blender via /v1/exec
    print("[2] POST /v1/exec webrtc.set_remote_offer ...")
    resp = http_post_json(f"{BTP_BASE}/v1/exec", {
        "command": "webrtc.set_remote_offer",
        "params": {"sdp": pc.localDescription.sdp},
    })
    answer_sdp = resp["answer_sdp"]
    print(f"  got answer SDP ({len(answer_sdp)} bytes)")

    # 4. Apply answer, wait for DC open
    await pc.setRemoteDescription(RTCSessionDescription(sdp=answer_sdp, type="answer"))
    print("[3] waiting for DataChannel open ...")
    await asyncio.wait_for(opened.wait(), timeout=10.0)
    print(f"  DC open, state={dc.readyState}")

    # 5. Send envelope: GET /v1/textures over DataChannel
    envelope = {"id": "test-1", "method": "GET", "path": "/v1/textures"}
    dc.send(json.dumps(envelope))
    print("[4] sent envelope GET /v1/textures")

    raw = await asyncio.wait_for(response_q.get(), timeout=10.0)
    response = json.loads(raw)
    print(f"[5] response status={response['status']}, id={response.get('id')}")

    assert response["status"] == 200, f"bad status {response['status']}"
    assert response.get("id") == "test-1", "id mismatch"

    body = json.loads(base64.b64decode(response["body_b64"]))
    dc_names = sorted(t["name"] for t in body)
    print(f"  textures via DC: {dc_names}")
    assert dc_names == http_names, f"HTTP vs DC mismatch: {http_names} vs {dc_names}"
    print("[6] HTTP and DC return identical /v1/textures content ✓")

    # 6. Get specific texture bytes via DC, compare to HTTP
    if dc_names:
        sample = dc_names[0]
        envelope = {"id": "test-2", "method": "GET",
                    "path": f"/v1/textures/{sample}/data"}
        dc.send(json.dumps(envelope))
        raw = await asyncio.wait_for(response_q.get(), timeout=10.0)
        response = json.loads(raw)
        dc_bytes = base64.b64decode(response["body_b64"])
        print(f"[7] GET /v1/textures/{sample}/data via DC: {len(dc_bytes)} bytes")

        # Compare to HTTP fetch
        with urllib.request.urlopen(f"{BTP_BASE}/v1/textures/{sample}/data") as r:
            http_bytes = r.read()
        assert dc_bytes == http_bytes, "byte mismatch HTTP vs DC"
        print(f"  byte-identical to HTTP fetch ✓")

    await pc.close()
    print("\nALL OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"\nFAIL: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
