/** Hosted-only native workerd discriminators for complete accepted-item liveness. */
import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import { Miniflare } from "miniflare";
import { accepted, indexedText, text, sender, issuer } from "./outbound-recovery-fixture.mjs";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const phases = ["addresses", "outbound", "embeddings", "storage", "deleted", "orphans", "search", "abuse"];
// Historical slot, not invocation entry time: outbound must be first (slot % 8 = 1).
const outboundSlot = 1_680_000_300_000;
assert.equal(Math.floor(outboundSlot / 300_000) % 8, 1);

/** Fresh synthetic bindings, unchanged built Wasm and strict local egress only. */
async function fixture(run) {
  let unexpected = 0;
  const mf = new Miniflare({ cf: false, workers: [{
    name: "amail-liveness-synthetic", modules: true,
    scriptPath: path.join(root, "infra/tests/worker-boundary/maintenance-liveness-observer.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-08-06",
    bindings: { CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      MAIL_DOMAIN: "mail-staging.moesegfault.dev", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    outboundService(request) {
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") {
        return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
      }
      unexpected++;
      throw new Error("unexpected synthetic liveness egress");
    },
  }] });
  try {
    const { MAIL_DB: db, MAIL_BODIES: bucket } = await mf.getBindings();
    await applyMigrations(db, path.join(root, "crates/mail-worker/migrations"));
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,'recovery-synthetic',?2,'synthetic-recovery-owner',0,'active',?3)")
      .bind(sender, issuer, Date.now()).run();
    await db.prepare("UPDATE embedding_dependency SET blocked_until=?1 WHERE id=1").bind(Date.now() + 86_400_000).run();
    const tick = async (policy = {}, scheduledTime = outboundSlot) => {
      await mf.dispatchFetch("https://synthetic.invalid/liveness-policy", { method: "POST", body: JSON.stringify(policy) });
      const result = await (await mf.getWorker()).scheduled({ scheduledTime: new Date(scheduledTime) });
      assert.equal(result.outcome, "ok", "native scheduled handler must return normally");
      assert.equal(unexpected, 0, "no SMTP, Identity, OpenRouter or provider mutation");
      return (await mf.dispatchFetch("https://synthetic.invalid/liveness-stats")).json();
    };
    await run({ db, bucket, tick });
  } finally { await mf.dispose(); }
}

/** Stable rows expose first admission and untouched following-item scheduling. */
async function backlog(db, bucket) {
  await accepted(db, bucket, "liveness-first");
  await accepted(db, bucket, "liveness-second", "second body");
  await db.exec("UPDATE send_requests SET created_at=CASE WHEN message_id='liveness-first' THEN 1 ELSE 2 END;");
  await db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES('liveness-old-event','synthetic-provider','synthetic-message','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0)").run();
}

/** Completion means publication plus byte-exact independent text reconstruction. */
async function completeFirst(db, stats) {
  assert.equal(stats.chunks, 66);
  assert.deepEqual(stats.stageBatches, [8, 8, 8, 8, 8, 8, 8, 8, 2]);
  assert.equal(await indexedText(db, "liveness-first"), text);
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='liveness-first'").first()).state, "sent");
  assert.deepEqual(stats.due, ["liveness-first"]);
  assert.deepEqual(stats.r2.filter(row => row.method === "get").map(row => row.key), ["messages/liveness-first.zip"]);
  assert.equal((await db.prepare("SELECT index_next_attempt_at FROM send_requests WHERE message_id='liveness-second'").first()).index_next_attempt_at, 0);
  assert.equal(await indexedText(db, "liveness-second"), null);
}

/** The original 15-second mid-chunk cutoff fails this real 19.8-second workload. */
test("66 slow native batch members finish once while later cleanup remains live", { timeout: 120_000 }, async () => fixture(async ({ db, bucket, tick }) => {
  await backlog(db, bucket);
  const started = performance.now();
  const stats = await tick({ chunkDelayMs: 300 });
  assert.ok(performance.now() - started >= 19_800, "real timer delay, not only a fake clock discriminator");
  await completeFirst(db, stats);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events WHERE event_id='liveness-old-event'").first()).n, 0);
  assert.deepEqual(stats.phases, [...phases.slice(1), phases[0]]);
}));

/** A whole admitted projector is not cut short even beyond the work cutoff. */
test("logical cutoff at chunk 40 finishes the admitted item without another phase", async () => fixture(async ({ db, bucket, tick }) => {
  await backlog(db, bucket);
  const stats = await tick({ jumpAtChunk: 40, chunkJumpMs: 116_000 });
  await completeFirst(db, stats);
  assert.deepEqual(stats.phases, ["outbound"]);
  assert.equal(stats.afterCutoff.filter(row => row.chunk).length, 26, "continuation counts members, not native calls");
  assert.ok(stats.afterCutoff.every(row => row.phase === null), "only admitted continuation, no new business phase");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events WHERE event_id='liveness-old-event'").first()).n, 1);
}));

/** Setup crossing the soft slice must not consume the first whole-item entitlement. */
test("slow outbound setup preserves the first complete-item entitlement", async () => fixture(async ({ db, bucket, tick }) => {
  await backlog(db, bucket);
  await completeFirst(db, await tick({ setupJumpMs: 16_000 }));
}));

/** Insufficient completion headroom refuses setup as well as CAS and archive I/O. */
test("outbound with less than 60 seconds headroom performs no business setup", async () => fixture(async ({ db, bucket, tick }) => {
  await backlog(db, bucket);
  const stats = await tick({ addressJumpMs: 56_000 }, outboundSlot - 300_000);
  assert.equal(stats.setup, 0);
  assert.deepEqual(stats.due, []);
  assert.deepEqual(stats.r2, []);
  assert.equal(stats.chunks, 0);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM send_requests WHERE state='accepted' AND index_next_attempt_at=0").first()).n, 2);
}));

/** Rotation depends only on scheduled slots, not isolate-local invocation count. */
test("all eight scheduled slots rotate deterministically across duplicate delayed and missed events", async () => fixture(async ({ tick }) => {
  const base = outboundSlot - 300_000;
  for (let slot = 0; slot < 8; slot++) {
    const expected = [...phases.slice(slot), ...phases.slice(0, slot)];
    assert.deepEqual((await tick({}, base + slot * 300_000)).phases, expected);
  }
  // All historical slots are delayed relative to invocation. Duplicate and skip
  // checks deliberately reuse one isolate and omit intermediate schedule events.
  assert.deepEqual((await tick({}, base + 3 * 300_000)).phases, [...phases.slice(3), ...phases.slice(0, 3)]);
  assert.deepEqual((await tick({}, base + 19 * 300_000)).phases, [...phases.slice(3), ...phases.slice(0, 3)]);
}));

/** Grouping removes network-round-trip amplification without reducing SQL tokens. */
test("nine staging round trips finish a maximum archive with two-second native RTT", { timeout: 120_000 }, async () => fixture(async ({ db, bucket, tick }) => {
  await backlog(db, bucket);
  const started = performance.now();
  const stats = await tick({ stageCallDelayMs: 2_000 });
  assert.ok(performance.now() - started >= 18_000, "nine genuine delayed native calls, not a logical clock claim");
  await completeFirst(db, stats);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events WHERE event_id='liveness-old-event'").first()).n, 0);
}));
