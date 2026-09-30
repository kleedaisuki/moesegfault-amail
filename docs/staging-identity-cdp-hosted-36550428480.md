# Hosted staging CDP startup failure: run 36550428480

Status: source mitigation prepared; no rerun result yet. This note records only fixed harness labels and timing, not browser URLs, credentials, Identity responses, or mail.

## Evidence and scope

- On 2026-09-29, [hosted staging E2E run 36550428480](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36550428480) built and tested the Windows CLI, then printed `staging_hosted_e2e_failed:identity_chrome_cdp_unavailable` about 13 seconds after entering the Python harness. It stopped **before** address registration or any mail-route mutation.
- The `Browser._connect` source at that revision used a hard 12-second CDP readiness deadline; it mapped browser exit, missing page target, local HTTP readiness, and WebSocket handshake failures to one label. Chrome was found and `Popen` returned; the precise underlying condition cannot be recovered because raw browser output was intentionally suppressed.
- An earlier [hosted run 36533465672](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36533465672) passed native PKCE and authenticated Mail resource access with the same CDP source, then failed at address registration. Thus this is not evidence that the PKCE or Identity contract regressed. Slow cold browser/profile startup is a plausible **hypothesis**, not an established root cause.

## Narrow response

Give an installed Chrome up to 45 seconds to expose a localhost page target before any credentials are typed or mail is mutated. Preserve the exact loopback host/port check, proxy bypass, fresh profile, and suppressed stdout/stderr. Differentiate a process that exited before CDP from a still-running process that exceeded the deadline, using only fixed labels. The constructor must kill and reap a launched process when attach fails. Do **not** automatically repeat login, address registration, or route writes to make this startup flake disappear.

The hosted infrastructure test suite has synthetic cases for attachment after the old 12-second deadline, early exit, deadline expiry, wrong-port target, and constructor cleanup. These tests cannot prove a future runner's Chrome startup behavior. The next explicitly reviewed hosted E2E attempt should interpret a new fixed label as a discriminating signal; only a successful deployed native login can close this incident.
