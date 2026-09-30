# Independent review: frozen historical containment binding contract

Date: 2026-10-01. Reviewed immutable candidate:
`5d99147a80607b58127c0bad48adcde30c4b5c9d`, parent `1a77a50`.
Implementation worktree: `.temp/historical-binding-contract`.

## Decision

**GO for the bounded source change, subject to required hosted synthetic CI.**
No substantive defect was found in the inspected change. **NO-GO for rollout,
privacy acceptance, or replay of either spent correction operation.** This
change repairs a temporal binding-policy mismatch; it creates no successful
immutable settings attestation or positive current Issues-off evidence.

No local project test/build, provider operation, private log/body read, mail
operation, push or deployment was performed in this review. Test results are
not claimed. Commands were limited to repository/source inspection; one public
Cloudflare documentation page was read, with no account-specific information.

## Evidence and assessment

The review reused `held-staging-mail-promotion-2026-10-01.md`, inspected all
13 changed files, surrounding helper execution paths and workflow test discovery,
and compared historical `daaab1f79cd985030d8d502fd647e16757673052` source/config
directly. The retained phase evidence of operation `36761367007` is used only
as the parent handoff's historical pre-write binding provenance; its failed
privacy acceptance is not transformed into a successful operation.

| Boundary | Assessment |
| --- | --- |
| Historical contract | `containment_predecessor_bindings()` is a fresh literal 14-entry map matching the documented historical Mail/role D1 IDs, bucket, three secret names and seven variables. It does not read current TOML or returned provider bindings. |
| Historical version | `containment_bindings_match()` rejects any expected version other than exact c3f; the shared comparator separately requires the response version to equal that pin. |
| Current contract | `expected_bindings()` remains direct-only with exactly one reviewed Mail D1 and strict queue-api Queue identity. Ordinary `bindings_match()` has no historical fallback, union or optional role capability. |
| Shared comparison | Name/type/target/total-count/duplicate checks and the sole exact `result` wrapper remain unchanged; arbitrary extra ROLE_MONITOR, TRACE_EVENTS or OFFICIAL_EMAIL is not admitted historically. |
| Caller selection | Only settings-v1 containment verification and the three fixed historical helpers select the named historical matcher. Both correction helpers retain historical checks before and after their existing mutation/readback brackets. The diagnostic uses the same historical expected map for shape causes. |
| Privacy and immutable evidence | `immutable_evidence()` still precedes provider reads; marker/job/source validation is unchanged. Strict `effective_api_settings()` remains necessary after historical binding success, including independent Issues evidence and final unchanged serving bracket. |
| Current/production deployment | Ordinary pin remains current-policy based; production graph and staging trace rollout use explicit queue-api. No configuration, workflow, secret, mutation payload or permission change occurs. |
| Output and authorization | Fixed output labels and one-shot/environment guards are unchanged. Documentation explicitly denies current privacy inference and retry authority. |

The extraction now selects the current config contract before malformed response
shape/version rejection, rather than afterwards. This can expose a config error
earlier in an invalid-config case, but inspected operational callers either
validate config first or already fail closed on the relevant exceptions. There
is no demonstrated regression or security weakening requiring correction.

## Synthetic coverage inspected, not executed

The new literal fixture is independent of both current TOML and the factory.
Tests cover exact old acceptance, current direct-only/queue-api separation,
missing/extra/duplicate/renamed role, wrong IDs/production targets, unknown
capabilities, secret type substitution, response/version shape and expected
version rejection. A config-unavailable check verifies historical independence;
clearing one returned map verifies factory ownership isolation.

Settings-v1 tests use actual literal historical bindings and check missing,
null-enabled and enabled Issues rejection, failed run/missing marker refusal
before provider reads, and default deploy-kind separation. Correction helper
spies verify both historical checks. Existing diagnostic/output assertions
remain in place. Fixture imports follow the established `python -m unittest
discover -s infra/tests -v` discovery contract; its source job includes the new
test file automatically. This is source-level reasoning, not execution proof.

## Remaining acceptance and limits

1. Require green hosted synthetic source tests at the exact integrated SHA;
   integration may change surrounding source and therefore needs a settled pin.
2. Preserve the separate missing immutable containment-evidence gate and
   current Issues-off evidence requirement. Do not dispatch staging merely
   because this source change or source CI succeeds.
3. No live serving/binding/capture state was independently revalidated here.
   Secret names/types are checked; secret bytes are not attested.
4. The review does not authorize any new correction, containment redeployment,
   Queue operation, contact adoption, sending experiment or release.

References: [parent handoff](held-staging-mail-promotion-2026-10-01.md),
[implementation record](historical-containment-binding-contract-2026-10-01.md),
[direct-only deployment contract](direct-forward-api-deployment.md).
Cloudflare's [observability documentation](https://developers.cloudflare.com/workers/observability/errors/)
was consulted only as public platform context; repository predicates and
immutable historical evidence, not generic documentation, determine this
review's exact acceptance contract.
