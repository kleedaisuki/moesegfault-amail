/** Exercise transitive .js ESM discovery and the synthetic egress callback. */
import { marker } from "./module-smoke.js";

export default {
  /** Fetch through the local-only outbound handler instead of the network. */
  fetch() {
    return fetch(`https://fixture.invalid/${marker}`);
  },
};
