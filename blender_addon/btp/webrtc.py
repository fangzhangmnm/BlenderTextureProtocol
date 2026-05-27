"""
WebRTC DataChannel transport for BTP.

Signaling pattern: **browser-as-offerer** (browsers can't accept inbound
connections; aiortc on Blender side answers).

1. Browser:  `pc = new RTCPeerConnection(); pc.createDataChannel("btp");
              offer = await pc.createOffer(); await pc.setLocalDescription(offer);`
              (wait for ICE gather complete; non-trickle SDP)
2. Blender:  client `POST /v1/exec`:
              `{ "command": "webrtc.set_remote_offer", "params": { "sdp": "v=0\\r\\n..." } }`
              returns `{ "answer_sdp": "v=0\\r\\n..." }` after our ICE gather.
3. Browser:  `await pc.setRemoteDescription({ type:"answer", sdp: answer_sdp });`
4. DataChannel opens. Browser sends JSON envelopes (see frame format below);
   Blender dispatches each envelope to `api.handle(...)` on the main thread
   (same code path used by the HTTP server), sends JSON response.

Frame format (sender → server):
    { "id": "<client-chosen>",
      "method": "GET" | "PUT" | "POST" | "DELETE",
      "path": "/v1/textures/T_body/data",
      "headers": { ... },             // optional
      "body_b64": "<base64 PNG>" }    // optional

Frame format (server → sender):
    { "id": "<echoed>",
      "status": 200,
      "headers": { ... },
      "body_b64": "<base64 body or null>" }

Single PeerConnection at a time in v0.2 (multi-client deferred).
"""
import asyncio
import base64
import json
import threading
from typing import Optional, TYPE_CHECKING

from . import api, bridge, sdp_envelope

# aiortc + its 13 wheels are heavy. Import lazily inside _handle_offer
# so pure-HTTP users (AtlasMaker) never pay the cold-start cost.
# Subsequent WebRTC calls reuse the already-imported module.
if TYPE_CHECKING:
    from aiortc import RTCPeerConnection


_loop: Optional[asyncio.AbstractEventLoop] = None
_loop_thread: Optional[threading.Thread] = None
_pc: Optional["RTCPeerConnection"] = None


# ─── Event loop in a background thread ───

def _ensure_loop() -> None:
    global _loop, _loop_thread
    if _loop is not None and _loop.is_running():
        return
    _loop = asyncio.new_event_loop()

    def run():
        asyncio.set_event_loop(_loop)
        _loop.run_forever()

    _loop_thread = threading.Thread(target=run, daemon=True, name="BTP-WebRTC")
    _loop_thread.start()


def _run(coro, timeout: float = 30.0):
    """Block the caller while running `coro` on the WebRTC event loop."""
    _ensure_loop()
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    return fut.result(timeout=timeout)


# ─── Exec commands (signaling + control) ───

def cmd_set_remote_offer(params):
    """PWA-as-offerer path (used by demo/webrtc-test.html via /v1/exec).
    Accept a browser-side offer SDP (raw or BTP1 envelope); return our
    answer SDP both raw and as a BTP1 envelope."""
    sdp_in = params.get("sdp")
    if not sdp_in:
        raise ValueError("missing 'sdp' in params")
    try:
        offer_sdp = sdp_envelope.decode(sdp_in)
    except ValueError as e:
        raise ValueError(f"could not decode offer SDP: {e}")
    answer_sdp = _run(_handle_offer(offer_sdp), timeout=15.0)
    return {
        "answer_sdp": answer_sdp,
        "answer_envelope": sdp_envelope.encode(answer_sdp),
    }


def cmd_create_offer(params):
    """Blender-as-offerer path (used by N-panel manual paste flow).
    Generate an offer SDP, hold the PC open waiting for the remote answer."""
    offer_sdp = _run(_create_offer(), timeout=15.0)
    return {
        "offer_sdp": offer_sdp,
        "offer_envelope": sdp_envelope.encode(offer_sdp),
    }


def cmd_set_remote_answer(params):
    """Blender-as-offerer path: accept the PWA's answer SDP (raw or BTP1
    envelope) and apply it. DataChannel opens shortly after via DC.on('open')."""
    sdp_in = params.get("sdp")
    if not sdp_in:
        raise ValueError("missing 'sdp' in params")
    try:
        answer_sdp = sdp_envelope.decode(sdp_in)
    except ValueError as e:
        raise ValueError(f"could not decode answer SDP: {e}")
    _run(_set_remote_answer(answer_sdp), timeout=10.0)
    return {"ok": True}


def cmd_close(params):
    """Close the current PeerConnection if any."""
    global _pc
    if _pc is None:
        return {"closed": False, "reason": "no active peer connection"}
    _run(_pc.close(), timeout=5.0)
    _pc = None
    return {"closed": True}


def cmd_status(params):
    """Snapshot of current connection state."""
    if _pc is None:
        return {"state": "idle"}
    return {
        "state": _pc.connectionState,
        "signaling": _pc.signalingState,
        "ice": _pc.iceConnectionState,
    }


# ─── PeerConnection wiring ───

async def _create_offer() -> str:
    """Blender-as-offerer. Closes any existing PC, creates a fresh one with
    a DataChannel, generates an offer, gathers ICE. Returns offer SDP."""
    # Lazy import — same reason as _handle_offer below.
    from aiortc import RTCPeerConnection

    global _pc
    if _pc is not None:
        try:
            await _pc.close()
        except Exception:
            pass
        _pc = None

    pc = RTCPeerConnection()
    _pc = pc

    # DC must be created BEFORE createOffer so the SDP advertises an
    # application m-line for the data channel.
    dc = pc.createDataChannel("btp")
    _attach_channel(dc)

    @pc.on("connectionstatechange")
    def on_connectionstatechange():
        print(f"[BTP webrtc] connection: {pc.connectionState}", flush=True)

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.05)

    return pc.localDescription.sdp


async def _set_remote_answer(sdp: str) -> None:
    """Blender-as-offerer: apply the remote PWA's answer SDP."""
    from aiortc import RTCSessionDescription

    if _pc is None:
        raise RuntimeError(
            "No pending offer. Click 'Open for another device' to start a session first."
        )
    answer = RTCSessionDescription(sdp=sdp, type="answer")
    await _pc.setRemoteDescription(answer)


async def _handle_offer(sdp: str) -> str:
    # Lazy import: aiortc + all 13 wheels only load on first WebRTC use.
    from aiortc import RTCPeerConnection, RTCSessionDescription

    global _pc
    if _pc is not None:
        try:
            await _pc.close()
        except Exception:
            pass
        _pc = None

    pc = RTCPeerConnection()
    _pc = pc

    @pc.on("datachannel")
    def on_datachannel(channel):
        _attach_channel(channel)

    @pc.on("connectionstatechange")
    def on_connectionstatechange():
        print(f"[BTP webrtc] connection: {pc.connectionState}", flush=True)

    offer = RTCSessionDescription(sdp=sdp, type="offer")
    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    # Non-trickle: wait for ICE gathering to finish before returning SDP.
    while pc.iceGatheringState != "complete":
        await asyncio.sleep(0.05)

    return pc.localDescription.sdp


def _attach_channel(channel) -> None:
    print(f"[BTP webrtc] datachannel open: label={channel.label}", flush=True)

    @channel.on("message")
    def on_message(msg):
        # Sync handler. Runs on the loop thread; bridge.dispatch_to_main
        # blocks here until Blender's main thread services the request.
        # Single-client sequential is OK in v0.2.
        _handle_envelope(channel, msg)

    @channel.on("close")
    def on_close():
        print(f"[BTP webrtc] datachannel closed: label={channel.label}", flush=True)


def _handle_envelope(channel, msg) -> None:
    req_id = None
    try:
        if isinstance(msg, bytes):
            msg = msg.decode("utf-8")
        req = json.loads(msg)
        req_id = req.get("id")
        method = req.get("method", "GET")
        path = req.get("path", "/")
        body_b64 = req.get("body_b64")
        body = base64.b64decode(body_b64) if body_b64 else None
        headers = req.get("headers") or {}
    except Exception as e:
        _send(channel, {
            "id": req_id, "status": 400,
            "headers": {"Content-Type": "application/json"},
            "body_b64": _b64_json({"error": {
                "code": "bad_envelope", "message": str(e)}}),
        })
        return

    try:
        status, resp_headers, resp_body = bridge.dispatch_to_main(
            api.handle, method, path, body, headers)
    except Exception as e:
        _send(channel, {
            "id": req_id, "status": 500,
            "headers": {"Content-Type": "application/json"},
            "body_b64": _b64_json({"error": {
                "code": "dispatch_failed", "message": str(e)}}),
        })
        return

    _send(channel, {
        "id": req_id,
        "status": status,
        "headers": resp_headers,
        "body_b64": base64.b64encode(resp_body).decode() if resp_body else None,
    })


def _send(channel, response: dict) -> None:
    try:
        channel.send(json.dumps(response))
    except Exception as e:
        print(f"[BTP webrtc] channel.send failed: {e}", flush=True)


def _b64_json(obj) -> str:
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode()


# ─── Lifecycle (called by __init__.py) ───

def register() -> None:
    api.register_exec("webrtc.create_offer", cmd_create_offer)
    api.register_exec("webrtc.set_remote_answer", cmd_set_remote_answer)
    api.register_exec("webrtc.set_remote_offer", cmd_set_remote_offer)
    api.register_exec("webrtc.close", cmd_close)
    api.register_exec("webrtc.status", cmd_status)


def unregister() -> None:
    global _pc, _loop, _loop_thread
    if _pc is not None:
        try:
            _run(_pc.close(), timeout=5.0)
        except Exception:
            pass
        _pc = None
    if _loop is not None:
        try:
            _loop.call_soon_threadsafe(_loop.stop)
        except Exception:
            pass
        if _loop_thread is not None:
            _loop_thread.join(timeout=5.0)
        _loop = None
        _loop_thread = None
