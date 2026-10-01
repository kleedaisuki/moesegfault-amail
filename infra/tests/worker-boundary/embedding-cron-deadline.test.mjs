/** Hosted-only Cron embedding deadlines through unchanged built Rust/Wasm. */
import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Log, LogLevel, Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const endpoint = "https://openrouter.ai/api/v1/embeddings";
const bodySentinel = "SYNTHETIC_PRIVATE_CRON_BODY_3294";
const keySentinel = "SYNTHETIC_PRIVATE_CRON_KEY_a942";
const subjectSentinel = "SYNTHETIC_PRIVATE_CRON_SUBJECT_0512";
const model = "qwen/qwen3-embedding-8b";
const slot = 1_680_000_600_000; // Embeddings first; no setup phase consumes its timer.

/** Runtime log capture never prints synthetic content. */
class PrivateLog extends Log {
  constructor(records) { super(LogLevel.DEBUG); this.records = records; }
  logWithLevel(_level, message) { this.records.push(String(message)); }
}

/** Strict synthetic egress, fresh migrated D1 and the actual scheduled entry. */
async function exercise(response, { claimJumpMs = 0, cleanup = () => {} } = {}) {
  let calls = 0;
  const logs = [];
  const mf = new Miniflare({ cf: false, log: new PrivateLog(logs), workers: [{
    name: "cron-embedding-synthetic", modules: true,
    scriptPath: path.join(root, "infra/tests/worker-boundary/embedding-native-observer.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-08-06",
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    bindings: { OPENROUTER_API_KEY: keySentinel, OPENROUTER_EMBEDDING_MODEL: model,
      CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-routing-token",
      MAIL_DOMAIN: "mail-staging.moesegfault.dev", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    async outboundService(request) {
      if (request.url === endpoint) {
        calls++;
        assert.equal(request.method, "POST");
        assert.equal(request.headers.get("authorization"), `Bearer ${keySentinel}`);
        const input = await request.json();
        assert.equal(input.input, `${subjectSentinel}\n${bodySentinel}`);
        assert.equal(input.input_type, "search_document");
        assert.equal(input.dimensions, 256);
        assert.deepEqual(input.provider, { zdr: true, data_collection: "deny" });
        return response();
      }
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") {
        return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
      }
      throw new Error("unexpected synthetic Cron embedding egress");
    },
  }] });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    await applyMigrations(db, path.join(root, "crates/mail-worker/migrations"));
    await db.exec("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES('synthetic@mail-staging.moesegfault.dev','synthetic','https://synthetic.invalid','synthetic-owner',0,'active',0);");
    await db.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES('cron-first','synthetic@mail-staging.moesegfault.dev','https://synthetic.invalid','synthetic-owner','inbound','synthetic@example.invalid','[]',?1,?2,'{}',0,0,1,0,'synthetic.zip',100)")
      .bind(subjectSentinel, bodySentinel).run();
    await db.exec("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES('cron-old-event','synthetic','synthetic','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0);");
    await mf.dispatchFetch("https://synthetic.invalid/cron-policy", { method: "POST", body: JSON.stringify({ claimJumpMs }) });
    const started = Date.now();
    const scheduled = await (await mf.getWorker()).scheduled({ scheduledTime: new Date(slot) });
    const elapsed = Date.now() - started;
    assert.equal(scheduled.outcome, "ok");
    const native = await (await mf.dispatchFetch("https://synthetic.invalid/embedding-stats")).json();
    const work = await db.prepare("SELECT attempts,next_attempt_at,lease_until,lease_token,state,last_error_code FROM embedding_work WHERE message_id='cron-first'").first();
    const dependency = await db.prepare("SELECT blocked_until,last_error_code FROM embedding_dependency WHERE id=1").first();
    const message = await db.prepare("SELECT embedding_json,embedding_dimensions FROM messages WHERE id='cron-first'").first();
    const retainedEvent = (await db.prepare("SELECT COUNT(*) AS n FROM provider_events WHERE event_id='cron-old-event'").first()).n;
    for (const sentinel of [bodySentinel, subjectSentinel, keySentinel]) {
      assert.equal(logs.join("\n").includes(sentinel), false, "private sentinel entered runtime logs");
      assert.equal(JSON.stringify(native).includes(sentinel), false);
    }
    return { elapsed, calls, native, work, dependency, message, retainedEvent };
  } finally { await cleanup(); await mf.dispose(); }
}

/** Policy expiration releases only our token and never records a provider defect. */
function deferred(result) {
  assert.deepEqual(result.work, { attempts: 0, next_attempt_at: 0, lease_until: 0, lease_token: null, state: "pending", last_error_code: null });
  assert.deepEqual(result.dependency, { blocked_until: 0, last_error_code: null });
  assert.equal(result.message.embedding_json, null);
}

test("Cron embedding header stall aborts at ten seconds and leaves cleanup live", { timeout: 22_000 }, async () => {
  const result = await exercise(async () => {
    await new Promise(resolve => setTimeout(resolve, 12_000));
    return Response.json({ data: [{ embedding: Array(256).fill(2) }] });
  });
  deferred(result);
  assert.ok(result.elapsed >= 9_000 && result.elapsed < 16_000);
  assert.equal(result.calls, 1);
  assert.equal(result.native.abortCalls, 1);
  assert.equal(result.native.abortedSignals, 1);
  assert.equal(result.retainedEvent, 0);
});

test("Cron embedding body stall uses the same timer and cancels its pending reader", { timeout: 22_000 }, async () => {
  let source;
  const result = await exercise(() => new Response(new ReadableStream({
    start(controller) { source = controller; controller.enqueue(new TextEncoder().encode('{"data":')); },
  })), { cleanup: () => source.close() });
  deferred(result);
  assert.ok(result.elapsed >= 9_000 && result.elapsed < 16_000);
  assert.ok(result.native.reads >= 2 && result.native.bytes > 0);
  assert.equal(result.native.cancelCalls, 1);
  assert.equal(result.native.abortCalls, 1);
  assert.equal(result.native.abortedSignals, 1);
  assert.equal(result.retainedEvent, 0);
});

test("expired pre-transfer Cron deadline makes no OpenRouter call and releases lease", async () => {
  const result = await exercise(() => { throw new Error("expired input must not transfer"); }, { claimJumpMs: 116_000 });
  deferred(result);
  assert.equal(result.calls, 0);
  assert.equal(result.native.exchanges, 0);
  assert.equal(result.native.abortCalls, 0);
});

test("Cron exchange clips to seven remaining invocation seconds instead of restarting ten", { timeout: 22_000 }, async () => {
  const result = await exercise(async () => {
    await new Promise(resolve => setTimeout(resolve, 12_000));
    return Response.json({ data: [{ embedding: Array(256).fill(2) }] });
  }, { claimJumpMs: 108_000 });
  deferred(result);
  assert.ok(result.elapsed >= 6_000 && result.elapsed < 9_500);
  assert.equal(result.calls, 1);
  assert.equal(result.native.abortedSignals, 1);
});

test("Cron successful embedding preserves existing normalized vector and removes work", async () => {
  const result = await exercise(() => Response.json({ data: [{ embedding: Array(256).fill(2) }] }));
  assert.equal(result.calls, 1);
  assert.equal(result.work, null);
  assert.equal(result.message.embedding_dimensions, 256);
  assert.deepEqual(JSON.parse(result.message.embedding_json), Array(256).fill(0.0625));
  assert.equal(result.native.cancelCalls, 0);
  assert.equal(result.native.abortCalls, 0);
});

/** Ordinary provider response failures still follow existing durable backoff. */
test("Cron rate limit remains a provider failure, not policy deferral", async () => {
  const result = await exercise(() => new Response("synthetic provider text", { status: 429 }));
  assert.equal(result.calls, 1);
  assert.equal(result.work.attempts, 1);
  assert.equal(result.work.lease_token, null);
  assert.equal(result.work.last_error_code, "provider_rate_limited");
  assert.ok(result.work.next_attempt_at > Date.now());
  assert.ok(result.dependency.blocked_until > Date.now());
  assert.equal(result.dependency.last_error_code, "provider_rate_limited");
  assert.equal(result.native.cancelCalls, 1);
});
