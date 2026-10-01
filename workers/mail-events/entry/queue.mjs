/** Queue-only lifecycle surface; generated SDK classes must not become named RPC. */
import { WorkerEntrypoint } from "cloudflare:workers";
import BuiltEvents from "../build/worker/shim.mjs";

/** Delegate without inheritance so only the reviewed event handler is exported. */
export default class MailEvents extends WorkerEntrypoint {
  /** Preserve Rust acknowledgement/retry semantics and the native completion. */
  queue(batch) {
    return new BuiltEvents(this.ctx, this.env).queue(batch);
  }
}
