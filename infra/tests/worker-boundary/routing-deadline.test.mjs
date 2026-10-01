/** Hosted-only built-Wasm discriminators for Cron Routing deadlines and useful repair. */
import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import { Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const endpoint = "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules";
const domain = "mail-staging.moesegfault.dev";
const addresses = ["routing-first", "routing-second"].map(part => `${part}@${domain}`);
const slot = 1_680_000_000_000;
assert.equal(Math.floor(slot / 300_000) % 8, 0, "addresses must enter first");
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

/** Exact synthetic ownership, including name, destination and enabled state. */
function rule(index) {
  return { id: `routing-rule-${index}`, source: "api", enabled: true,
    name: `amail ${addresses[index]}`,
    actions: [{ type: "worker", value: ["synthetic-ingress"] }],
    matchers: [{ type: "literal", field: "to", value: addresses[index] }] };
}
/** Terminal ten-page proof with 500 unique rules; fillers cannot authorize repair. */
function pages() {
  const rules = [rule(0), rule(1), ...Array.from({ length: 498 }, (_, n) => ({
    id: `unowned-${n}`, source: "api", enabled: true, name: "unowned synthetic fixture",
    actions: [{ type: "worker", value: ["unowned-worker"] }],
    matchers: [{ type: "literal", field: "to", value: `unowned-${n}@example.invalid` }],
  }))];
  return Array.from({ length: 10 }, (_, n) => rules.slice(n * 50, (n + 1) * 50));
}
/** Provider envelope includes count and terminal metadata, not only a short page. */
function inventory(rules, totalPages = 1, totalCount = rules.length) {
  return Response.json({ success: true, result: rules,
    result_info: { total_pages: totalPages, total_count: totalCount } });
}

/** Every case gets fresh native bindings and a strict local stub with no send capability. */
async function fixture(run) {
  let handler, unexpected = 0;
  const calls = [], cleanups = [];
  const mf = new Miniflare({ cf: false, workers: [{
    name: "amail-routing-deadline-synthetic", modules: true,
    scriptPath: path.join(root, "infra/tests/worker-boundary/routing-deadline-observer.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-08-06",
    bindings: { CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      MAIL_DOMAIN: domain, EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    async outboundService(request) {
      const url = new URL(request.url);
      const list = request.method === "GET" && url.origin + url.pathname === endpoint
        && url.searchParams.get("per_page") === "50"
        && /^([1-9]|10)$/.test(url.searchParams.get("page") ?? "")
        && [...url.searchParams].length === 2;
      const item = ["GET", "DELETE"].includes(request.method)
        && url.origin + url.pathname === `${endpoint}/routing-rule-0` && !url.search;
      if (!handler || (!list && !item)) {
        unexpected++;
        throw new Error("unapproved synthetic Routing egress");
      }
      const call = { method: request.method, page: list ? Number(url.searchParams.get("page")) : null };
      calls.push(call);
      return handler(call);
    },
  }] });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    await applyMigrations(db, path.join(root, "crates/mail-worker/migrations"));
    assert.equal((await db.prepare("SELECT state FROM send_policy WHERE scope='global'").first()).state, "held");
    await db.prepare("UPDATE embedding_dependency SET blocked_until=?1 WHERE id=1").bind(Date.now() + 86_400_000).run();
    await db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES('routing-old-event','synthetic-provider','synthetic-message','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0)").run();
    const seed = async (states = ["provisioning", "provisioning"]) => {
      for (const [n, state] of states.entries()) {
        await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at,next_reconcile_at,cf_rule_id) VALUES(?1,?2,'https://synthetic.invalid',?3,0,?4,?5,0,?6)")
          .bind(addresses[n], `routing-${n}`, `synthetic-owner-${n}`, state, n + 1,
            state === "deleting" ? "routing-rule-0" : null).run();
      }
    };
    const rows = () => db.prepare("SELECT address,state,cf_rule_id,next_reconcile_at,needs_reconcile FROM addresses ORDER BY created_at").all().then(value => value.results);
    const tick = async provider => {
      handler = provider;
      calls.length = 0;
      const start = performance.now();
      const result = await (await mf.getWorker()).scheduled({ scheduledTime: new Date(slot) });
      const elapsed = performance.now() - start;
      assert.equal(result.outcome, "ok");
      assert.equal(unexpected, 0, "no SMTP, Identity, redirect, or unapproved provider calls");
      const stats = await (await mf.dispatchFetch("https://synthetic.invalid/routing-stats")).json();
      assert.equal(stats.exchanges.length, calls.length, "observe every native Routing submission");
      assert.ok(calls.length <= 20, "immutable shared call cap");
      assert.ok(stats.laterCleanup >= 1, "later Cron cleanup remains live");
      assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events WHERE event_id='routing-old-event'").first()).n, 0);
      return { stats, elapsed, calls: [...calls] };
    };
    await run({ db, seed, rows, tick, cleanups });
  } finally {
    // This closes Node bridge resources independently; it is not a cancellation oracle.
    for (const cleanup of cleanups) await cleanup();
    await mf.dispose();
  }
}

/** Exact-slot priority release must not erase another actor's lease. */
function priority(stats, expectedAddresses) {
  assert.equal(stats.claims.length, 2);
  assert.ok(stats.claims.every(row => row.due === stats.scanAt + 300_000 && row.expected === stats.scanAt));
  assert.deepEqual(stats.releases.map(row => row.address), expectedAddresses);
  assert.ok(stats.releases.every(row => row.due === stats.scanAt - 1 && row.expected === stats.scanAt + 300_000));
}
/** Production must abort the exact native-fetch signal, not a Node-side source callback. */
function aborted(exchange, acquired = false) {
  assert.equal(exchange.aborts, 1);
  assert.equal(exchange.aborted, 1);
  if (acquired) {
    assert.equal(exchange.acquired, 1);
    assert.ok(exchange.reads >= 2 && exchange.bytes > 0, "prefix received before a pending native body read");
    assert.equal(exchange.cancels, 1);
    assert.equal(exchange.cancelFulfilled + exchange.cancelRejected, 1);
    assert.equal(exchange.releases, 1);
  }
}

test("20-second complete inventory promotes first row once and prioritizes second for fast following turn", { timeout: 90_000 }, async () => fixture(async ({ seed, rows, tick }) => {
  await seed();
  const list = pages();
  const slow = await tick(async ({ method, page }) => {
    assert.equal(method, "GET"); assert.ok(page);
    await sleep(2_000);
    return inventory(list[page - 1], 10, 500);
  });
  assert.ok(slow.elapsed >= 20_000 && slow.elapsed < 35_000, "real slow setup, not a fake clock");
  assert.deepEqual(slow.calls.map(call => call.page), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  assert.equal(slow.stats.addressStatements, 7);
  assert.equal(slow.stats.promotions, 1);
  priority(slow.stats, [addresses[1]]);
  const first = await rows();
  assert.equal(first[0].state, "active"); assert.equal(first[0].cf_rule_id, "routing-rule-0");
  assert.equal(first[1].state, "provisioning"); assert.equal(first[1].next_reconcile_at, slow.stats.scanAt - 1);
  assert.ok(slow.stats.exchanges.every(row => row.aborts === 0 && row.cancels === 0));
  const fast = await tick(({ page }) => { assert.equal(page, 1); return inventory([rule(0), rule(1)]); });
  assert.equal(fast.calls.length, 1);
  assert.equal(fast.stats.claims.length, 1);
  assert.equal(fast.stats.claims[0].address, addresses[1]);
  assert.equal(fast.stats.promotions, 1);
  assert.equal(fast.stats.releases.length, 0);
  assert.equal(fast.stats.addressStatements, 5);
  assert.deepEqual((await rows()).map(row => row.state), ["active", "active"]);
}));

for (const kind of ["headers", "body"]) {
  test(`Cron inventory ${kind} stall aborts within 10 seconds and priority-releases unattempted rows`, { timeout: 40_000 }, async () => fixture(async ({ seed, rows, tick, cleanups }) => {
    await seed();
    const result = await tick(async () => {
      if (kind === "headers") return new Promise(resolve => cleanups.push(() => resolve(inventory([]))));
      // Headers consume three seconds of the SAME ten-second complete-fetch timer.
      await sleep(3_000);
      return new Response(new ReadableStream({ start(controller) {
        controller.enqueue(new TextEncoder().encode('{"success":true,"result":['));
        cleanups.push(() => controller.close());
      } }));
    });
    assert.ok(result.elapsed >= 9_000 && result.elapsed < 16_000, "one total request deadline plus hosted overhead");
    assert.equal(result.calls.length, 1);
    aborted(result.stats.exchanges[0], kind === "body");
    assert.equal(result.stats.promotions, 0);
    assert.equal(result.stats.addressStatements, 5, "SELECT + two claims + two exact-slot releases");
    priority(result.stats, addresses);
    assert.ok((await rows()).every(row => row.state === "provisioning" && row.next_reconcile_at === result.stats.scanAt - 1));
  }));
}

test("ten 3.2-second pages share original 30-second inventory deadline, never partial absence proof", { timeout: 60_000 }, async () => fixture(async ({ seed, rows, tick }) => {
  await seed();
  const list = pages();
  const result = await tick(async ({ method, page }) => {
    assert.equal(method, "GET"); assert.ok(page);
    await sleep(3_200);
    return inventory(list[page - 1], 10, 500);
  });
  assert.ok(result.elapsed >= 29_000 && result.elapsed < 39_000);
  assert.deepEqual(result.calls.map(call => call.page), [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
  aborted(result.stats.exchanges[9]);
  assert.ok(result.stats.exchanges.slice(0, 9).every(row => row.aborts === 0));
  assert.equal(result.stats.promotions, 0);
  assert.equal(result.stats.addressStatements, 5);
  priority(result.stats, addresses);
  assert.ok((await rows()).every(row => row.state === "provisioning" && row.cf_rule_id === null && row.needs_reconcile === 0));
}));

test("accepted DELETE with stalled body retains finite journal lease and converges without another DELETE", { timeout: 40_000 }, async () => fixture(async ({ db, seed, rows, tick, cleanups }) => {
  await seed(["deleting"]);
  let deleted = false, deleteCalls = 0;
  const result = await tick(({ method, page }) => {
    if (page) return inventory([rule(0)]);
    if (method === "GET") return Response.json({ success: true, result: rule(0) });
    assert.equal(method, "DELETE"); deleted = true; deleteCalls++;
    return new Response(new ReadableStream({ start(controller) {
      controller.enqueue(new TextEncoder().encode('{"success":'));
      cleanups.push(() => controller.close());
    } }));
  });
  assert.equal(deleted, true, "synthetic provider accepted the destructive side effect");
  assert.equal(result.calls.length, 3);
  assert.equal(result.stats.addressStatements, 5);
  aborted(result.stats.exchanges[2], true);
  assert.equal(result.stats.releases.length, 0, "an actual failed repair keeps its future retry slot");
  const pending = (await rows())[0];
  assert.equal(pending.state, "deleting");
  assert.equal(pending.next_reconcile_at, result.stats.scanAt + 300_000);
  const absent = ({ method, page }) => { assert.equal(method, "GET"); assert.equal(page, 1); return inventory([]); };
  const immediate = await tick(absent);
  assert.equal(immediate.stats.claims.length, 0);
  assert.equal(immediate.stats.addressStatements, 2);
  assert.equal((await rows())[0].state, "deleting", "no immediate journal retry");
  // Make the finite lease due through setup bindings, without replacing the production clock.
  await db.prepare("UPDATE addresses SET next_reconcile_at=0 WHERE address=?1").bind(addresses[0]).run();
  const settled = await tick(absent);
  assert.equal(settled.stats.addressStatements, 4);
  assert.equal((await rows())[0].state, "retired");
  assert.equal((await rows())[0].cf_rule_id, null);
  assert.equal(deleteCalls, 1, "complete successful inventory settles unknown DELETE outcome");
}));

test("oversized native Routing body stops reads at 256 KiB and cancels/releases its reader", { timeout: 30_000 }, async () => fixture(async ({ seed, rows, tick, cleanups }) => {
  await seed();
  let stopped = false, source, produced = 0;
  cleanups.push(() => { stopped = true; if (source && produced < 2 * 1024 * 1024) source.close(); });
  const result = await tick(() => new Response(new ReadableStream({
    start(controller) { source = controller; },
    async pull(controller) {
      await sleep(2);
      if (stopped) return;
      if (produced >= 2 * 1024 * 1024) { controller.close(); return; }
      controller.enqueue(new TextEncoder().encode("x".repeat(8192))); produced += 8192;
    },
  })));
  const native = result.stats.exchanges[0];
  assert.equal(result.calls.length, 1);
  assert.ok(native.bytes > 262_144);
  assert.equal(native.lateReads, 0);
  assert.equal(native.cancels, 1); assert.equal(native.cancelFulfilled, 1);
  assert.equal(native.cancelRejected, 0); assert.equal(native.releases, 1);
  assert.equal(result.stats.promotions, 0); assert.equal(result.stats.releases.length, 0);
  assert.equal(result.stats.addressStatements, 3);
  assert.ok((await rows()).every(row => row.state === "provisioning" && row.next_reconcile_at === result.stats.scanAt + 300_000));
}));

test("Routing foreign redirect is not followed and cannot authorize any row repair", async () => fixture(async ({ seed, rows, tick }) => {
  await seed();
  const result = await tick(() => new Response("synthetic redirect", { status: 302,
    headers: { location: "https://foreign.invalid/never-contact" } }));
  assert.equal(result.calls.length, 1);
  assert.equal(result.stats.addressStatements, 3);
  assert.equal(result.stats.promotions, 0); assert.equal(result.stats.releases.length, 0);
  assert.ok((await rows()).every(row => row.state === "provisioning" && row.next_reconcile_at === result.stats.scanAt + 300_000));
}));
