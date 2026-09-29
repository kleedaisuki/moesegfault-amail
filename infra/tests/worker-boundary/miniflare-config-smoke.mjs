/** Validate the pinned Miniflare v5 option shape before the costly Rust build. */
import assert from "node:assert/strict";
import { Miniflare } from "miniflare";

const mf = new Miniflare({
  cf: false,
  workers: [{
    name: "amail-config-smoke",
    modules: true,
    script: 'export default { fetch() { return new Response("ok") } }',
    compatibilityDate: "2026-09-25",
    d1Databases: ["MAIL_DB"],
    outboundService() {
      throw new Error("config smoke forbids outbound requests");
    },
  }],
});

try {
  const response = await mf.dispatchFetch("http://synthetic.invalid/");
  assert.equal(await response.text(), "ok");
  const { MAIL_DB: db } = await mf.getBindings();
  assert.equal(typeof db.prepare, "function");
} finally {
  await mf.dispose();
}
