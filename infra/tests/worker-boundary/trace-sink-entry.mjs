/** Test-only console-order barrier around the unchanged official Rust Queue bridge. */
import Generated from "../../../workers/trace-sink/build/worker/shim.mjs";

/** Preserve SDK dispatch/recovery; publish a static barrier after Rust returns. */
export default class Observer extends Generated {
  async queue(...args) {
    const result = await super.queue(...args);
    console.log("SYNTHETIC_QUEUE_CONSOLE_BARRIER");
    return result;
  }
}
