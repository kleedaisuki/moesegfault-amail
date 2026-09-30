# Review: complete production role capabilities and non-Queue predecessor (`413557d`)

Date: 2026-10-01. Verdict: **GO for non-deploying hosted source checks only.**
No substantive defect found in the exact shared-checker slice. This is not
approval to deploy, change routes, enable sending, or assert privacy acceptance.

## Scope and method

Reviewed `413557dc85506070ae5c31dbd2f10b4824e15998`, following the independently
reviewed `dfa727e` contract, using commit-specific source/config reads. Inspected
`verify_role_monitor_staging.py`, the production binding fixture, Mail pin helper,
both Wrangler configurations and existing staging callers. Reused
`review-production-role-bindings-dfa727e.md` and the production graph-transition
decision. The concurrently edited orchestration and later `d58921f` change are
outside this review. Static `git diff --check 413557d^ 413557d` passed. No local
or hosted tests, provider requests, secret reads or production edits were made.

## Checked invariants

- Production role capabilities must include all seven non-Queue names, or all
  eight names with `ROLE_TRACE_EVENTS`. Exact name equality, duplicate rejection
  and allowed name/type pairs together reject missing secrets, unexpected
  resources and a capability substituted under an approved name.
- Production still requires the independently supplied D1 identity, the fixed
  production realm and zone, and the singleton official sender restriction.
  Staging-only `ROLE_TEST_FAULT` cannot appear in either production phase.
- `queue_attached=False` is explicit and production-only. It requires zero
  Queue bindings; it is not a fallback after an unavailable or mismatched Queue
  read. The caller still supplies a syntactically valid independently reviewed
  Queue pin for the surrounding graph, even though the predecessor has no
  Queue attachment.
- The immutable-version adapter forwards the phase without bypassing the exact
  requested version ID or accepting an unknown bindings wrapper. The shared
  checker itself does not establish single-100 serving deployment, graph
  topology, no-capture settings or route state; those separate gates remain.
- Existing staging defaults retain `queue_attached=True`, the staging database
  default and previous optional staging secret behavior. No existing staging
  caller in this commit selects the predecessor mode.
- The preceding Mail contract still requires the exact production
  `OFFICIAL_EMAIL` binding and singleton `mail@moesegfault.dev` sender allowlist.
  Its staging default rejects that production-only capability. This commit does
  not modify Mail's bindings, privacy predicates or send policy.

## Integration and verification limits

The new fixture supplies all three required production secrets, consistent with
the reviewed role configuration's runtime capability model. It still exercises
production acceptance, duplicate/fault rejection and staging-default rejection.
The exact slice does not add executable predecessor acceptance/rejection cases
or one-at-a-time removal of required secrets. Hosted follow-on orchestration
fixtures should cover: non-Queue predecessor accepted only with an explicit
production phase and reviewed serving/D1 pins; attached Queue rejected in that
phase; staging cannot use it; each required capability missing; and the adapter
forwarding the chosen phase. This is a focused verification follow-up, not a
claim of a demonstrated implementation defect.

A predecessor's permitted binding set is not evidence its code is privacy-safe
or operationally compatible. The upcoming production orchestration must bracket
its reviewed serving version, effective parent/Logs/Traces/Issues capture-off,
private surfaces and strict `api-only` topology, distinguish confirmed absence
from a failed read, and preserve existing direct forwards. Neither this checker
nor its source review substitutes for complete retained-record acceptance.

## External references

Retrieved current official documentation on 2026-10-01:

- [Cloudflare send bindings](https://developers.cloudflare.com/email-service/configuration/send-bindings/): sender and destination restrictions are separate capabilities; the singleton sender requirement here matches the explicit official-sender contract.
- [Workers best practices](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/): controlled platform bindings support capability isolation. Generic observability advice does not override the project's stronger original-context privacy boundary.
