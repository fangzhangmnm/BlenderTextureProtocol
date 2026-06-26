// Static end-to-end test for the BTP remote transport (no browser, no Blender).
//
//   node scripts/smoke_test_webrtc_transport.mjs
//
// It wires a mock DataChannel pair and a JS stub of Blender's envelope
// handler (mirroring blender_addon/btp/webrtc.py's framing) to the real
// client stack: BTPClient → channelFetch → frame.js → wire → stub server →
// frame.js → channelFetch → Response → BTPClient.
//
// Covers what is testable without real WebRTC/ICE: envelope framing, the
// fetch-shim, base64 body round-trip, MULTI-FRAME chunking of large bodies
// in BOTH directions (the part that breaks a naive single-send transport),
// and error→BTPError mapping. The only thing left for a real device is the
// ICE handshake itself.

import { BTPClient, BTPError } from "../protocol/v1/btp.js";
import { channelFetch } from "../protocol/v1/webrtc-fetch.js";
import { frame, Reassembler } from "../protocol/v1/frame.js";

let failures = 0;
function check(name, cond) {
  console.log(`  ${cond ? "ok  " : "FAIL"}  ${name}`);
  if (!cond) failures++;
}

// ─── mock DataChannel pair ───

class MockChannel {
  constructor(label) {
    this.label = label;
    this.readyState = "open";
    this.binaryType = "arraybuffer";
    this.peer = null;
    this.sentCount = 0;
    this._listeners = { message: [], close: [], open: [] };
  }
  addEventListener(type, fn) { this._listeners[type].push(fn); }
  removeEventListener(type, fn) {
    this._listeners[type] = this._listeners[type].filter((f) => f !== fn);
  }
  send(data) {
    this.sentCount++;
    // async delivery, preserve order
    queueMicrotask(() => {
      for (const fn of this.peer._listeners.message) fn({ data });
    });
  }
  close() {
    this.readyState = "closed";
    for (const fn of this._listeners.close) fn({});
  }
}

function makePair() {
  const a = new MockChannel("btp");
  const b = new MockChannel("btp");
  a.peer = b;
  b.peer = a;
  return [a, b];
}

// ─── stub Blender server (mirror of webrtc.py _attach_channel/_handle_envelope) ───

const BIG = new Uint8Array(1_500_000);
for (let i = 0; i < BIG.length; i++) BIG[i] = (i * 31 + 7) & 0xff;

let lastPutBody = null; // captured to assert request round-trip

function stubHandle(method, path, body /* Uint8Array|null */) {
  const json = (obj, status = 200) => ({
    status,
    headers: { "Content-Type": "application/json; charset=utf-8" },
    body: new TextEncoder().encode(JSON.stringify(obj)),
  });
  if (method === "GET" && path === "/v1/scene") {
    return json({ blend_filepath: "D:/x.blend", unit: "METRIC", active_object_name: "Cube" });
  }
  if (method === "GET" && path === "/v1/textures") {
    return json([{ name: "T_Body", width: 2048, height: 2048 }]);
  }
  if (method === "GET" && path === "/v1/textures/BIG/data") {
    return { status: 200, headers: { "Content-Type": "image/png" }, body: BIG };
  }
  if (method === "PUT" && path === "/v1/textures/T/data") {
    lastPutBody = body;
    return json({ name: "T", width: 64, height: 64, packed: true });
  }
  return json({ error: { code: "texture_not_found", message: `no ${path}` } }, 404);
}

function attachStubServer(channel) {
  const reasm = new Reassembler();
  const b64ToBytes = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const bytesToB64 = (bytes) => {
    let bin = "";
    for (let i = 0; i < bytes.length; i += 0x8000) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    }
    return btoa(bin);
  };
  channel.addEventListener("message", (ev) => {
    const req = reasm.accept(ev.data);
    if (!req) return; // mid-message
    const body = req.body_b64 ? b64ToBytes(req.body_b64) : null;
    const res = stubHandle(req.method, req.path, body);
    const env = {
      id: req.id,
      status: res.status,
      headers: res.headers,
      body_b64: res.body ? bytesToB64(res.body) : null,
    };
    for (const f of frame(req.id, JSON.stringify(env))) channel.send(f);
  });
}

// ─── run ───

function eqBytes(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

async function main() {
  const [clientChan, serverChan] = makePair();
  attachStubServer(serverChan);
  const client = new BTPClient({ baseUrl: "", fetch: channelFetch(clientChan) });

  console.log("[1] getScene (single frame)");
  const scene = await client.getScene();
  check("blend_filepath round-trips", scene.blend_filepath === "D:/x.blend");

  console.log("[2] listTextures");
  const list = await client.listTextures();
  check("array of 1", Array.isArray(list) && list.length === 1 && list[0].name === "T_Body");

  console.log("[3] PUT 1.5 MB body (multi-frame request)");
  clientChan.sentCount = 0;
  const meta = await client.putTextureData("T", BIG);
  check("server got byte-identical body", lastPutBody && eqBytes(lastPutBody, BIG));
  check("request was chunked (>1 frame)", clientChan.sentCount > 1);
  check("response metadata parsed", meta.name === "T" && meta.packed === true);

  console.log("[4] GET 1.5 MB body (multi-frame response)");
  serverChan.sentCount = 0;
  const blob = await client.getTextureData("BIG");
  const got = new Uint8Array(await blob.arrayBuffer());
  check("client got byte-identical body", eqBytes(got, BIG));
  check("response was chunked (>1 frame)", serverChan.sentCount > 1);

  console.log("[5] 404 → BTPError");
  let threw = null;
  try {
    await client.getTextureMetadata("__nope__");
  } catch (e) {
    threw = e;
  }
  check("BTPError with code texture_not_found",
    threw instanceof BTPError && threw.code === "texture_not_found" && threw.status === 404);

  console.log(failures === 0 ? "\nALL OK" : `\n${failures} FAILURE(S)`);
  if (failures) process.exit(1);
}

main().catch((e) => { console.error("FAIL:", e); process.exit(1); });
