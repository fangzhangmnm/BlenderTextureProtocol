# Blender Texture Protocol (BTP)

A Blender addon that exposes textures, selection, and (planned) mesh data
over an HTTP / WebRTC API, so external editors — desktop PWAs, tablet apps,
or your own scripts — can read and write Blender content without going
through `tmp_file.png` and a file manager.

**Status: v1.1 alpha** — both transports working. Localhost HTTP (same machine)
and cross-device WebRTC DataChannel (Blender-as-offerer, manual-paste pairing)
are verified end-to-end against a real Blender — handshake + a texture PUT round
trip. Same-machine access requires per-session consent (off at each Blender
launch; open it from the BTP panel). PIN/relay signaling and zero-paste reconnect
are on the roadmap (see `protocol/v1/README.md`).

## What it solves

The texture-painting loop in Blender today is friction-heavy: export PNG →
open in editor → save → re-import → reload UVs. BTP collapses that loop.
A PWA texture editor (or any local tool) calls a small HTTP API and the
change appears in Blender immediately, packed into the `.blend`.

Built as the shared backbone for sibling projects:
- **WebPaint** — Procreate-style PWA for iPad
- **AtlasMaker** — PureRef-like reference + atlas board for PC
- (future) **BodyPaint3D**-style 3D paint mode

## Install

1. Grab `dist/btp-X.Y.Z.zip` from a release, or build locally:
   ```bash
   python3 scripts/package.py
   ```
2. In Blender 4.2+ / 5.x:
   **Edit → Preferences → Extensions → Install from Disk** → pick the zip.
3. Enable the addon. The localhost HTTP server auto-starts on
   `http://127.0.0.1:18765` (port configurable in addon preferences).

## Quick check

```bash
curl http://127.0.0.1:18765/v1/scene
```
You should get JSON with the current `.blend` path and active object.

## For sibling integrators

The wire spec and JS client live in [`protocol/v1/`](./protocol/v1/).
Vendor the whole directory into your app (no `npm install`, no CDN) and import
only from `index.js`:

```js
import { BTPClient, connectRemote, ManualSignaling } from "./vendor/btp/v1/index.js";

// Same machine (PC) — localhost HTTP, zero setup:
const client   = new BTPClient();                     // default http://127.0.0.1:18765
const textures = await client.listTextures();
await client.putTextureData("T_Body", pngBlob);       // pixels packed into .blend

// Cross device (iPad) — WebRTC, paired once via Blender's N-panel:
const conn   = await connectRemote({ signaling: ManualSignaling({ offer, onAnswer }) });
const remote = new BTPClient({ baseUrl: "", fetch: conn.fetch });   // identical API
```

See [`protocol/v1/README.md`](./protocol/v1/README.md) for the endpoint table,
metadata fields, error codes, and forward-compatibility rules.

## v1 endpoints

```
GET    /v1/scene                          .blend filepath, units, active object
GET    /v1/textures                       list metadata
GET    /v1/textures/{name}                single metadata
GET    /v1/textures/{name}/data           raw bytes (image/png or source format)
PUT    /v1/textures/{name}/data           replace pixels (image/png, auto-packs)
POST   /v1/textures                       create (X-BTP-Name header + PNG body)
POST   /v1/textures/{name}/rename         { "new_name": "..." }
GET    /v1/selection                      currently-selected texture / object / mesh
POST   /v1/exec                           ad-hoc commands (server-registered, not version-protected)
```

`/v1/meshes`, `/v1/objects`, `/v1/materials`, `/v1/jobs` namespaces are
reserved for future additions inside v1 (no breaking change required).

## Repo layout

```
blender_addon/btp/      Blender addon (zip target)
protocol/v1/            Wire spec + JS client (what siblings vendor)
docs/                   Design notes and version-compat memos
fixtures/               PNG test fixtures
scripts/                Packager, debug bash scripts, Node smoke test
```

## Build & test

```bash
# Repackage the addon zip (reads version from manifest)
python3 scripts/package.py

# Integration tests against a live Blender (addon must be installed & enabled)
node scripts/smoke_test_btp_js.mjs

# Remote-transport tests (no Blender / browser needed — mock DataChannel):
node scripts/smoke_test_webrtc_transport.mjs   # client stack + framing end-to-end
python3 scripts/test_frame_python.py           # JS↔Python wire compatibility

# Convenience debug scripts (curl wrappers)
./scripts/debug/list.sh
./scripts/debug/put_checker.sh T_test
./scripts/debug/status.sh
```

If you're developing with Claude Code, `.claude/settings.local.json`
ships a `PostToolUse` hook that auto-repackages the zip on every addon
edit. Project-local; doesn't affect external contributors.

## Caveats

- **Image pixel undo** — Ctrl-Z on a PUT'd image works visually, but
  redo (Ctrl-Shift-Z) is unreliable. Blender's image data lives on a
  separate `ED_image_undo_*` stack that doesn't yet have a Python entry
  point. Workaround: don't rely on redo across BTP mutations. See
  [`docs/blender5-api-notes.md`](./docs/blender5-api-notes.md).
- **localhost binds `127.0.0.1`** — not exposed to LAN (a LAN port scan
  can't even see it). Cross-device access goes through the WebRTC transport,
  not by exposing the HTTP port. Why WebRTC even on a LAN: an HTTPS PWA may
  not `fetch http://<lan-ip>` (mixed content), so the texture editor can't
  hit a LAN HTTP server directly — the DataChannel is the way through. See
  `protocol/v1/README.md`.
- **Same machine, cross-origin OK** — CORS headers are sent; HTTPS PWAs
  on github.io / Vercel / etc. can `fetch()` `http://127.0.0.1:18765`
  because browsers whitelist localhost as a secure context.

## Versioning

- **Addon** (`btp X.Y.Z` in `blender_manifest.toml`) — incremented per
  shipped change.
- **Wire protocol** (`/v1/` URL prefix) — `/v1/*` endpoints are stable
  within v1.x. Breaking changes spawn a parallel `protocol/v2/` directory.
- **Bundle** (`BUNDLE_VERSION` in `btp.js`) — tracks the spec + client
  pair. Bumps only on protocol-semantic or documented-client-API changes;
  internal refactors / bug fixes do not bump.

## License

MIT — see addon manifest.

## Acknowledgments

Initial development co-authored with Claude (Anthropic). Built as part of
a family of texture-painting tools designed to remove friction from the
Blender → editor → Blender loop.
