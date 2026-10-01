/** Queue-only platform surface; generated SDK helper classes are not RPC exports. */
import { WorkerEntrypoint } from "cloudflare:workers";
import BuiltSink from "../build/worker/shim.mjs";

/** Compose the generated default so Rust dispatch and SDK recovery remain unchanged. */
export default class TraceSink extends WorkerEntrypoint {
  /** Preserve the batch, invocation environment, context and native completion. */
  queue(batch) {
    return new BuiltSink(this.ctx, this.env).queue(batch);
  }
}
