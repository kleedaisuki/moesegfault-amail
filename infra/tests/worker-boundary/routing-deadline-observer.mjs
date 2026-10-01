/** Test-only native Routing and SQL observations; never supplies production policy. */
import BuiltWorker from "../../../crates/mail-worker/build/worker/shim.mjs";

const endpoint = "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules";
const signals = new WeakMap(), streams = new WeakMap(), readers = new WeakMap();
const statements = new WeakMap();
let stats;
/** Each scheduled invocation starts a fresh evidence ledger, excluding setup/readback. */
function reset() {
  stats = { exchanges: [], scanAt: null, claims: [], releases: [], promotions: 0,
    addressStatements: 0, laterCleanup: 0 };
}
reset();

const nativeFetch = globalThis.fetch;
globalThis.fetch = async function(input, init) {
  const url = typeof input === "string" ? input : input.url;
  if (url !== endpoint && !url.startsWith(`${endpoint}?`) && !url.startsWith(`${endpoint}/`)) {
    return nativeFetch.call(this, input, init);
  }
  const row = { reads: 0, bytes: 0, lateReads: 0, acquired: 0, cancels: 0,
    cancelFulfilled: 0, cancelRejected: 0, releases: 0, aborts: 0, aborted: 0 };
  stats.exchanges.push(row);
  if (init?.signal) signals.set(init.signal, row);
  const response = await nativeFetch.call(this, input, init);
  if (response.body) streams.set(response.body, row);
  return response;
};
const nativeGetReader = ReadableStream.prototype.getReader;
ReadableStream.prototype.getReader = function(...args) {
  const reader = nativeGetReader.apply(this, args);
  const row = streams.get(this);
  if (row) { row.acquired++; readers.set(reader, row); }
  return reader;
};
const probe = new ReadableStream().getReader();
const prototype = Object.getPrototypeOf(probe);
probe.releaseLock();
const nativeRead = prototype.read;
prototype.read = async function(...args) {
  const row = readers.get(this);
  if (!row) return nativeRead.apply(this, args);
  row.reads++;
  if (row.bytes > 262_144 || row.cancels) row.lateReads++;
  const result = await nativeRead.apply(this, args);
  if (!result.done) row.bytes += result.value.byteLength;
  return result;
};
const nativeCancel = prototype.cancel;
prototype.cancel = async function(...args) {
  const row = readers.get(this);
  if (!row) return nativeCancel.apply(this, args);
  row.cancels++;
  try { const result = await nativeCancel.apply(this, args); row.cancelFulfilled++; return result; }
  catch (error) { row.cancelRejected++; throw error; }
};
const nativeRelease = prototype.releaseLock;
prototype.releaseLock = function(...args) {
  const row = readers.get(this);
  const result = nativeRelease.apply(this, args);
  if (row) row.releases++;
  return result;
};
const nativeAbort = AbortController.prototype.abort;
AbortController.prototype.abort = function(...args) {
  const row = signals.get(this.signal);
  if (row) row.aborts++;
  const result = nativeAbort.apply(this, args);
  if (row && this.signal.aborted) row.aborted++;
  return result;
};

/** Count actual native submissions, retaining SQL values only for fixed synthetic rows. */
function observe(sql, args) {
  if (/\baddresses\b/.test(sql)) stats.addressStatements++;
  if (/SELECT address,state,cf_rule_id,created_at FROM addresses/.test(sql) && stats.scanAt === null) stats.scanAt = args[0];
  if (/UPDATE addresses SET next_reconcile_at=\?1/.test(sql)) {
    const row = { due: args[0], address: args[1], expected: args[3] };
    if (args[0] === stats.scanAt - 1) stats.releases.push(row);
    else stats.claims.push(row);
  }
  if (/UPDATE addresses SET state='active',cf_rule_id=/.test(sql)) stats.promotions++;
  if (/DELETE FROM provider_events/.test(sql)) stats.laterCleanup++;
}
/** Preserve native constructor identity and statement/batch transaction behavior. */
function statement(native, sql, args = []) {
  const proxy = new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "bind") return (...values) => statement(target.bind(...values), sql, values);
    if (["first", "all", "run"].includes(key)) return (...values) => {
      observe(sql, args);
      return target[key](...values);
    };
    throw new Error(`unsupported synthetic Routing statement method: ${String(key)}`);
  } });
  statements.set(proxy, { native, sql, args });
  return proxy;
}
/** Setup uses original Miniflare bindings; only the production invocation is wrapped. */
function database(native) {
  return new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "prepare") return sql => statement(target.prepare(sql), sql);
    if (key === "batch") return values => {
      const rows = values.map(value => statements.get(value));
      if (rows.some(value => !value)) throw new Error("unobserved synthetic Routing batch");
      for (const row of rows) observe(row.sql, row.args);
      return target.batch(rows.map(row => row.native));
    };
    throw new Error(`unsupported synthetic Routing database method: ${String(key)}`);
  } });
}

/** Forward unchanged built Wasm; the only HTTP surface returns synthetic counters. */
export default class RoutingDeadlineObserver extends BuiltWorker {
  constructor(ctx, env) { super(ctx, { ...env, MAIL_DB: database(env.MAIL_DB) }); }
  async scheduled(event) { reset(); return super.scheduled(event); }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/routing-stats") return Response.json(stats);
    throw new Error("no production HTTP surface in synthetic Routing fixture");
  }
}
