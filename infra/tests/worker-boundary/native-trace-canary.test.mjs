/** Hosted native Rust canary isolation checks; old workerd is not new-API acceptance. */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const scriptPath = path.join(root, "workers/native-trace-canary/build/worker/shim.mjs");
const run = "0123456789abcdef0123456789abcdef";
/** Exercise real native service dispatch while denying every external fetch. */
function options(role) {
  return { name: role, modules: true, scriptPath, modulesRoot: root,
    modulesRules: workerModuleRules, compatibilityDate: "2026-07-30",
    bindings: { CANARY_ROLE: role, PROBE_ID: run },
    outboundService() { throw new Error("infrastructure canary must not use external data/capabilities"); } };
}

test("compiled Rust caller constructs four synthetic requests without forwarding input", async () => {
  const received = [];
  const caller = options("caller");
  const mf = new Miniflare({ cf: false, workers: [
    { ...caller, serviceBindings: { PROBE: async request => {
      const body = await request.text();
      received.push({ url: request.url, body, headers: [...request.headers], method: request.method });
      return Response.json({ available: true, synthetic: true });
    } } },
  ] });
  try {
    const marker = "SYNTHETIC_USER_DATA_MUST_NOT_FORWARD";
    const response = await mf.dispatchFetch(`https://synthetic.invalid/${marker}?query=${marker}`, {
      method: "POST", body: marker, headers: { authorization: `Bearer ${marker}`, "user-agent": marker },
    });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).receipts.length, 4);
    assert.equal(received.length, 4);
    assert.equal(JSON.stringify(received).includes(marker), false);
    const tuples = received.map(item => {
      assert.equal(item.method, "POST");
      assert.equal(item.body, `amail_native_body_${run}`);
      const url = new URL(item.url), headers = new Headers(item.headers);
      assert.equal(url.searchParams.get("query"), `amail_native_query_${run}`);
      assert.equal(headers.get("authorization"), null);
      assert.equal(headers.get("user-agent"), `amail_native_header_${run}`);
      assert.equal(headers.get("traceparent"), `00-${run}-0123456789abcdef-01`);
      return url.pathname;
    });
    assert.equal(new Set(tuples).size, 4);
  } finally { await mf.dispose(); }
});

test("compiled Rust probe reports new getter unavailable on the pinned older runtime", async () => {
  const output = [];
  const mf = new Miniflare({ cf: false, ...options("probe"),
    handleRuntimeStdio(stdout, stderr) {
      for (const stream of [stdout, stderr]) {
        stream.setEncoding("utf8");
        stream.on("data", chunk => output.push(chunk));
      }
    } });
  try {
    const marker = "SYNTHETIC_USER_DATA_MUST_NOT_LOG";
    const response = await mf.dispatchFetch(`https://synthetic.invalid/baseline/success/amail_native_path_${run}?private=${marker}`, {
      method: "POST", body: marker, headers: { "user-agent": marker },
    });
    const report = await response.json();
    assert.equal(response.status, 503);
    assert.equal(report.available, false);
    assert.equal(report.sampled, false);
    assert.ok(["get_active_span", "request_context"].includes(report.stage));
    assert.equal(JSON.stringify(report).includes(marker), false);
    assert.equal(output.join("").includes(marker), false);
    const unknown = await mf.dispatchFetch(`https://synthetic.invalid/${marker}`);
    assert.equal(unknown.status, 404);
  } finally { await mf.dispose(); }
});
