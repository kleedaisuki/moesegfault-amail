/** Execute only explicit Wrangler-output modules, never source-side SDK observers. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import test from "node:test";
import { createRequire } from "node:module";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const boundary = path.join(root, "infra/tests/worker-boundary");
const require = createRequire(import.meta.url);
const { Log, LogLevel, Miniflare } = await import(pathToFileURL(require.resolve("miniflare", { paths: [boundary] })).href);
const receiptPath = path.join(root, ".temp/ci/packaging-probe/packages.json");
const receipt = JSON.parse(await readFile(receiptPath, "utf8"));
assert.equal(process.env.GITHUB_ACTIONS, "true", "packaged native tests belong on hosted runners");

/** Native console data stays in a local synthetic capture; no external sink exists. */
class CapturedLog extends Log {
  constructor(records) { super(LogLevel.DEBUG); this.records = records; }
  logWithLevel(_level, message) { this.records.push(String(message)); }
}

/** Explicit arrays prevent falling back to original/generated/source module trees. */
async function modules(item) {
  const entry = path.join(root, item.entry), wasm = path.join(root, item.wasm);
  for (const [file, digest] of Object.entries(item.files)) {
    const content = await readFile(path.join(path.dirname(entry), file));
    assert.equal(createHash("sha256").update(content).digest("hex"), digest, "packaged bytes changed after dry run");
  }
  return [{ type: "ESModule", path: entry, contents: await readFile(entry, "utf8") },
          { type: "CompiledWasm", path: wasm, contents: await readFile(wasm) }];
}

/** Every dry-run product must load its complete real module graph without egress. */
for (const item of receipt.packages) {
  test(`${item.component}/${item.realm}: actual packaged graph loads`, async () => {
    const records = [], graph = await modules(item), folder = path.dirname(path.join(root, item.entry));
    const common = { modulesRoot: folder, compatibilityDate: "2026-07-30",
      outboundService() { throw new Error("packaged probe egress refused"); } };
    const mf = new Miniflare({ cf: false, log: new CapturedLog(records), ...common, modules: graph });
    try {
      await mf.ready;
      if (item.component === "mail_api") {
        const worker = await mf.getWorker();
        const response = await worker.fetch("https://synthetic.invalid/health");
        assert.equal(response.status, 200);
        const body = await response.json();
        assert.equal(body.status, "ok", "real packaged Rust dispatcher executed");
        assert.match(body.request_id, /^[0-9a-f-]{36}$/);
        assert.equal((await worker.fetch("https://synthetic.invalid/v1/addresses")).status, 401);
        try {
          assert.notEqual((await worker.scheduled({ cron: "*/5 * * * *" })).outcome, "ok", "API cannot accept Cron");
        } catch (error) {
          assert.match(String(error), /scheduled|Handler/i);
        }
      }
    } finally { await mf.dispose(); }
  });

  if (item.component === "mail_api") {
    test(`${item.component}/${item.realm}: packaged API is fetch-only composition`, async () => {
      const graph = await modules(item), folder = path.dirname(path.join(root, item.entry));
      const inspector = { type: "ESModule", path: path.join(folder, "synthetic-inspector.mjs"), contents:
        `import { WorkerEntrypoint } from "cloudflare:workers";
         import * as Entry from "./${path.basename(item.entry)}";
         export default class Inspector extends WorkerEntrypoint {
           fetch() { return Response.json({ exports: Object.keys(Entry).sort(),
             methods: Object.getOwnPropertyNames(Entry.default.prototype).filter(name => name !== "constructor").sort(),
             platformBase: Object.getPrototypeOf(Entry.default) === WorkerEntrypoint }); }
         }` };
      const mf = new Miniflare({ cf: false, modulesRoot: folder, modules: [inspector, ...graph],
        compatibilityDate: "2026-07-30", outboundService() { throw new Error("inspector egress refused"); } });
      try {
        assert.deepEqual(await (await mf.dispatchFetch("https://synthetic.invalid/surface")).json(),
                         { exports: ["default"], methods: ["fetch"], platformBase: true });
      } finally { await mf.dispose(); }
    });
  }

  if (item.component === "trace_sink") {
    test(`${item.component}/${item.realm}: packaged Rust Queue acknowledges poison without logging it`, async () => {
      const graph = await modules(item), folder = path.dirname(path.join(root, item.entry)), records = [];
      const marker = "SYNTHETIC_PACKAGED_QUEUE_BARRIER";
      let arrived;
      const barrier = new Promise(resolve => { arrived = resolve; });
      const observer = { type: "ESModule", path: path.join(folder, "synthetic-queue-observer.mjs"), contents:
        `import Generated from "./${path.basename(item.entry)}";
         export default class Observer extends Generated {
           async queue(...args) { const result = await super.queue(...args); console.log("${marker}"); return result; }
         }` };
      const mf = new Miniflare({ cf: false, log: new CapturedLog(records), modulesRoot: folder,
        modules: [observer, ...graph], compatibilityDate: "2026-07-30",
        handleRuntimeStdio(stdout, stderr) {
          for (const stream of [stdout, stderr]) {
            stream.setEncoding("utf8");
            let captured = "";
            stream.on("data", chunk => { captured += chunk; records.push(chunk); if (captured.includes(marker)) arrived(); });
          }
        }, outboundService() { throw new Error("Queue egress refused"); } });
      const event = { schema_version: 1, event_id: "00000000-0000-4000-8000-000000000002",
        service: "mail_api", operation: "messages_list", phase: "request_exit",
        trace_id: "0123456789abcdef0123456789abcdef", span_id: "abcdef0123456789",
        request_id: "00000000-0000-4000-8000-000000000001", outcome: "success", http_status_class: 2, duration_ms_bucket: 8 };
      let timer;
      try {
        const messages = [event, { ...event, subject: "SYNTHETIC_PACKAGING_POISON" }].map((body, index) =>
          ({ id: `synthetic-${index}`, timestamp: new Date(1_790_000_000_999), attempts: 1, body }));
        const result = await (await mf.getWorker()).queue("synthetic-trace", messages);
        assert.equal(result.outcome, "ok");
        assert.equal(result.retryBatch.retry, false);
        assert.deepEqual(result.retryMessages, []);
        assert.deepEqual(result.explicitAcks.sort(), ["synthetic-0", "synthetic-1"]);
        await Promise.race([barrier, new Promise((_, reject) => { timer = setTimeout(() => reject(new Error("packaged Queue barrier missing")), 5_000); })]);
        assert.equal(records.join("").includes("SYNTHETIC_PACKAGING_POISON"), false);
        const events = records.join("").split("\n").flatMap(line => {
          const match = line.match(/(\{"schema_version".*\})/);
          return match ? [JSON.parse(match[1])] : [];
        });
        assert.deepEqual(events, [event]);
      } finally { clearTimeout(timer); await mf.dispose(); }
    });
  }
}

/** Node TAP remains authoritative; this only documents which exact graphs were exercised. */
test("packaged receipt retains diagnostic boundaries", async () => {
  await writeFile(path.join(path.dirname(receiptPath), "native-graphs.json"), JSON.stringify({
    schema: "packaged-native-graphs/v1", build_source_sha: receipt.source_sha,
    probe_source_sha: receipt.probe_sha, build_run_id: receipt.run_id, diagnostic_only: true,
    packages: receipt.packages.map(({ component, realm, entry, wasm_sha256 }) => ({ component, realm, entry, wasm_sha256 })),
  }));
});
