/** Validate the pinned stable Miniflare option shape before the costly Rust build. */
import assert from "node:assert/strict";
import { Miniflare } from "miniflare";

let outboundCalls = 0;
const mf = new Miniflare({
  cf: false,
  workers: [{
    name: "amail-config-smoke",
    modules: true,
    script: 'export default { fetch() { return fetch("https://fixture.invalid/") } }',
    compatibilityDate: "2026-09-25",
    d1Databases: ["MAIL_DB"],
    outboundService(request) {
      assert.equal(request.url, "https://fixture.invalid/");
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
