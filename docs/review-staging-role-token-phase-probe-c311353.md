# Review: guarded role Routing token discriminator (`c311353`)

## Verdict

**GO for one manually dispatched, read-only staging diagnostic**, after the
branch's hosted CI has validated the new synthetic tests and after a fresh role
Worker serving-version pin has been obtained. This is not a GO for SMTP replay,
public sending, or historical root-cause attribution.

## Evidence and scope

Reviewed the commit diff, `ci.yml` control inputs/step scopes,
`infra/tests/staging_role_token_phase_probe.py` and its synthetic cases,
`infra/provider/ensure_role_forwarding.py`'s paginator and strict four-role
audit, `workers/role-monitor/hosted_acceptance.py`'s active-version reader, and
`workers/role-monitor/staging_route.py`'s disposable-alias detector. No provider
request or local test execution was performed in this review.

The workflow dispatch target is limited to `main` or the project branch and
requires exact confirmation plus historical run ID **before** the final step
receives provider and destination secrets. The script independently classifies
Addresses and Rules reads using the existing bounded paginator; bearer-carrying
requests use a redirect-rejecting opener. It compares the private destination
only in memory, requires one provider-verified destination and four enabled,
API-owned, exact direct forwards, detects the disposable alias, and checks one
100%-serving role Worker version against the supplied UUID. Output is limited
to fixed labels, including on unexpected exceptions. The script issues GETs
only and contains no SMTP, deployment, D1, or route mutation path.

## Material limits, not blockers for this diagnostic

1. **Current state, not historical state.** Secret rotation or routing changes
   since run `36603362864` mean even a `read_only_pass` cannot prove the token
   capabilities or Cron phase of that failed run. The implementation and its
   runbook state this correctly.
2. **Pagination is not an atomic provider snapshot.** The shared paginator
   checks each page's count, total, shape, and bounds, but a concurrent
   equal-count insertion/deletion between pages can shift items while totals
   stay constant. Therefore `absent` is a bounded inventory observation, not
   an immutable guarantee. No write or replay is authorized by this probe, so
   this does not block the diagnostic; a mutation gate must use its own fresh
   route readback and external deployment freeze.
3. **The destination verification contract is inherited.** Any nonempty
   string in the provider `verified` field is interpreted as verified, as in
   the existing provisioner. This matches the expected timestamp-or-null API
   shape but does not parse a timestamp. An API shape drift could theoretically
   be misclassified. For a read-only discriminator this is acceptable, but a
   future provider-contract tightening should happen in the shared helper
   rather than only in this script.

The synthetic tests exercise independent 403s, redirect rejection, incomplete
pages, mismatched rules, and secret scoping. Hosted CI, not this review, must
establish that those tests actually pass on the current branch.
