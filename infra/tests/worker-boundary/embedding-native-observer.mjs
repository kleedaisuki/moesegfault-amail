/** Test-only observer of native APIs, scoped to the single synthetic OpenRouter exchange. */
import { WorkerEntrypoint } from "cloudflare:workers";
import MailApi from "../../../crates/mail-worker/entry/api.mjs";
import MailMaintenance from "../../../crates/mail-worker/entry/maintenance.mjs";

const endpoint = "https://openrouter.ai/api/v1/embeddings";
const streams = new WeakSet();
const readers = new WeakSet();
const signals = new WeakSet();
const stats = { exchanges: 0, reads: 0, bytes: 0, lateReads: 0,
  cancelCalls: 0, cancelFulfilled: 0, cancelRejected: 0, abortCalls: 0, abortedSignals: 0 };
const nativeFetch = globalThis.fetch;
globalThis.fetch = async function(input, init) {
  const url = typeof input === "string" ? input : input.url;
  if (url !== endpoint) return nativeFetch.call(this, input, init);
  stats.exchanges++;
  if (init?.signal) signals.add(init.signal);
  const response = await nativeFetch.call(this, input, init);
  if (response.body) streams.add(response.body);
  return response;
};

const nativeGetReader = ReadableStream.prototype.getReader;
ReadableStream.prototype.getReader = function(...args) {
  const reader = nativeGetReader.apply(this, args);
  if (streams.has(this)) readers.add(reader);
  return reader;
};
const probe = new ReadableStream().getReader();
const readerPrototype = Object.getPrototypeOf(probe);
probe.releaseLock();
const nativeRead = readerPrototype.read;
readerPrototype.read = async function(...args) {
  if (!readers.has(this)) return nativeRead.apply(this, args);
  stats.reads++;
  if (stats.bytes > 65_536 || stats.cancelCalls > 0) stats.lateReads++;
  const result = await nativeRead.apply(this, args);
  if (!result.done) stats.bytes += result.value.byteLength;
  return result;
};
const nativeCancel = readerPrototype.cancel;
readerPrototype.cancel = async function(...args) {
  if (!readers.has(this)) return nativeCancel.apply(this, args);
  stats.cancelCalls++;
  try {
    const result = await nativeCancel.apply(this, args);
    stats.cancelFulfilled++;
    return result;
  } catch (error) {
    stats.cancelRejected++;
    throw error;
  }
};
const nativeAbort = AbortController.prototype.abort;
AbortController.prototype.abort = function(...args) {
  const tracked = signals.has(this.signal);
  if (tracked) stats.abortCalls++;
  const result = nativeAbort.apply(this, args);
  if (tracked && this.signal.aborted) stats.abortedSignals++;
  return result;
};

/** Logical late-claim policy exists only in this synthetic observer module. */
const nativeNow = Date.now;
let offset = 0;
let claimJumpMs = 0;
Date.now = () => nativeNow() + offset;

/** Preserve actual D1 calls; shift the clock only after the fenced active-row read. */
function cronDatabase(native) {
  return new Proxy(native, {
    get(target, field) {
      if (field === "constructor") return target.constructor;
      if (field === "prepare") return sql => {
        const statement = target.prepare(sql);
        const wrap = current => new Proxy(current, {
          get(inner, name) {
            if (name === "constructor") return inner.constructor;
            if (name === "bind") return (...args) => wrap(inner.bind(...args));
            if (name === "first") return async (...args) => {
              const result = await inner.first(...args);
              if (sql.includes("SELECT m.subject,m.body_text,w.attempts")) offset += claimJumpMs;
              return result;
            };
            const value = Reflect.get(inner, name, inner);
            return typeof value === "function" ? value.bind(inner) : value;
          },
        });
        return wrap(statement);
      };
      const value = Reflect.get(target, field, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

/** Fixture-only dual surface delegates to the actual independently owned adapters. */
export default class EmbeddingNativeObserver extends WorkerEntrypoint {
  constructor(ctx, env) { super(ctx, { ...env, MAIL_DB: cronDatabase(env.MAIL_DB) }); }
  scheduled(event) { return new MailMaintenance(this.ctx, this.env).scheduled(event); }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/cron-policy") {
      ({ claimJumpMs = 0 } = await request.json());
      return new Response(null, { status: 204 });
    }
    if (request.url === "https://synthetic.invalid/embedding-stats") return Response.json(stats);
    const response = await new MailApi(this.ctx, this.env).fetch(request);
    const headers = new Headers(response.headers);
    for (const [name, value] of Object.entries(stats)) {
      headers.set(`x-synthetic-native-${name.toLowerCase()}`, String(value));
    }
    return new Response(response.body, { status: response.status, headers });
  }
}
