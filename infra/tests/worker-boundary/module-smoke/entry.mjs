/** Catch module roots that cannot resolve a parent-directory ES module. */
import { marker } from "../module-smoke.js";

export default {
  /** Fetch through the local-only outbound handler instead of the network. */
  fetch() {
    return fetch(`https://fixture.invalid/${marker}`);
  },
};
