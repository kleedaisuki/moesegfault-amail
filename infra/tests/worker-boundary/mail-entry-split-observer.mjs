/**
 * Local-only introspection and critical-error injection around the actual 0.8.5
 * generated SDK and the checked-in entry adapters. Never an upload input.
 */
import { WorkerEntrypoint } from "cloudflare:workers";
import * as ApiModule from "../../../crates/mail-worker/entry/api.mjs";
import * as MaintenanceModule from "../../../crates/mail-worker/entry/maintenance.mjs";
import BuiltMail from "../../../crates/mail-worker/build/worker/shim.mjs";

let trap, armed = false, traps = 0;
let lifecycle = null;
/** Supply a native Wasm unreachable trap from the generated local fixture module. */
export function setTrap(value) { trap = value; }

/** Report application methods only, excluding platform-provided RPC machinery. */
function surface(module) {
  const prototype = module.default.prototype;
  return {
    exports: Object.keys(module).sort(),
    methods: Object.getOwnPropertyNames(prototype).filter(name => name !== "constructor").sort(),
    directPlatformBase: Object.getPrototypeOf(prototype) === WorkerEntrypoint.prototype,
  };
}

/** Separate control entry; tests still load the production adapters unchanged. */
export default class MailEntrySplitObserver extends WorkerEntrypoint {
  fetch(request) {
    if (request.url === "https://synthetic.invalid/arm-trap") {
      armed = true;
      return new Response(null, { status: 204 });
    }
    if (request.url === "https://synthetic.invalid/lifecycle") return Response.json(lifecycle);
    if (request.url === "https://synthetic.invalid/surfaces") {
      return Response.json({ api: surface(ApiModule), maintenance: surface(MaintenanceModule), traps });
    }
    throw new Error("no application HTTP on split observer");
  }

  /**
   * Exercise the unchanged SDK's synchronous critical-error path with an actual
   * Wasm trap; restore its prototype before the next real Rust scheduled tick.
   * This is reset-boundary evidence, not a claim that Rust business code panicked.
   */
  scheduled(event) {
    if (!armed) return this.realScheduled(event);
    armed = false;
    const prototype = BuiltMail.prototype;
    const original = Object.getOwnPropertyDescriptor(prototype, "scheduled");
    if (!original || typeof trap !== "function") throw new Error("real generated scheduled handler/trap absent");
    Object.defineProperty(prototype, "scheduled", { ...original, value: function() { return trap(); } });
    try {
      return new MaintenanceModule.default(this.ctx, this.env).scheduled(event);
    } catch (error) {
      if (error instanceof WebAssembly.RuntimeError) traps++;
      throw error;
    } finally {
      Object.defineProperty(prototype, "scheduled", original);
    }
  }

  /** Observe identities and completion without replacing the real Rust handler. */
  realScheduled(event) {
    const prototype = BuiltMail.prototype;
    const original = Object.getOwnPropertyDescriptor(prototype, "scheduled");
    const expectedContext = this.ctx, expectedEnv = this.env;
    let originalResult;
    lifecycle = { sameEvent: false, sameEnv: false, sameContext: false,
      returnsOriginal: false, promise: false, backgroundCompleted: false, cron: null, scheduledTime: null };
    Object.defineProperty(prototype, "scheduled", { ...original, value: function(arg) {
      lifecycle.sameEvent = arg === event;
      lifecycle.cron = arg.cron;
      lifecycle.scheduledTime = arg.scheduledTime;
      lifecycle.sameEnv = this.env === expectedEnv;
      lifecycle.sameContext = this.ctx === expectedContext;
      originalResult = original.value.call(this, arg);
      return originalResult;
    } });
    try {
      const result = new MaintenanceModule.default(this.ctx, this.env).scheduled(event);
      lifecycle.returnsOriginal = result === originalResult;
      lifecycle.promise = typeof result?.then === "function";
      // Native scheduled completion includes this registered background promise.
      this.ctx.waitUntil(result.then(() => { lifecycle.backgroundCompleted = true; }));
      return result;
    } finally {
      Object.defineProperty(prototype, "scheduled", original);
    }
  }

}
