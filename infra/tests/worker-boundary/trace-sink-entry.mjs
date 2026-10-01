/** Test-only console-order barrier around the production queue-only entry wrapper. */
import TraceSink from "../../../workers/trace-sink/entry/queue.mjs";

/** Preserve SDK dispatch/recovery; publish a static barrier after Rust returns. */
export default class Observer extends TraceSink {
  async queue(...args) {
    const result = await super.queue(...args);
    console.log("SYNTHETIC_QUEUE_CONSOLE_BARRIER");
    return result;
  }
}
