// SDP envelope: BTP1:<gzip+base64url> single-line format.
// Mirror of blender_addon/btp/sdp_envelope.py. Keep them in lockstep.

export const ENVELOPE_PREFIX = "BTP1:";

export async function encodeSDP(sdp) {
  const input = new TextEncoder().encode(sdp);
  const cs = new CompressionStream("gzip");
  const writer = cs.writable.getWriter();
  writer.write(input);
  writer.close();
  const gz = new Uint8Array(await new Response(cs.readable).arrayBuffer());
  let b64 = btoa(String.fromCharCode(...gz));
  b64 = b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return ENVELOPE_PREFIX + b64;
}

export async function decodeSDP(envelope) {
  const s = envelope.trim();
  if (s.startsWith("v=0")) return s;
  if (!s.startsWith(ENVELOPE_PREFIX)) {
    throw new Error(`Unrecognized SDP envelope. Expected '${ENVELOPE_PREFIX}...' or raw SDP starting with 'v=0'.`);
  }
  let b64 = s.slice(ENVELOPE_PREFIX.length);
  b64 = b64.replace(/-/g, "+").replace(/_/g, "/");
  while (b64.length % 4) b64 += "=";
  const gz = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const ds = new DecompressionStream("gzip");
  const writer = ds.writable.getWriter();
  writer.write(gz);
  writer.close();
  return new TextDecoder().decode(await new Response(ds.readable).arrayBuffer());
}

export function isEnvelope(s) {
  return s.trim().startsWith(ENVELOPE_PREFIX);
}
