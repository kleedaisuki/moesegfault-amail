/** Hosted native Queue entrypoint tests for the actual compiled Rust trace sink. */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Log, LogLevel, Miniflare } from "miniflare";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
/** Capture all native console output, including any accidental poison serialization. */
class CapturedLog extends Log {
  constructor(records) { super(LogLevel.DEBUG); this.records = records; }
  logWithLevel(_level, message) { this.records.push(String(message)); }
}
/** Valid old producer payload: the new reader must not invent timestamps. */
function legacy() {
  return { schema_version: 1, event_id: "00000000-0000-4000-8000-000000000002",
    service: "mail_api", operation: "messages_list", phase: "request_exit",
    trace_id: "0123456789abcdef0123456789abcdef", span_id: "abcdef0123456789",
    parent_span_id: "0123456789abcdef", request_id: "00000000-0000-4000-8000-000000000001",
    outcome: "success", http_status_class: 2, duration_ms_bucket: 8 };
}
/** Dispatch a native batch and await the handler's actual result/acknowledgements. */
async function consume(bodies) {
  const logs = [];
  const mf = new Miniflare({ cf: false, log: new CapturedLog(logs), modules: true,
    scriptPath: path.join(root, "workers/trace-sink/build/worker/shim.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-07-30",
    outboundService() { throw new Error("trace sink must not contact any external service"); } });
  try {
    const messages = bodies.map((body, index) => ({ id: `synthetic-${index}`,
      timestamp: new Date(1_790_000_000_999), body }));
    const result = await (await mf.getWorker()).queue("synthetic-trace", messages);
    assert.equal(result.outcome, "ok");
    assert.equal(result.retryAll, false);
    assert.deepEqual(result.explicitRetries, []);
    assert.deepEqual(result.explicitAcks.sort(), messages.map(message => message.id).sort());
    const records = logs.flatMap(line => {
      const match = line.match(/(\{"schema_version".*\})/);
      return match ? [JSON.parse(match[1])] : [];
    });
    return { logs: logs.join("\n"), records };
  } finally { await mf.dispose(); }
}

test("native sink retains legacy and enriched causal measurements exactly", async () => {
  const old = legacy();
  const enriched = { ...legacy(), event_id: "00000000-0000-4000-8000-000000000003",
    occurred_at_ms: 1_790_000_000_123, duration_ms: 7, http_status: 201 };
  const { records } = await consume([old, enriched]);
  assert.deepEqual(records, [old, enriched]);
  assert.equal(records[0].occurred_at_ms, undefined);
  assert.equal(records[1].occurred_at_ms, enriched.occurred_at_ms,
    "source event clock must not be replaced by Queue delivery time");
});

test("native sink drops invalid measurement types and mismatched status without replay", async () => {
  const bad = [{ occurred_at_ms: -1 }, { duration_ms: 0.5 }, { http_status: 503 },
    { duration_ms: Number.MAX_SAFE_INTEGER + 1 }, { http_status: 600 }];
  const { records } = await consume(bad.map(fields => ({ ...legacy(), ...fields })));
  assert.deepEqual(records, []);
});

test("native sink rejects poisoned metadata without logging either the payload or error", async () => {
  const marker = "SYNTHETIC_PRIVATE_TRACE_MARKER";
  const { logs, records } = await consume([
    { ...legacy(), occurred_at_ms: marker }, { ...legacy(), user_subject: marker },
    marker, { ...legacy(), duration_ms: marker }, legacy(),
  ]);
  assert.equal(logs.includes(marker), false);
  assert.deepEqual(records, [legacy()], "positive control proves the Queue entrypoint executed");
});
