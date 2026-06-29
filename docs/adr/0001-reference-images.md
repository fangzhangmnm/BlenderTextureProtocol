---
created: 20260626
status: accepted
---

# Reference images are a placement resource, decoupled from texture pixels

Clients (WebPaint, AtlasMaker) want to "send an image to Blender as a modeling
reference, creating it if absent and updating it if present." We model a
reference as a **metadata-only placement object** addressed by name
(`/v1/references/{name}`) that *links to a texture by name* — the pixels live in
`/v1/textures` and are sent separately, exactly like any other texture. A
reference carries no pixels of its own; it is `{ image: "<texture-name>",
placement, opacity }`. The Blender side realises it as an Image Empty tagged
`btp_ref=<name>` so BTP can find-and-update its own references without scanning
or clobbering the user's namespace.

## Decisions

- **Pixels vs placement are separate resources.** `/v1/textures` owns pixels
  (one source of truth). A reference is a *role/placement* over an existing
  texture. A future camera-background or image-plane endpoint reuses the same
  texture with no pixel duplication and no new pixel transport.
- **Upsert by name (idempotent `PUT /v1/references/{name}`).** Create if absent,
  update if present. Matches "send to create (update if exists)". Name-as-id,
  overwrite, no conflict resolution — consistent with the texture stance, but
  deliberately *different* from textures' POST-creates / PUT-requires-exists: a
  reference is desired-state you push idempotently. On update we relink the
  image, re-read its aspect, and re-normalise.
- **Two client UX intents, one mental model.** "仅发送贴图" = `PUT/POST
  /v1/textures` only. "发送并作为参考图" = send the texture, then
  `PUT /v1/references`. The reference call never carries pixels.
- **Normalise the placed image to longest-edge = 1 Blender unit** (see below).
- **Additive within `/v1`.** New endpoints only; no field re-meaning. Client
  bumps `BUNDLE_VERSION` (documented API addition), old clients unaffected.

## Considered options — size normalisation

Longest-edge = 1 vs total-area = 1 for the placed image's extent.

**Chosen: longest-edge = 1.** Reasons, strongest first:

1. **Bounded, predictable extent.** Every reference fits a 1×1 box for any
   aspect (4:1 → 1.0×0.25; square → 1×1). Area=1 leaves the longest edge
   *unbounded* — a 10:1 panorama becomes ~3.16 units and can dwarf the model. A
   reference is a fit-by-eye placement aid; a consistent bounded max is more
   intuitive.
2. **Maps to Blender's native knob.** An Image Empty is sized by a single scalar
   (`empty_display_size`) with aspect taken from the linked image. Longest-edge=1
   *is* that scalar — set it to 1, done. Area=1 forces `size = 1/√aspect` on
   every change, fighting the native model.
3. **Stable under idempotent update.** Longest-edge=1 keeps `display_size = 1`
   across re-uploads; the aspect just follows the new image — no recompute, no
   visible jump. Area=1 must resize on every aspect change to hold area constant
   — the wrong kind of surprise for an idempotent upsert.

## Consequences

- `placement` is an extensible object, minimal to start: `{ mode: "view", view:
  "front|back|left|right|top|bottom|camera" }` (axis-aligned, the 90% modeling
  case) or `{ mode: "transform", location/rotation/scale }`. Unknown fields are
  ignored (forward-compat per the `/v1` rule).
- Implementation (addon Python + `protocol/v1` client + spec + `BUNDLE_VERSION`
  bump) is **not** done yet — this ADR records the agreed shape so the protocol
  bump is ratified before code. Strict-versioning escalation still applies.
- We ship `/v1/references` specifically rather than a general
  `/v1/image-placements?kind=` — YAGNI on the umbrella resource; the real
  foresight is the pixels/placement split, which lets camera backgrounds or
  textured planes be added later without breaking `/v1`.
