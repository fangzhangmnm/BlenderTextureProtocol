// Node smoke test for protocol/v1/btp.js
// Hits the live Blender server (must be running with HTTP toggle on).
//   node scripts/smoke_test_btp_js.mjs

import { readFile } from "node:fs/promises";
import { BTPClient, BTPError, BUNDLE_VERSION, PROTOCOL } from "../protocol/v1/btp.js";

const FIXTURE = new URL("../fixtures/checker_512.png", import.meta.url);

async function main() {
  console.log(`bundle ${BUNDLE_VERSION}, wire ${PROTOCOL}`);
  const client = new BTPClient();

  console.log("\n[1] getScene");
  console.log(await client.getScene());

  console.log("\n[2] listTextures");
  const before = await client.listTextures();
  console.log(`  ${before.length} textures: ${before.map(t => t.name).join(", ")}`);

  console.log("\n[3] createTexture T_smoke");
  if (before.find(t => t.name === "T_smoke")) {
    console.log("  exists already, skipping create");
  } else {
    const png = await readFile(FIXTURE);
    const meta = await client.createTexture("T_smoke", png);
    console.log(`  ${meta.name} ${meta.width}x${meta.height} packed=${meta.packed}`);
  }

  console.log("\n[4] getTextureData round-trip");
  const blob = await client.getTextureData("T_smoke");
  const got = new Uint8Array(await blob.arrayBuffer());
  const expected = await readFile(FIXTURE);
  if (got.length !== expected.length) {
    throw new Error(`size mismatch: ${got.length} vs ${expected.length}`);
  }
  let same = true;
  for (let i = 0; i < got.length; i++) if (got[i] !== expected[i]) { same = false; break; }
  console.log(`  ${got.length} bytes, identical=${same}`);

  console.log("\n[5] renameTexture T_smoke -> T_smoke_renamed");
  await client.renameTexture("T_smoke", "T_smoke_renamed");
  await client.renameTexture("T_smoke_renamed", "T_smoke");
  console.log("  rename back and forth OK");

  console.log("\n[6] getSelection");
  console.log(" ", await client.getSelection());

  console.log("\n[7] exec unknown -> BTPError");
  try {
    await client.exec("definitely_not_registered");
    throw new Error("expected error");
  } catch (e) {
    if (e instanceof BTPError && e.code === "unknown_command") {
      console.log("  caught BTPError code=unknown_command status=" + e.status);
    } else {
      throw e;
    }
  }

  console.log("\n[8] not-found -> BTPError");
  try {
    await client.getTextureMetadata("__no_such_image__");
    throw new Error("expected error");
  } catch (e) {
    if (e instanceof BTPError && e.code === "texture_not_found") {
      console.log("  caught BTPError code=texture_not_found status=" + e.status);
    } else {
      throw e;
    }
  }

  console.log("\nALL OK");
}

main().catch(e => {
  console.error("FAIL:", e);
  process.exit(1);
});
