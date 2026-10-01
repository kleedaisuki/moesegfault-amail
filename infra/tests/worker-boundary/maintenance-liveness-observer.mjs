/** Test-only native binding observer; production code receives no test policy knobs. */
import BuiltWorker from "../../../crates/mail-worker/build/worker/shim.mjs";

const nativeStatements = new WeakMap();
let policy = {}, stats, offset = 0;
/** Reset invocation evidence without intercepting fixture setup bindings. */
function reset() {
  offset = 0;
  stats = { phases: [], due: [], r2: [], chunks: 0, stageBatches: [], setup: 0, afterCutoff: [] };
}
reset();

/** Recognize only the first business submission of each production phase. */
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

/** Record executed statements, not speculative prepare/bind calls. */
async function submit(native, sql, args, method, values) {
  const phase = phaseOf(sql);
  if (phase && !stats.phases.includes(phase)) stats.phases.push(phase);
  const chunk = /INSERT INTO message_text_chunks/.test(sql);
  if (/UPDATE send_requests SET index_next_attempt_at=/.test(sql)) stats.due.push(args[1]);
  if (phase === "outbound") stats.setup++;
  if (offset >= 115_000) stats.afterCutoff.push({ phase, chunk });
  if (chunk && policy.chunkDelayMs) await new Promise(resolve => setTimeout(resolve, policy.chunkDelayMs));
  const result = await native[method](...values);
  if (chunk && ++stats.chunks === policy.jumpAtChunk) offset += policy.chunkJumpMs;
  if (phase === "outbound" && policy.setupJumpMs) offset += policy.setupJumpMs;
  // Consume headroom inside the admitted first addresses phase, before
  // outbound can enter; existing addresses work retains its entitlement.
  if (phase === "addresses" && policy.addressJumpMs && stats.phases.length === 1 && !stats.addressJumped) {
    stats.addressJumped = true;
    offset += policy.addressJumpMs;
  }
  return result;
}

/** Preserve real native SQL execution and batch transaction semantics. */
function statement(native, sql, args = []) {
  const proxy = new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "bind") return (...values) => statement(target.bind(...values), sql, values);
    if (["first", "all", "run"].includes(key)) return (...values) => submit(target, sql, args, key, values);
    throw new Error(`unsupported synthetic statement method: ${String(key)}`);
  } });
  nativeStatements.set(proxy, { native, sql, args });
  return proxy;
}

/** Wrap only invocation bindings; seed/readback never passes this observer. */
function database(native) {
  return new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "prepare") return sql => statement(target.prepare(sql), sql);
    if (key === "batch") return async statements => {
      if (statements.some(value => !nativeStatements.has(value))) throw new Error("unobserved batch statement");
      const members = statements.map(value => nativeStatements.get(value));
      const chunks = members.filter(value => /INSERT INTO message_text_chunks/.test(value.sql));
      if (chunks.length && chunks.length !== members.length) throw new Error("mixed synthetic stage batch");
      if (offset >= 115_000) members.forEach(() => stats.afterCutoff.push({ phase: null, chunk: chunks.length > 0, publication: chunks.length === 0 }));
      if (chunks.length && policy.chunkDelayMs) await new Promise(resolve => setTimeout(resolve, policy.chunkDelayMs * chunks.length));
      if (chunks.length && policy.stageCallDelayMs) await new Promise(resolve => setTimeout(resolve, policy.stageCallDelayMs));
      // One real native batch, not an array of individual run() calls: preserve
      // ordered transactional rollback while observing every submitted member.
      const result = await target.batch(members.map(value => value.native));
      if (chunks.length) {
        const before = stats.chunks;
        stats.chunks += chunks.length;
        stats.stageBatches.push(chunks.length);
        if (before < policy.jumpAtChunk && stats.chunks >= policy.jumpAtChunk) offset += policy.chunkJumpMs;
      }
      return result;
    };
    throw new Error(`unsupported synthetic database method: ${String(key)}`);
  } });
}

/** Observe native object access without changing stream or bounded reader behavior. */
function bucket(native) {
  return new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    const value = target[key];
    if (typeof value !== "function") return value;
    return (...args) => {
      stats.r2.push({ method: String(key), key: args[0] });
      return value.apply(target, args);
    };
  } });
}

/** Invocation-local fake clock is restored even when production work fails. */
export default class MaintenanceLivenessObserver extends BuiltWorker {
  constructor(ctx, env) { super(ctx, { ...env, MAIL_DB: database(env.MAIL_DB), MAIL_BODIES: bucket(env.MAIL_BODIES) }); }
  async scheduled(event) {
    reset();
    const original = Date.now;
    Date.now = () => original() + offset;
    try { return await super.scheduled(event); }
    finally { Date.now = original; }
  }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/liveness-policy") {
      policy = await request.json();
      return Response.json({ configured: true });
    }
    if (request.url === "https://synthetic.invalid/liveness-stats") return Response.json(stats);
    throw new Error("no production HTTP surface in synthetic liveness fixture");
  }
}
