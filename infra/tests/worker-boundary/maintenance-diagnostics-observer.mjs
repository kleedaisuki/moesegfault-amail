/** Synthetic native-boundary observer; production receives no fixture policy. */
import BuiltWorker from "../../../crates/mail-worker/build/worker/shim.mjs";

const nativeStatements = new WeakMap();
let policy = {}, stats, offset = 0;
/** Invocation tape contains dependency categories only, never SQL/binds/body. */
function reset() {
  offset = 0;
  stats = { tape: [], phases: [], statements: 0, lookups: 0, send: 0, batches: 0,
    forwarded: 0, settled: 0, constructor: null, codes: [], lengths: [], charge: 0,
    envelopeBytes: 0, valid: true };
}
reset();

/** Match first submissions only; eight terminal slots are independently unit-tested. */
function phaseOf(sql) {
  if (/SELECT address,state,cf_rule_id,created_at FROM addresses/.test(sql)) return "addresses";
  if (/UPDATE send_requests SET state='preparing',reservation_started_at=NULL/.test(sql)) return "outbound";
  if (/SELECT blocked_until FROM embedding_dependency/.test(sql)) return "embeddings";
  if (/UPDATE storage_reservations SET state='indexed' WHERE state='reserved'/.test(sql)) return "storage";
  if (/SELECT id,r2_key FROM messages WHERE deleted_at IS NOT NULL/.test(sql)) return "deleted";
  if (/SELECT r.id FROM storage_reservations r LEFT JOIN messages/.test(sql)) return "orphans";
  if (/DELETE FROM search_jobs WHERE state='preparing'/.test(sql)) return "search";
  if (/UPDATE send_requests SET sender=NULL,envelope_json=NULL/.test(sql)) return "abuse";
  return null;
}

/** Real D1 submission with explicit synthetic failure/delay/clock injection. */
async function submit(target, sql, method, args) {
  stats.tape.push("d1");
  stats.statements++;
  const phase = phaseOf(sql);
  if (phase && !stats.phases.includes(phase)) stats.phases.push(phase);
  if (policy.delayMs) await new Promise(resolve => setTimeout(resolve, policy.delayMs));
  if (policy.jumpFirst && stats.statements === 1) offset += policy.jumpFirst;
  if (policy.jumpEach) offset += policy.jumpEach;
  if (phase && policy.failPhases?.includes(phase)) throw new Error("SYNTHETIC_PRIVATE_D1_FAILURE");
  return target[method](...args);
}

/** Preserve D1 constructor, bound native receiver and real batch atomicity. */
function statement(native, sql) {
  const proxy = new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "bind") return (...values) => statement(target.bind(...values), sql);
    if (["first", "all", "run"].includes(key)) return (...args) => submit(target, sql, key, args);
    throw new Error("unsupported synthetic statement operation");
  } });
  nativeStatements.set(proxy, native);
  return proxy;
}

/** Setup/readback bindings are unobserved; only production invocation is wrapped. */
function database(native) {
  return new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "prepare") return sql => statement(target.prepare(sql), sql);
    if (key === "batch") return statements => {
      stats.tape.push("d1");
      stats.statements += statements.length;
      if (statements.some(value => !nativeStatements.has(value))) throw new Error("unobserved native batch");
      return target.batch(statements.map(value => nativeStatements.get(value)));
    };
    throw new Error("unsupported synthetic D1 operation");
  } });
}

/** Observe R2 business submissions without replacing object readers. */
function bucket(native) {
  return new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    const value = target[key];
    if (typeof value !== "function") return value;
    return (...args) => { stats.tape.push("r2"); return value.apply(target, args); };
  } });
}

const phaseCodes = ["routing_reconciliation_failed", "outbound_reconciliation_failed",
  "semantic_index_retry_failed", "storage_ledger_reconciliation_failed", "deleted_message_cleanup_failed",
  "orphan_object_cleanup_failed", "search_job_cleanup_failed", "abuse_data_cleanup_failed"];
const deepCodes = ["address_reconciliation_batch_full", "non_enabled_committed_routing_rule",
  "non_enabled_provisioning_routing_rule", "semantic_document_quarantined", "semantic_provider_cooldown"];
const deferrals = ["maintenance_budget_deferred", "maintenance_deadline_deferred"];
const fields = ["schema_version", "event_id", "service", "operation", "phase", "trace_id", "span_id",
  "request_id", "outcome", "error_code", "duration_ms_bucket", "diagnostic_code"].sort();
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** Independent wire shape and bytes agree with Rust's literal-schema unit check. */
function inspect(body) {
  const code = body?.diagnostic_code;
  const error = deferrals.includes(code) ? "resource_deferred" : "dependency_failure";
  const expected = { schema_version: 1, event_id: "00000000-0000-4000-8000-000000000001",
    service: "mail_api", operation: "maintenance", phase: "maintenance",
    trace_id: "0123456789abcdef0123456789abcdef", span_id: "0123456789abcdef",
    request_id: "00000000-0000-4000-8000-000000000001", outcome: "phase_failure",
    error_code: error, duration_ms_bucket: 0, diagnostic_code: code };
  const length = new TextEncoder().encode(JSON.stringify(body)).byteLength;
  const valid = JSON.stringify(Object.keys(body).sort()) === JSON.stringify(fields)
    && [...phaseCodes, ...deepCodes, ...deferrals].includes(code)
    && body.schema_version === 1 && body.service === "mail_api" && body.operation === "maintenance"
    && body.phase === "maintenance" && body.outcome === "phase_failure" && body.error_code === error
    && body.duration_ms_bucket === 0 && uuid.test(body.event_id) && uuid.test(body.request_id)
    && /^[0-9a-f]{32}$/.test(body.trace_id) && !/^0+$/.test(body.trace_id)
    && /^[0-9a-f]{16}$/.test(body.span_id) && !/^0+$/.test(body.span_id)
    && length === new TextEncoder().encode(JSON.stringify(expected)).byteLength && length <= 1024;
  stats.valid &&= valid;
  stats.codes.push(code);
  stats.lengths.push(length);
}

/** Keep real WorkerQueue constructor/prototype and native method receiver. */
function queue(native) {
  if (!native) return undefined;
  return new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "send") return (...args) => { stats.send++; return target.send(...args); };
    if (key !== "sendBatch") return target[key];
    return (messages, options) => {
      stats.tape.push("queue");
      stats.batches++;
      stats.constructor = target.constructor.name;
      const rows = Array.from(messages);
      for (const row of rows) {
        stats.valid &&= row.contentType === "json" && (row.delaySeconds === undefined || row.delaySeconds === null);
        inspect(row.body);
      }
      stats.charge = 2 + stats.lengths.reduce((sum, length) => sum + length, 0)
        + Math.max(rows.length - 1, 0) + 4096 + 512 * rows.length;
      stats.envelopeBytes = new TextEncoder().encode(JSON.stringify(rows)).byteLength;
      if (policy.queueMode === "throw") throw new Error("SYNTHETIC_PRIVATE_QUEUE_FAILURE");
      if (policy.queueMode === "reject") return Promise.reject(new Error("SYNTHETIC_PRIVATE_QUEUE_FAILURE"));
      const forward = () => {
        stats.forwarded++;
        return target.sendBatch(rows, options).then(value => { stats.settled++; return value; });
      };
      if (policy.queueDelayMs) return new Promise(resolve => setTimeout(resolve, policy.queueDelayMs)).then(forward);
      return forward();
    };
  } });
}

/** No production HTTP requests; fixture control remains synthetic-only. */
export default class MaintenanceDiagnosticsObserver extends BuiltWorker {
  constructor(ctx, env) {
    const nativeQueue = queue(env.TRACE_EVENTS);
    const wrapped = { ...env, MAIL_DB: database(env.MAIL_DB), MAIL_BODIES: bucket(env.MAIL_BODIES) };
    super(ctx, new Proxy(wrapped, { get(target, key) {
      if (key !== "TRACE_EVENTS") return target[key];
      stats.tape.push("lookup");
      stats.lookups++;
      return policy.queueMode === "wrong" ? {} : nativeQueue;
    } }));
  }
  async scheduled(event) {
    reset();
    const original = Date.now;
    Date.now = () => original() + offset;
    try { return await super.scheduled(event); }
    finally { Date.now = original; }
  }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/diagnostics-policy") {
      policy = await request.json();
      return Response.json({ configured: true });
    }
    if (request.url === "https://synthetic.invalid/diagnostics-stats") return Response.json(stats);
    throw new Error("no production HTTP surface in diagnostics fixture");
  }
}
