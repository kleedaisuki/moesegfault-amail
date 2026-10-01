/** Hosted-only unchanged Rust/Wasm Cron plus real synthetic native Queue binding. */
import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Log, LogLevel, Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { accepted, indexedText, sender, issuer } from "./outbound-recovery-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const phases = ["addresses", "outbound", "embeddings", "storage", "deleted", "orphans", "search", "abuse"];
const phaseCodes = ["routing_reconciliation_failed", "outbound_reconciliation_failed",
  "semantic_index_retry_failed", "storage_ledger_reconciliation_failed", "deleted_message_cleanup_failed",
  "orphan_object_cleanup_failed", "search_job_cleanup_failed", "abuse_data_cleanup_failed"];
const deepCodes = ["address_reconciliation_batch_full", "non_enabled_committed_routing_rule",
  "non_enabled_provisioning_routing_rule", "semantic_document_quarantined", "semantic_provider_cooldown"];
const slot = 1_680_000_000_000; // Historical scheduled slot % 8 = 0, not entry time.
assert.equal(Math.floor(slot / 300_000) % 8, 0);
const secret = "SYNTHETIC_PRIVATE_DIAGNOSTIC_CONTENT";

/** Keep runtime diagnostics private; fixture failures report fixed assertions only. */
class PrivateLog extends Log {
  constructor(records) { super(LogLevel.DEBUG); this.records = records; }
  logWithLevel(_level, message) { this.records.push(String(message)); }
}

/** Independent local storage with strict synthetic GET/provider-error exchanges. */
async function fixture(run, { queueBinding = true, deep = false } = {}) {
  const logs = [], rules = [];
  let unexpected = 0, embeddingCalls = 0;
  const mf = new Miniflare({ cf: false, log: new PrivateLog(logs), workers: [{
    name: "amail-maintenance-diagnostics-synthetic", modules: true,
    scriptPath: path.join(root, "infra/tests/worker-boundary/maintenance-diagnostics-observer.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-08-06",
    bindings: { CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: secret,
      MAIL_DOMAIN: "mail-staging.moesegfault.dev", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress",
      OPENROUTER_API_KEY: secret, OPENROUTER_EMBEDDING_MODEL: "qwen/qwen3-embedding-8b" },
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    ...(queueBinding ? { queueProducers: { TRACE_EVENTS: "synthetic-maintenance-trace" } } : {}),
    outboundService(request) {
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") {
        return Response.json({ success: true, result: rules, result_info: { total_pages: 1 } });
      }
      if (deep && request.method === "POST" && request.url === "https://openrouter.ai/api/v1/embeddings") {
        embeddingCalls++;
        // Two third-attempt malformed documents quarantine; then dependency cooldown.
        return new Response(secret, { status: embeddingCalls <= 2 ? 200 : 401 });
      }
      unexpected++;
      throw new Error("unexpected synthetic diagnostic egress");
    },
  }] });
  try {
    const { MAIL_DB: db, MAIL_BODIES: bucket } = await mf.getBindings();
    await applyMigrations(db, path.join(root, "crates/mail-worker/migrations"));
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,'recovery-synthetic',?2,'synthetic-recovery-owner',0,'active',0)")
      .bind(sender, issuer).run();
    if (!deep) await db.prepare("UPDATE embedding_dependency SET blocked_until=?1 WHERE id=1").bind(Date.now() + 86_400_000).run();
    const stats = async () => (await mf.dispatchFetch("https://synthetic.invalid/diagnostics-stats")).json();
    const tick = async (policy = {}, scheduledTime = slot) => {
      await mf.dispatchFetch("https://synthetic.invalid/diagnostics-policy", { method: "POST", body: JSON.stringify(policy) });
      const result = await (await mf.getWorker()).scheduled({ scheduledTime: new Date(scheduledTime) });
      assert.equal(result.outcome, "ok", "diagnostic errors do not fail the scheduled handler");
      assert.equal(unexpected, 0, "SMTP, Identity, provider writes and foreign egress stay denied");
      const resultStats = await stats();
      assert.equal(resultStats.valid, true, "native bodies preserve exact closed standalone schema");
      for (const marker of [secret, "SYNTHETIC_PRIVATE_D1_FAILURE", "SYNTHETIC_PRIVATE_QUEUE_FAILURE", sender]) {
        assert.equal(logs.join("\n").includes(marker), false, "private synthetic marker leaked to runtime diagnostics");
        assert.equal(JSON.stringify(resultStats).includes(marker), false, "observer stats retain fixed facts only");
      }
      return resultStats;
    };
    await run({ db, bucket, tick, stats, rules, embeddingCalls: () => embeddingCalls });
  } finally { await mf.dispose(); }
}

/** Positive control is mandatory: zero sends alone could be a failed Queue cast. */
function oneBatch(stats, { forwarded = 1 } = {}) {
  assert.equal(stats.constructor, "WorkerQueue", "real native constructor survives the proxy");
  assert.equal(stats.lookups, 1);
  assert.equal(stats.send, 0);
  assert.equal(stats.batches, 1);
  assert.equal(stats.forwarded, forwarded);
  assert.equal(stats.settled, forwarded);
  assert.ok(stats.codes.length > 0 && stats.codes.length <= 13);
  assert.ok(stats.lengths.every(length => length <= 1024));
  assert.ok(stats.charge <= 240_000);
  assert.ok(stats.envelopeBytes + 100 * stats.codes.length < stats.charge,
    "actual native envelope plus documented approximate metadata fits reviewed headroom");
  const lookup = stats.tape.indexOf("lookup"), send = stats.tape.indexOf("queue");
  assert.ok(lookup >= 0 && send > lookup);
  assert.ok(stats.tape.slice(0, lookup).some(kind => kind === "d1"));
  assert.ok(stats.tape.slice(lookup).every(kind => kind === "lookup" || kind === "queue"),
    "no D1/R2 business submission follows final Queue lookup/send");
}

test("eight independently failed phases reach exactly one real native final batch", async () => fixture(async ({ tick }) => {
  const stats = await tick({ failPhases: phases });
  oneBatch(stats);
  assert.deepEqual(stats.phases, phases);
  assert.deepEqual(stats.codes, phaseCodes);
}));

test("healthy no-op phases never resolve or submit to Queue", async () => fixture(async ({ tick }) => {
  const stats = await tick();
  assert.deepEqual(stats.phases, phases);
  assert.equal(stats.lookups, 0);
  assert.equal(stats.batches, 0);
}));

test("thirty routed rows and repeated quarantine notes retain all five deep facts once", async () => fixture(async ({ db, tick, rules, embeddingCalls }) => {
  for (let n = 0; n < 30; n++) {
    const address = `synthetic-deep-${n}@mail-staging.moesegfault.dev`, id = `synthetic-rule-${n}`;
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,cf_rule_id,state,needs_reconcile,created_at) VALUES(?1,?2,?3,?4,0,?5,?6,1,?7)")
      .bind(address, `synthetic-deep-${n}`, issuer, `synthetic-deep-owner-${n}`, id, n % 2 ? "provisioning" : "active", n).run();
    rules.push({ id, source: "api", enabled: false, name: `amail ${address}`,
      actions: [{ type: "worker", value: ["synthetic-ingress"] }],
      matchers: [{ type: "literal", field: "to", value: address }] });
  }
  for (let n = 0; n < 3; n++) {
    await db.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,has_html,has_text,attachment_count,r2_key,size_bytes) VALUES(?1,?2,?3,'synthetic-recovery-owner','inbound','synthetic@example.invalid','[]',?4,?4,'{}',?5,0,1,0,?6,64)")
      .bind(`synthetic-deep-message-${n}`, sender, issuer, secret, n, `messages/synthetic-deep-message-${n}.zip`).run();
  }
  await db.exec("UPDATE embedding_work SET attempts=2;");
  const stats = await tick();
  oneBatch(stats);
  assert.deepEqual(stats.codes, deepCodes);
  assert.equal(embeddingCalls(), 3);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM embedding_work WHERE state='quarantined'").first()).n, 2);
  assert.ok((await db.prepare("SELECT blocked_until FROM embedding_dependency WHERE id=1").first()).blocked_until > Date.now());
}, { deep: true }));

/** Queue failures do not alter already committed projection or later retention. */
for (const mode of ["throw", "reject", "wrong", "missing"]) {
  test(`final ${mode} Queue cannot undo durable work or skip later cleanup`, async () => fixture(async ({ db, bucket, tick }) => {
    await accepted(db, bucket, "diagnostics-durable", "synthetic durable body");
    await db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES('diagnostics-old-event','synthetic-provider','synthetic-message','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0)").run();
    const stats = await tick({ failPhases: ["storage"], queueMode: mode });
    assert.equal(await indexedText(db, "diagnostics-durable"), "synthetic durable body");
    assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='diagnostics-durable'").first()).state, "sent");
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events WHERE event_id='diagnostics-old-event'").first()).n, 0);
    assert.deepEqual(stats.phases, phases);
    if (mode === "wrong" || mode === "missing") {
      assert.equal(stats.batches, 0);
      assert.equal(stats.lookups, 1);
    } else oneBatch(stats, { forwarded: 0 });
  }, { queueBinding: mode !== "missing" }));
}

test("one final delayed Queue await cannot delay later business phases", async () => fixture(async ({ db, bucket, tick, stats }) => {
  await accepted(db, bucket, "diagnostics-delayed", "synthetic durable body");
  const pending = tick({ failPhases: ["storage"], queueDelayMs: 1500 });
  let entered;
  for (let attempt = 0; attempt < 150; attempt++) {
    entered = await stats();
    if (entered.batches === 1) break;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  assert.equal(entered.batches, 1, "observe final Queue promise before resolving it");
  assert.equal(entered.settled, 0);
  assert.deepEqual(entered.phases, phases);
  assert.equal(await indexedText(db, "diagnostics-delayed"), "synthetic durable body");
  oneBatch(await pending);
}));

test("synthetic thirty-second D1 stalls stop new phases after headroom cutoff, not 900 seconds", async () => fixture(async ({ tick }) => {
  const stats = await tick({ failPhases: phases, jumpEach: 30_000 });
  oneBatch(stats);
  assert.deepEqual(stats.phases, phases.slice(0, 4));
  assert.equal(stats.statements, 4);
  assert.equal(stats.codes.filter(code => code === "maintenance_deadline_deferred").length, 4);
  assert.deepEqual(stats.codes.slice(0, 4), phaseCodes.slice(0, 4));
}));

test("back-to-back rotated invocations do not retain diagnostics or condition presence", async () => fixture(async ({ tick }) => {
  oneBatch(await tick({ failPhases: phases }));
  const healthy = await tick({}, slot + 300_000);
  assert.equal(healthy.batches, 0);
  assert.deepEqual(healthy.codes, []);
  assert.deepEqual(healthy.phases, [...phases.slice(1), phases[0]]);
}));
