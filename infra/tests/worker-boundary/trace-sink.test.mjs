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
/** Synthetic reader records cover observed client boundaries without creating mail users. */
function clientAttempts() {
  const base = { schema_version: 1, event_id: "00000000-0000-4000-8000-000000000004",
    service: "mail_cli", operation: "messages_list", phase: "operation_exit",
    trace_id: "0123456789abcdef0123456789abcdef", span_id: "0123456789abcdef",
    request_id: "00000000-0000-4000-8000-000000000001",
    duration_ms_bucket: 131_072, response_bytes_bucket: 0,
    occurred_at_ms: 1_790_000_000_123, duration_ms: 121_007 };
  return [
    { client_phase: "auth", client_error_kind: "credential_unavailable", http_status: 0 },
    { client_phase: "transport", client_error_kind: "connect", http_status: 0 },
    { client_phase: "response_body", client_error_kind: "decode", http_status: 200 },
    { client_phase: "complete", http_status: 201 },
    { client_phase: "complete", http_status: 503 },
  ].map(fields => {
    const failed = fields.client_phase !== "complete";
    return { ...base, ...fields, http_status_class: Math.floor(fields.http_status / 100),
      outcome: failed ? "phase_failure" : fields.http_status < 400 ? "success" : "server_error",
      ...(failed ? { error_code: "dependency_failure" } : {}) };
  });
}
/** Dispatch a native batch and await the handler's actual result/acknowledgements. */
async function consume(bodies) {
  const logs = [];
  let arrived;
  const barrier = new Promise(resolve => { arrived = resolve; });
  const marker = "SYNTHETIC_QUEUE_CONSOLE_BARRIER";
  const mf = new Miniflare({ cf: false, log: new CapturedLog(logs), modules: true,
    scriptPath: path.join(root, "infra/tests/worker-boundary/trace-sink-entry.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-07-30",
    handleRuntimeStdio(stdout, stderr) {
      for (const stream of [stdout, stderr]) {
        stream.setEncoding("utf8");
        let captured = "";
        stream.on("data", chunk => {
          captured += chunk;
          logs.push(chunk);
          if (captured.includes(marker)) arrived();
        });
      }
    },
    outboundService() { throw new Error("trace sink must not contact any external service"); } });
  try {
    const messages = bodies.map((body, index) => ({ id: `synthetic-${index}`,
      timestamp: new Date(1_790_000_000_999), attempts: 1, body }));
    const result = await (await mf.getWorker()).queue("synthetic-trace", messages);
    assert.equal(result.outcome, "ok");
    assert.equal(result.retryBatch.retry, false);
    assert.deepEqual(result.retryMessages, []);
    assert.deepEqual(result.explicitAcks.sort(), messages.map(message => message.id).sort());
    let timer;
    try {
      await Promise.race([barrier, new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error("native console completion barrier missing")), 5_000);
      })]);
    } finally { clearTimeout(timer); }
  } finally {
    await mf.dispose();
  }
  const records = logs.join("").split("\n").flatMap(line => {
      const match = line.match(/(\{"schema_version".*\})/);
      return match ? [JSON.parse(match[1])] : [];
    });
  return { logs: logs.join(""), records };
}

test("native sink retains legacy and enriched causal measurements exactly", async () => {
  const old = legacy();
  const enriched = { ...legacy(), event_id: "00000000-0000-4000-8000-000000000003",
    occurred_at_ms: 1_790_000_000_123, duration_ms: 7, http_status: 201 };
  const attempts = clientAttempts();
  const { records } = await consume([old, enriched, ...attempts]);
  assert.deepEqual(records, [old, enriched, ...attempts]);
  assert.equal(records[0].occurred_at_ms, undefined);
  assert.equal(records[1].occurred_at_ms, enriched.occurred_at_ms,
    "source event clock must not be replaced by Queue delivery time");
  assert.equal(records[4].outcome, "phase_failure", "a 200 header cannot hide response-body failure");
});

test("native sink drops invalid measurement types and mismatched status without replay", async () => {
  const bad = [{ occurred_at_ms: -1 }, { duration_ms: 0.5 }, { http_status: 503 },
    { duration_ms: Number.MAX_SAFE_INTEGER + 1 }, { http_status: 600 }];
  const bodyFailure = clientAttempts()[2];
  const { records } = await consume([
    ...bad.map(fields => ({ ...legacy(), ...fields })),
    { ...bodyFailure, outcome: "success" },
    { ...bodyFailure, http_status: 0, http_status_class: 0 },
    { ...bodyFailure, duration_ms: null },
    { ...bodyFailure, client_error_kind: "credential_unavailable" },
    { ...bodyFailure, client_phase: "complete" },
    { ...legacy(), client_phase: "complete" },
  ]);
  assert.deepEqual(records, []);
});

test("native sink rejects poisoned metadata without logging either the payload or error", async () => {
  const marker = "SYNTHETIC_PRIVATE_TRACE_MARKER";
  const { logs, records } = await consume([
    { ...legacy(), occurred_at_ms: marker }, { ...legacy(), user_subject: marker },
    marker, { ...legacy(), duration_ms: marker }, legacy(),
    { ...clientAttempts()[2], client_phase: marker },
    { ...clientAttempts()[2], client_error_kind: marker },
  ]);
  assert.equal(logs.includes(marker), false);
  assert.deepEqual(records, [legacy()], "positive control proves the Queue entrypoint executed");
});
