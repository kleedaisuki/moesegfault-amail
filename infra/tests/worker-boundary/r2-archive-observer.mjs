/** Test-only native R2 observer: production Rust/shim is imported unchanged. */
import BuiltWorker from "../../../crates/mail-worker/build/worker/shim.mjs";

const cap = 5 * 1024 * 1024;
const nativeNow = Date.now;
let offset = 0;
Date.now = () => nativeNow() + offset;
const stats = { gets: 0, reads: 0, cancels: 0, arrayBuffers: 0 };

/** Forge metadata/body disagreement only on explicitly named synthetic objects. */
async function object(native, key) {
  let chunks;
  if (key.includes("archive-slow-valid")) {
    const bytes = new Uint8Array(await native.arrayBuffer());
    const width = Math.ceil(bytes.length / 66);
    chunks = Array.from({ length: 66 }, (_, n) => bytes.slice(n * width, (n + 1) * width));
  } else if (key.includes("archive-single")) chunks = [new Uint8Array(cap + 1), new Uint8Array(1)];
  else if (key.includes("archive-total")) chunks = [new Uint8Array(cap - 8), new Uint8Array(16), new Uint8Array(1)];
  else chunks = [new Uint8Array(1)];
  const stream = new ReadableStream({
    /** Zero high-water mark prevents eager test producer reads before admission. */
    async pull(controller) {
      if (key.includes("archive-stall")) {
        stats.reads++;
        return new Promise(() => {});
      }
      if (key.includes("archive-slow-valid") && chunks.length) {
        await new Promise(resolve => setTimeout(resolve, 300));
      }
      stats.reads++;
      if (chunks.length) controller.enqueue(chunks.shift());
      else controller.close();
    },
    /** Both stream and reader cancellation must stop subsequent synthetic pulls. */
    cancel() {
      stats.cancels++; chunks = [];
      if (key.includes("archive-cancel-stall")) return new Promise(() => {});
    },
  }, { highWaterMark: 0 });
  return new Proxy(native, {
    get(target, field) {
      if (field === "size") {
        if (key.includes("archive-slow-valid")) return native.size;
        return key.includes("archive-metadata") || key.includes("archive-cancel-stall") ? cap + 1 : 1;
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
        if (String(args[0]).includes("archive-late-get")) offset += 35_000;
        return object(result, String(args[0]));
      };
      const value = Reflect.get(target, field, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

/** Isolated fixture hook; no production env flags, endpoints or service are added. */
export default class R2ArchiveObserver extends BuiltWorker {
  constructor(ctx, env) { super(ctx, { ...env, MAIL_BODIES: bucket(env.MAIL_BODIES) }); }
  async fetch(request) {
    if (request.url === "https://synthetic.invalid/r2-stats") return Response.json(stats);
    return super.fetch(request);
  }
}
