/** Native scheduled Billing reconciliation using real quota SQL and isolated D1/R2. */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { applyMigrations, seedResourceAccount } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const issuer = "https://identity-staging.moesegfault.dev";
const subject = "synthetic-outbox-owner";
const ownerId = "synthetic-opaque-billing-owner";
const authorizationId = "abcdefghijklmnopqrstuvwx01234567";
const idem = "2560d2eb-3326-4017-9dc0-56dd9d738b5a";

/** Generate one real overage event through production reservation/acceptance triggers. */
async function fixture(run) {
  const calls = [], liabilities = new Map();
  let failure = false;
  const mf = new Miniflare({ cf: false, workers: [{
    name: "maintenance", modules: true, compatibilityDate: "2026-08-06",
    scriptPath: path.join(root, "crates/mail-worker/entry/maintenance.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules,
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    bindings: { IDENTITY_ISSUER: issuer, MAIL_DOMAIN: "mail-staging.moesegfault.dev",
      CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-routing-token",
      EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress",
      BILLING_BASE_URL: "https://billing-staging.moesegfault.dev",
      BILLING_SUBSCRIBE_ORIGIN: "https://subscribe-staging.moesegfault.dev",
      BILLING_RETURN_URL: "https://amail-staging.moesegfault.dev/billing/return",
      BILLING_SERVICE_KEY: "synthetic-outbox-service-key" },
    async outboundService(request) {
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") {
        return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
      }
      assert.equal(request.method, "POST");
      assert.equal(request.url, "https://billing-staging.moesegfault.dev/v1/service/amail/usage");
      assert.equal(request.headers.get("Authorization"), "Bearer synthetic-outbox-service-key");
      assert.match(request.headers.get("traceparent"), /^00-[0-9a-f]{32}-[0-9a-f]{16}-01$/);
      const event = await request.json();
      assert.equal(request.headers.get("Idempotency-Key"), event.event_id);
      assert.equal(event.owner_id, ownerId);
      assert.equal(event.authorization_id, authorizationId);
      assert.ok(Number.isInteger(event.authorized_at));
      assert.ok(event.authorized_at <= event.occurred_at);
      assert.equal(event.meter, "outbound_recipients");
      assert.equal(event.quantity, 1);
      assert.equal(event.amount_micros, 5000);
      assert.doesNotMatch(JSON.stringify(event), /synthetic-outbox-service-key|synthetic-outbox-owner|@/);
      calls.push(event);
      if (failure) return Response.json({ code: "synthetic_unavailable" }, { status: 503 });
      if (liabilities.has(event.event_id)) assert.deepEqual(liabilities.get(event.event_id), event);
      else liabilities.set(event.event_id, event);
      return Response.json({ event_id: event.event_id, amount_micros: 5000, settlement_status: "pending_settlement" });
    },
  }] });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    await applyMigrations(db, path.join(root, "crates/mail-worker/migrations"));
    await seedResourceAccount(db, issuer, subject);
    await db.prepare("UPDATE resource_accounts SET billing_owner_id=?1,authorization_id=?2,overage_budget_micros=10000,authority_updated_at=unixepoch() WHERE owner_iss=?3 AND owner_sub=?4")
      .bind(ownerId, authorizationId, issuer, subject).run();
    await db.prepare("INSERT INTO resource_send_reservations(owner_iss,owner_sub,idem_key,period_start,units,authorization_id,authorized_at) SELECT ?1,?2,?3,period_start,101,?4,unixepoch()-5 FROM resource_current WHERE owner_iss=?1 AND owner_sub=?2")
      .bind(issuer, subject, idem, authorizationId).run();
    await db.prepare("UPDATE resource_send_reservations SET state='accepted' WHERE owner_iss=?1 AND owner_sub=?2 AND idem_key=?3")
      .bind(issuer, subject, idem).run();
    const row = () => db.prepare("SELECT * FROM resource_outbox").first();
    assert.equal((await row()).amount_micros, 5000);
    assert.equal((await row()).delivered_at, null);
    const tick = () => mf.getWorker().then(worker => worker.scheduled());
    await run({ db, row, tick, calls, liabilities, fail: value => { failure = value; } });
  } finally { await mf.dispose(); }
}

test("scheduled reconciliation delivers one original human-authorized usage event", async () => fixture(async ({ tick, row, calls, liabilities }) => {
  await tick();
  assert.ok(Number.isInteger((await row()).delivered_at));
  assert.equal(calls.length, 1);
  assert.equal(liabilities.size, 1);
  await tick();
  assert.equal(calls.length, 1, "delivered usage is not resubmitted each Cron");
}));

test("transient Billing failure retains liability and backs off without losing its key", async () => fixture(async ({ db, row, tick, calls, liabilities, fail }) => {
  fail(true);
  await tick();
  const held = await row();
  assert.equal(held.delivered_at, null);
  assert.equal(held.attempts, 1);
  assert.ok(held.next_attempt_at > Math.floor(Date.now() / 1000));
  await tick();
  assert.equal(calls.length, 1, "not-yet-due retry cannot monopolize the next sweep");
  fail(false);
  await db.exec("UPDATE resource_outbox SET next_attempt_at=0;");
  await tick();
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(liabilities.size, 1);
  assert.ok(Number.isInteger((await row()).delivered_at));
}));

test("lost local ACK replays the same immutable event rather than a second liability", async () => fixture(async ({ db, row, tick, calls, liabilities }) => {
  await db.exec("CREATE TRIGGER synthetic_lost_ack BEFORE UPDATE OF delivered_at ON resource_outbox WHEN NEW.delivered_at IS NOT NULL BEGIN SELECT RAISE(FAIL,'synthetic lost local ACK'); END;");
  await tick();
  assert.equal((await row()).delivered_at, null);
  assert.equal(liabilities.size, 1, "Billing accepted before local ACK failed");
  await db.exec("DROP TRIGGER synthetic_lost_ack;");
  await tick();
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0], calls[1]);
  assert.equal(liabilities.size, 1, "same event must remain one logical external liability");
  assert.ok(Number.isInteger((await row()).delivered_at));
}));
