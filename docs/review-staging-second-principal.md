# Review: second staging Identity principal preparation

Scope: independent source review of commit `7d7748a` against the private two-contact OTP inbox, route ownership, CDP registration, legacy DPAPI credentials, and the live runbook. This review did not create a rule, account, email, or session, did not deploy a Worker, and did not validate the live Cloudflare configuration.

## Findings

### P1 — Deployment interlock ignores the new B route

`7d7748a` parameterizes `workers/identity-test-inbox/ensure_route.py` and permits `amail-e2e-isolation@moesegfault.dev`, but both deployment workflows still call the helper without `--address`: `.github/workflows/ci.yml:774-797` and `.github/workflows/deploy-identity-test-inbox.yml:59-82`. The default audits only A. If a B registration is in progress, or B cleanup fails and leaves its exact rule enabled, a branch push or manual redeployment passes the predeploy check and replaces the inbox Worker while that OTP route is live. The postdeploy check also reports success despite the open B route. This breaks the intended invariant that no test code-capture route is active during Worker replacement and could lose or redirect an in-flight verification message.

**Correction:** audit **every configured test address** before and after deployment and require all absent. Do not silently auto-remove a route in CI; fail and let the owner reconcile the exact route. Derive the bounded list from the validated source allowlist, then test that an enabled B route blocks either workflow. Keep the same interlock in both workflows.

### P2 — Local allowlist is mistaken for deployed recipient evidence

`workers/identity-test-inbox/ensure_route.py:26-43` reads `wrangler.toml` only, yet its docstring calls this the “reviewed, deployed” allowlist. `workers/identity-test-inbox/check_config.py:144-165` checks local TOML and private R2 state; the deploy workflows do not read back `TEST_RECIPIENTS` from the deployed Worker after `wrangler deploy`. `docs/staging-second-principal.md:15` correctly requires this readback but supplies no concrete verifier. A stale/failed or drifted deployment can thus leave the Worker accepting only A (or some other value), while the route helper opens B and the local config checks pass. The actual challenge to B will be rejected or disappear from the expected private inbox; the runbook's “source accepted” condition is not met by the current automated evidence.

**Correction:** add a bounded, sanitized postdeploy settings/bindings readback of the exact deployed `TEST_RECIPIENTS` value, together with the already-required no-HTTP/private-R2 checks. Fail closed on missing or unequal value. Check both workflows; distinguish local-source validation from live deployment validation in helper wording.

## Not elevated to a blocking finding

- The Rust Email Worker checks the SMTP envelope recipient against a bounded explicit allowlist and still has no HTTP handler. Each message receives a fresh R2 object key; this does not expose a user mailbox.
- Route `apply`/`remove` compares one literal `to` matcher, API ownership, enabled state, and exact Worker action, and passes the selected address through create/readback/delete. It does not take over a foreign or duplicate literal rule.
- Registration uses the selected address for route audits, first-party form, and encrypted credential, including cleanup; the first alias stays the default. `decoded_credential` defaults a *missing* encrypted address to A, preserving old blobs, and rejects non-test addresses.
- `staging_identity_cdp.py:713,729` accepts `--address` for the `login` phase but ignores it; login uses the encrypted run-directory credential. This can confuse an operator who passes `login --address B` with A's run directory, yet the documented B sequence intentionally relies on a fresh B run directory. A useful hardening is to reject a supplied login address that disagrees with the credential, but the current runbook is not directly invalidated by it.

## Evidence boundary

The new tests verify route parameter propagation, legacy payload interpretation, and local allowlist syntax. They do not simulate a B route during either deployment interlock, nor verify a deployed Worker variable. Live B account and ownership isolation remain untested by this source review.
