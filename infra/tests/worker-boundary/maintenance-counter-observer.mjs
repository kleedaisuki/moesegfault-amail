/** Test-only submission counter around unchanged built Rust/Wasm + native D1. */
import BuiltWorker from "../../../crates/mail-worker/build/worker/shim.mjs";

const nativeStatements = new WeakMap();
const stats = { statements: 0, individual: 0, batchCalls: 0, batchStatements: 0, unsupported: 0 };

/** Unsupported submission paths cannot silently escape this independent counter. */
function unsupported() {
  stats.unsupported++;
  throw new Error("synthetic D1 observer unsupported binding method");
}

/** Count actual invocation of a binding executor, never prepare/bind/result work. */
function statement(native) {
  const proxy = new Proxy(native, {
    get(target, key) {
      if (key === "constructor") return target.constructor;
      if (key === "bind") return (...args) => statement(target.bind(...args));
      if (["first", "all", "run"].includes(key)) return (...args) => {
        stats.statements++;
        stats.individual++;
        return target[key](...args);
      };
      return unsupported();
    },
  });
  nativeStatements.set(proxy, native);
  return proxy;
}

/** Unwrap observed statements for real native ordered/transactional D1 batch. */
function database(native) {
  return new Proxy(native, {
    get(target, key) {
      if (key === "constructor") return target.constructor;
      if (key === "prepare") return sql => statement(target.prepare(sql));
      if (key === "batch") return statements => {
        if (!Array.isArray(statements) || statements.some(value => !nativeStatements.has(value))) return unsupported();
        stats.statements += statements.length;
        stats.batchStatements += statements.length;
        stats.batchCalls++;
        return target.batch(statements.map(value => nativeStatements.get(value)));
      };
      return unsupported();
    },
  });
}

/** Only fresh synthetic fixture invocations can observe these numeric counters. */
export default class MaintenanceCounterObserver extends BuiltWorker {
  constructor(ctx, env) { super(ctx, { ...env, MAIL_DB: database(env.MAIL_DB) }); }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/d1-stats") return Response.json(stats);
    return super.fetch(request);
  }
}
