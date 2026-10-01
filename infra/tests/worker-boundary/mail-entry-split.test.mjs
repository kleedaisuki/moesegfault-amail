/** Hosted workerd acceptance for the actual worker-build 0.8.5 module graph. */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
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
/** Keep intentional trap logs local rather than spraying error stacks into CI. */
class FixtureLog extends Log {
  constructor(records) { super(LogLevel.DEBUG); this.records = records; }
  logWithLevel(_level, message) { this.records.push(String(message)); }
}

/** Node owns both sides of each independent native service barrier. */
function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

/** A missing hook or event completion fails instead of hanging the hosted job. */
async function bounded(promise, label, milliseconds = 5_000) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(`synthetic ${label} timed out`)), milliseconds);
    })]);
  } finally { clearTimeout(timer); }
}

/** Pending is measured only while the independently owned release is held. */
async function assertPending(promise) {
  let timer;
  try {
    const result = await Promise.race([
      promise.then(() => "settled"),
      new Promise(resolve => { timer = setTimeout(() => resolve("held"), 100); }),
    ]);
    assert.equal(result, "held", "registered background work must keep scheduled dispatch pending");
  } finally { clearTimeout(timer); }
}

/** Fresh local stores and closed egress; no provider or deployed Worker is used. */
async function fixture(run) {
  const records = [];
  let unexpected = 0;
  const gates = Object.fromEntries(["registered", "unregistered"].map(mode =>
    [mode, { arrived: deferred(), release: deferred(), calls: 0 }]));
  const control = async request => {
    const mode = request.url.slice("https://synthetic.invalid/background/".length);
    if (request.method !== "POST" || request.url !== `https://synthetic.invalid/background/${mode}` || !gates[mode]) {
      unexpected++;
      throw new Error("unmatched synthetic lifetime control request");
    }
    const gate = gates[mode];
    assert.equal(++gate.calls, 1, "one detached background operation per armed event");
    gate.arrived.resolve();
    await gate.release.promise;
    return new Response(null, { status: 204 });
  };
  await mkdir(path.join(root, ".temp"), { recursive: true });
  const temp = await mkdtemp(path.join(root, ".temp/mail-entry-split-"));
  // (module (func (export "trap") unreachable)): deliberately independent of Mail.
  const trap = Buffer.from("0061736d0100000001040160000003020100070801047472617000000a05010300000b", "hex");
  await writeFile(path.join(temp, "trap.wasm"), trap);
  await writeFile(path.join(temp, "observer.mjs"), `import trap from "./trap.wasm";
import Observer, { setTrap } from "../../infra/tests/worker-boundary/mail-entry-split-observer.mjs";
setTrap(() => new WebAssembly.Instance(trap).exports.trap());
export default Observer;
`);
  const common = {
    modules: true, modulesRoot: root, modulesRules: workerModuleRules,
    // Harness-supported date; the production config's date is not changed.
    compatibilityDate: "2026-08-06",
    bindings: { CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress", OPENROUTER_EMBEDDING_MODEL: "synthetic-model",
      OPENROUTER_API_KEY: "synthetic-key" },
    d1Databases: { MAIL_DB: "entry-split-shared-db" },
    r2Buckets: { MAIL_BODIES: "entry-split-shared-r2" },
    outboundService(request) {
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") {
        return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
      }
      unexpected++;
      throw new Error("unmatched split fixture egress");
    },
  };
  let mf;
  try {
    mf = new Miniflare({ cf: false, log: new FixtureLog(records), workers: [
      { ...common, name: "api", scriptPath: path.join(worker, "entry/api.mjs") },
      { ...common, name: "maintenance", scriptPath: path.join(worker, "entry/maintenance.mjs") },
      { ...common, name: "observer", scriptPath: path.join(temp, "observer.mjs"),
        bindings: { ...common.bindings, TEST_WAIT_UNTIL_MODE: "registered" },
        serviceBindings: { TEST_CONTROL: control } },
      { ...common, name: "unregistered", scriptPath: path.join(temp, "observer.mjs"),
        bindings: { ...common.bindings, TEST_WAIT_UNTIL_MODE: "unregistered" },
        serviceBindings: { TEST_CONTROL: control } },
    ] });
    const { MAIL_DB: db } = await mf.getBindings("maintenance");
    await applyMigrations(db, path.join(worker, "migrations"));
    await run({ mf, db, records, gates });
    assert.equal(unexpected, 0, "only local fixture Routing GET is allowed");
  } finally {
    for (const gate of Object.values(gates)) gate.release.resolve();
    if (mf) await mf.dispose();
    await rm(temp, { recursive: true, force: true });
  }
}

/** Native missing-handler results may be returned as 500 or thrown by workerd. */
async function noFetch(binding) {
  try {
    const response = await binding.fetch("https://synthetic.invalid/never-public");
    assert.equal(response.status, 500, "maintenance must not return a business HTTP response");
  } catch (error) {
    assert.match(String(error), /does not implement.*fetch|no.*fetch.*handler|Handler does not exist/i);
  }
}

/** Assert runtime export shape, not just adapter source strings or a mock shim. */
test("actual split entries expose only their own application event surface", async () => fixture(async ({ mf }) => {
  const observer = await mf.getWorker("observer");
  const surfaces = await (await observer.fetch("https://synthetic.invalid/surfaces")).json();
  assert.deepEqual(surfaces, {
    api: { exports: ["default"], methods: ["fetch"], directPlatformBase: true },
    maintenance: { exports: ["default"], methods: ["scheduled"], directPlatformBase: true }, traps: 0,
  });
  await noFetch(await mf.getWorker("maintenance"));
  const response = await (await mf.getWorker("api")).fetch("https://synthetic.invalid/health");
  assert.equal(response.status, 200, "the real Rust fetch dispatcher is still reachable");
  try {
    const disabled = await (await mf.getWorker("api")).scheduled({ cron, scheduledTime: new Date(slot) });
    assert.notEqual(disabled.outcome, "ok", "API must not accept scheduled events");
  } catch (error) {
    assert.match(String(error), /does not implement.*scheduled|no.*scheduled.*handler|Handler does not exist/i);
  }
}));

/** One complete native event must finish all cleanup writes before returning. */
test("maintenance completes real Rust work repeatedly without foreground capabilities", async () => fixture(async ({ mf, db }) => {
  for (let turn = 0; turn < 8; turn++) {
    await db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES(?1,'synthetic','synthetic-message','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0)").bind(`split-old-${turn}`).run();
    const result = await (await mf.getWorker("maintenance")).scheduled({ cron, scheduledTime: new Date(slot + turn * 300_000) });
    assert.equal(result.outcome, "ok");
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events").first()).n, 0,
      "returned completion includes the late abuse retention phase");
  }
}));

/** Native controller/Env/context identity survives both adapter and SDK layers. */
test("real shim receives original invocation and retains returned completion", async () => fixture(async ({ mf }) => {
  const observer = await mf.getWorker("observer");
  for (let turn = 0; turn < 2; turn++) {
    const result = await observer.scheduled({ cron, scheduledTime: new Date(slot + turn * 300_000) });
    assert.equal(result.outcome, "ok");
    const lifecycle = await (await observer.fetch("https://synthetic.invalid/lifecycle")).json();
    assert.deepEqual(lifecycle, { sameEvent: true, sameEnv: true, sameContext: true,
      returnsOriginal: true, promise: true, cron, scheduledTime: slot + turn * 300_000 });
  }
}));

/** Omitting waitUntil must change completion while identical background work is held. */
test("native SDK context waitUntil owns detached background lifetime with negative control", async () => fixture(async ({ mf, gates }) => {
  const observer = await mf.getWorker("observer");
  const unregistered = await mf.getWorker("unregistered");
  await observer.fetch("https://synthetic.invalid/arm-background");
  await unregistered.fetch("https://synthetic.invalid/arm-background");
  const positive = observer.scheduled({ cron, scheduledTime: new Date(slot) });
  const negative = unregistered.scheduled({ cron, scheduledTime: new Date(slot) });
  // Keep early event errors observed while acquiring the independent barriers.
  positive.catch(() => {});
  negative.catch(() => {});
  try {
    await bounded(Promise.all(Object.values(gates).map(gate => gate.arrived.promise)), "background arrival");
    const omitted = await bounded(negative, "unregistered completion");
    assert.equal(omitted.outcome, "ok", "unregistered promise cannot extend event lifetime");
    const negativeStats = await (await unregistered.fetch("https://synthetic.invalid/lifecycle")).json();
    assert.equal(negativeStats.backgroundRegistered, false);
    assert.equal(negativeStats.backgroundCompleted, false, "negative control release is still held");
    await assertPending(positive);
    const held = await (await observer.fetch("https://synthetic.invalid/lifecycle")).json();
    assert.equal(held.sameContext, true, "registration occurs on the generated SDK's adapter-provided native context");
    assert.equal(held.backgroundRegistered, true);
    assert.equal(held.backgroundCompleted, false, "registered promise outlives returned Rust completion");
    gates.registered.release.resolve();
    assert.equal((await bounded(positive, "registered completion")).outcome, "ok");
    const finished = await (await observer.fetch("https://synthetic.invalid/lifecycle")).json();
    assert.equal(finished.backgroundCompleted, true, "native dispatch waits for independently released background work");
    assert.equal(finished.backgroundCancelled, false);
  } finally {
    for (const gate of Object.values(gates)) gate.release.resolve();
    await bounded(Promise.allSettled([positive, negative]), "event cleanup");
  }
}));

/** Actual SDK Proxy records a native critical trap and resets on the next event. */
test("real generated SDK reset boundary survives a critical Wasm trap", async () => fixture(async ({ mf, db, records }) => {
  const observer = await mf.getWorker("observer");
  assert.equal((await observer.scheduled({ cron, scheduledTime: new Date(slot) })).outcome, "ok");
  await observer.fetch("https://synthetic.invalid/arm-trap");
  const trapped = await observer.scheduled({ cron, scheduledTime: new Date(slot) });
  assert.notEqual(trapped.outcome, "ok");
  assert.equal((await (await observer.fetch("https://synthetic.invalid/surfaces")).json()).traps, 1);
  await db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES('after-reset','synthetic','synthetic-message','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0)").run();
  const recovered = await observer.scheduled({ cron, scheduledTime: new Date(slot + 300_000) });
  assert.equal(recovered.outcome, "ok", "restored handler executes actual Rust after SDK reset");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events").first()).n, 0);
  assert.equal(records.filter(record => record.includes("Reinitializing Wasm application")).length, 1,
    "assert the actual generated reset path, not just a successful later call");
}));

/** Both production adapters resolve the same generated alias and immutable Wasm. */
test("entry adapters share the single module-mode build artifact", async () => {
  const alias = await readFile(path.join(worker, "build/worker/shim.mjs"), "utf8");
  assert.match(alias, /export \{ default \} from ['"]\.\.\/index\.js['"]/);
  const wasm = await readFile(path.join(worker, "build/index_bg.wasm"));
  const digest = createHash("sha256").update(wasm).digest("hex");
  for (const entry of ["api", "maintenance"]) {
    const source = await readFile(path.join(worker, `entry/${entry}.mjs`), "utf8");
    assert.match(source, /from ["']\.\.\/build\/worker\/shim\.mjs["']/);
    assert.equal(createHash("sha256").update(await readFile(path.join(worker, "build/index_bg.wasm"))).digest("hex"), digest);
  }
});
