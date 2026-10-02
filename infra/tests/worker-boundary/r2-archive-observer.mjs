/** Test-only native R2 observer: production Rust/shim is imported unchanged. */
import MailMaintenance from "../../../crates/mail-worker/entry/maintenance.mjs";

const cap = 5 * 1024 * 1024;
const stats = { gets: 0, reads: 0, cancels: 0, arrayBuffers: 0 };

/** Forge metadata/body disagreement only on explicitly named synthetic objects. */
async function object(native, key) {
  let chunks;
  if (key.includes("archive-single")) chunks = [new Uint8Array(cap + 1), new Uint8Array(1)];
  else if (key.includes("archive-total")) chunks = [new Uint8Array(cap - 8), new Uint8Array(16), new Uint8Array(1)];
  else chunks = [new Uint8Array(1)];
  const stream = new ReadableStream({
    /** Zero high-water mark prevents eager test producer reads before admission. */
    async pull(controller) {
      stats.reads++;
      if (chunks.length) controller.enqueue(chunks.shift());
      else controller.close();
    },
    /** Both stream and reader cancellation must stop subsequent synthetic pulls. */
    cancel() {
      stats.cancels++; chunks = [];
    },
  }, { highWaterMark: 0 });
  return new Proxy(native, {
    get(target, field) {
      if (field === "size") {
        return key.includes("archive-metadata") ? cap + 1 : 1;
      }
      if (field === "body") return stream;
      if (field === "bodyUsed") return false;
      if (field === "arrayBuffer") return () => {
        stats.arrayBuffers++;
        throw new Error("production must not buffer a synthetic R2 body before its cap");
      };
      const value = Reflect.get(target, field, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

/** Preserve native R2 constructor and operations except the retained read body. */
function bucket(native) {
  return new Proxy(native, {
    get(target, field) {
      if (field === "constructor") return target.constructor;
      if (field === "get") return async (...args) => {
        stats.gets++;
        const result = await target.get(...args);
        if (!result || !String(args[0]).includes("archive-")) return result;
        return object(result, String(args[0]));
      };
      const value = Reflect.get(target, field, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

/** Isolated fixture hook; no production env flags, endpoints or service are added. */
export default class R2ArchiveObserver extends MailMaintenance {
  constructor(ctx, env) { super(ctx, { ...env, MAIL_BODIES: bucket(env.MAIL_BODIES) }); }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/r2-stats") return Response.json(stats);
    throw new Error("no application HTTP surface in maintenance observer");
  }
}
