/** Hosted workerd acceptance for the actual worker-build 0.8.5 module graph. */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Log, LogLevel, Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const worker = path.join(root, "crates/mail-worker");
const cron = "*/5 * * * *";
const slot = 1_680_000_000_000;
/** Real entries use shared native storage and fail-closed fixture egress. */
async function fixture(run) {
  let unexpected = 0, retiredRule = null, retiredDeletes = 0;
  const common = {
    modules: true, modulesRoot: root, modulesRules: workerModuleRules,
    // Harness-supported date; the production config's date is not changed.
    compatibilityDate: "2026-08-06",
    bindings: { MAIL_DOMAIN: "mail-staging.moesegfault.dev", CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    d1Databases: { MAIL_DB: "entry-split-shared-db" },
    r2Buckets: { MAIL_BODIES: "entry-split-shared-r2" },
    outboundService(request) {
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") {
        return Response.json({ success: true, result: retiredRule ? [retiredRule] : [], result_info: { total_pages: 1 } });
      }
      if (retiredRule && request.url === `https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules/${retiredRule.id}`) {
        if (request.method === "GET") return Response.json({ success: true, result: retiredRule });
        if (request.method === "DELETE") {
          retiredDeletes++;
          retiredRule = null;
          return Response.json({ success: true, result: null });
        }
      }
      unexpected++;
      throw new Error("unmatched split fixture egress");
    },
  };
  const mf = new Miniflare({ cf: false, log: new Log(LogLevel.NONE), workers: [
    { ...common, name: "api", scriptPath: path.join(worker, "entry/api.mjs") },
    { ...common, name: "maintenance", scriptPath: path.join(worker, "entry/maintenance.mjs") },
  ] });
  try {
    const { MAIL_DB: db } = await mf.getBindings("maintenance");
    await applyMigrations(db, path.join(worker, "migrations"));
    const retired = {
      arm(rule) { retiredRule = rule; },
      get deletes() { return retiredDeletes; },
      get present() { return retiredRule !== null; },
    };
    await run({ mf, db, retired });
    assert.equal(unexpected, 0, "only local fixture Routing requests are allowed");
  } finally { await mf.dispose(); }
}

/** Native missing-handler results may be returned as 500 or thrown by workerd. */
async function noFetch(binding) {
  try {
    const response = await binding.fetch("https://synthetic.invalid/never-public");
    assert.equal(response.status, 500, "maintenance must not return a business HTTP response");
  } catch (error) {
    assert.match(String(error), /does not implement.*fetch|no.*fetch.*handler|Handler does not exist|Handler does not export a fetch\(\) function/i);
  }
}

/** Reject the opposite event on each real entry, rather than inspecting source strings. */
test("actual split entries expose only their own application event surface", async () => fixture(async ({ mf }) => {
  await noFetch(await mf.getWorker("maintenance"));
  const response = await (await mf.getWorker("api")).fetch("https://synthetic.invalid/health");
  assert.equal(response.status, 200, "the real Rust fetch dispatcher is still reachable");
  try {
    const disabled = await (await mf.getWorker("api")).scheduled({ cron, scheduledTime: new Date(slot) });
    assert.notEqual(disabled.outcome, "ok", "API must not accept scheduled events");
  } catch (error) {
    assert.match(String(error), /does not implement.*scheduled|no.*scheduled.*handler|Handler does not exist|Handler does not export a scheduled\(\) function/i);
  }
}));

/** One complete native event must finish all cleanup writes before returning. */
test("maintenance completes real Rust work repeatedly without foreground capabilities", async () => fixture(async ({ mf, db }) => {
  for (let turn = 0; turn < 2; turn++) {
    await db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES(?1,'synthetic','synthetic-message','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0)").bind(`split-old-${turn}`).run();
    const result = await (await mf.getWorker("maintenance")).scheduled({ cron, scheduledTime: new Date(slot + turn * 300_000) });
    assert.equal(result.outcome, "ok");
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events").first()).n, 0,
      "returned completion includes the late abuse retention phase");
  }
}));

/** Successful scheduled outcome alone can hide a caught phase capability error. */
test("least-privilege maintenance discovers and prunes retired domain routes", async () => fixture(async ({ mf, db, retired }) => {
  const address = "retired-synthetic@mail-staging.moesegfault.dev";
  const rule = { id: "synthetic-retired-rule", source: "api", enabled: true, name: `amail ${address}`,
    actions: [{ type: "worker", value: ["synthetic-ingress"] }],
    matchers: [{ type: "literal", field: "to", value: address }] };
  await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at,needs_reconcile) VALUES(?1,'retired-synthetic','https://synthetic.invalid','synthetic-owner',0,'retired',0,0)").bind(address).run();
  retired.arm(rule);
  assert.equal((await (await mf.getWorker("maintenance")).scheduled({ cron, scheduledTime: new Date(slot) })).outcome, "ok");
  assert.equal(retired.deletes, 1, "discovery plus useful repair needs the domain capability");
  assert.equal(retired.present, false);
  const row = await db.prepare("SELECT state,needs_reconcile,cf_rule_id FROM addresses WHERE address=?1").bind(address).first();
  assert.equal(row.state, "retired");
  assert.equal(row.needs_reconcile, 0);
  assert.equal(row.cf_rule_id, null);
}));
