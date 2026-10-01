/** Test-only native batch observer; production receives no test-policy switches. */
import { WorkerEntrypoint } from "cloudflare:workers";
import MailApi from "../../../crates/mail-worker/entry/api.mjs";
import MailMaintenance from "../../../crates/mail-worker/entry/maintenance.mjs";

const nativeStatements = new WeakMap();
let policy = {}, stats;

/** Retain numeric submission evidence only; setup/readback bypass this wrapper. */
function reset() {
  stats = { statements: 0, individual: 0, batches: 0, chunkRuns: 0, stage: [], publication: 0 };
}
reset();

/** Preserve bound native statements and their test-local classification metadata. */
function statement(native, sql, args = []) {
  const proxy = new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "bind") return (...values) => statement(target.bind(...values), sql, values);
    if (["first", "all", "run"].includes(key)) return (...values) => {
      stats.statements++;
      stats.individual++;
      if (/INSERT INTO message_text_chunks/.test(sql)) stats.chunkRuns++;
      return target[key](...values);
    };
    throw new Error("unsupported synthetic stage statement method");
  } });
  nativeStatements.set(proxy, { native, sql, args });
  return proxy;
}

/** A deterministic await boundary carries only stage/publication ordinal numbers. */
async function barrier(control, kind, call) {
  const response = await control.fetch(`https://test.invalid/${kind}`, {
    method: "POST", body: JSON.stringify({ call }),
  });
  if (!response.ok) throw new Error("synthetic stage barrier failed");
}

/** Submit one actual native transaction, never replace it with individual runs. */
function database(native, control) {
  return new Proxy(native, { get(target, key) {
    if (key === "constructor") return target.constructor;
    if (key === "prepare") return sql => statement(target.prepare(sql), sql);
    if (key === "batch") return async statements => {
      if (!Array.isArray(statements) || !statements.length || statements.some(value => !nativeStatements.has(value))) throw new Error("unobserved or empty synthetic batch");
      const members = statements.map(value => nativeStatements.get(value));
      const chunks = members.filter(value => /INSERT INTO message_text_chunks/.test(value.sql));
      if (chunks.length && chunks.length !== members.length) throw new Error("mixed stage transaction");
      const publication = members.some(value => /INSERT INTO messages\(/.test(value.sql));
      const stageCall = chunks.length ? stats.stage.length + 1 : 0;
      if (publication && policy.pausePublication) await barrier(control, "before-publication", ++stats.publication);
      stats.statements += members.length;
      stats.batches++;
      if (chunks.length) stats.stage.push({
        size: chunks.length, first: chunks[0].args[10], last: chunks.at(-1).args[10],
        bytes: chunks.reduce((sum, value) => sum + new TextEncoder().encode(value.args[11]).byteLength, 0),
        commonClock: chunks.every(value => value.args[9] === chunks[0].args[9]),
      });
      const result = await target.batch(members.map(value => value.native));
      if (stageCall === policy.rejectAfterStage) throw new Error("synthetic ambiguous committed stage return");
      if (stageCall === policy.shortAfterStage) return result.slice(1);
      if (stageCall === policy.falseAfterStage) return result.map((value, index) => index ? value : { ...value, success: false });
      if (stageCall === policy.pauseAfterStage) await barrier(control, "after-stage", stageCall);
      return result;
    };
    throw new Error("unsupported synthetic stage database method");
  } });
}

/** The real compiled Rust HTTP and Cron handlers retain all business contracts. */
export default class AcceptedStageObserver extends WorkerEntrypoint {
  constructor(ctx, env) { super(ctx, { ...env, MAIL_DB: database(env.MAIL_DB, env.TEST_CONTROL) }); }
  /** Exercise the actual scheduled-only adapter with the same observed native state. */
  scheduled(event) { return new MailMaintenance(this.ctx, this.env).scheduled(event); }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/stage-policy") {
      policy = await request.json();
      reset();
      return Response.json({ configured: true });
    }
    if (request.url === "https://synthetic.invalid/stage-stats") return Response.json(stats);
    return new MailApi(this.ctx, this.env).fetch(request);
  }
}
