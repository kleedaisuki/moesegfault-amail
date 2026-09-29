/** Validate the pinned stable Miniflare option shape before the costly Rust build. */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import { workerModuleRules } from "./worker-module-rules.mjs";

let outboundCalls = 0;
const here = path.dirname(fileURLToPath(import.meta.url));
const mf = new Miniflare({
  cf: false,
  workers: [{
    name: "amail-config-smoke",
    modules: true,
    scriptPath: path.join(here, "module-smoke.mjs"),
    modulesRules: workerModuleRules,
    // Stable v4's workerd supports dates only through 2026-08-06.
    compatibilityDate: "2026-08-06",
    d1Databases: ["MAIL_DB"],
    outboundService(request) {
      assert.equal(request.url, "https://fixture.invalid/ok");
      outboundCalls++;
      return new Response("ok");
    },
  }],
});

try {
  const response = await mf.dispatchFetch("http://synthetic.invalid/");
  assert.equal(await response.text(), "ok");
  assert.equal(outboundCalls, 1, "synthetic fetch must use the local egress handler");
  const { MAIL_DB: db } = await mf.getBindings();
  assert.equal(typeof db.prepare, "function");
} finally {
  await mf.dispose();
}
