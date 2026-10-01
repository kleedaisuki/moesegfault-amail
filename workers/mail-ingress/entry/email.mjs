/** Email-only platform surface; no fetch, named RPC or generated helper exports. */
import { WorkerEntrypoint } from "cloudflare:workers";
import BuiltIngress from "../build/worker/shim.mjs";

/** Keep envelope processing and SDK recovery inside the existing Rust delegate. */
export default class MailIngress extends WorkerEntrypoint {
  /** Return the original email completion with the invocation's environment/context. */
  email(message) {
    return new BuiltIngress(this.ctx, this.env).email(message);
  }
}
