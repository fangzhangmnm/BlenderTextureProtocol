// Helper for the cross-language framing test (scripts/test_frame_python.py).
// Bridges frame.js to the command line so Python can check wire compatibility.
//
//   echo '{"id":"x","obj":{...}}' | node _frame_cli.mjs emit        -> prints ["<frame>", ...]
//   echo '["<frame>", ...]'       | node _frame_cli.mjs reassemble  -> prints the reassembled obj
import { frame, Reassembler } from "../protocol/v1/frame.js";

const mode = process.argv[2];
let input = "";
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  if (mode === "emit") {
    const { id, obj } = JSON.parse(input);
    process.stdout.write(JSON.stringify(frame(id, JSON.stringify(obj))));
  } else if (mode === "reassemble") {
    const frames = JSON.parse(input);
    const r = new Reassembler();
    let out = null;
    for (const f of frames) { const e = r.accept(f); if (e) out = e; }
    process.stdout.write(JSON.stringify(out));
  } else {
    process.stderr.write(`unknown mode: ${mode}\n`);
    process.exit(2);
  }
});
