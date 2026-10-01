/** Scheduled-only platform surface; never add a public health check or RPC method. */
import { WorkerEntrypoint } from "cloudflare:workers";
import BuiltMail from "../build/worker/shim.mjs";

/** One invocation-scoped delegate shares the existing Rust dispatcher and SDK recovery. */
export default class MailMaintenance extends WorkerEntrypoint {
  /** Return the native scheduled completion with the original controller/Env/context. */
  scheduled(event) {
    return new BuiltMail(this.ctx, this.env).scheduled(event);
  }
}
