/** Fetch-only platform surface; the generated SDK retains Wasm recovery ownership. */
import { WorkerEntrypoint } from "cloudflare:workers";
import BuiltMail from "../build/worker/shim.mjs";

/** Compose rather than inherit: no generated scheduled/RPC method is exported. */
export default class MailApi extends WorkerEntrypoint {
  /** Preserve the invocation's request, environment, context and returned completion. */
  fetch(request) {
    return new BuiltMail(this.ctx, this.env).fetch(request);
  }
}
