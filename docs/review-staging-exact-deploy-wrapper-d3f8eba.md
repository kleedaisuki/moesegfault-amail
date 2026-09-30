# Review: exact staging Mail deployment wrapper (`d3f8eba`)

Date: 2026-10-01. Scope: the three-file commit
`d3f8ebab70c463a277317db49fa8da01626803b0`, existing production call site,
staging isolation/binding helpers, and the narrow staging promotion integration
observed in the working-tree `.github/workflows/ci.yml`. Reviewed the deployment
decision, historical serving-pin contract, and prior production gate review
before tracing source. This review does not cover the other pending workflow
changes or the ten-address harness.

## Verdict

**GO for hosted source checks. No substantive new wrapper defect identified.**
The observed pending staging wrapper integration is also **GO for hosted source
checks**, conditional on retaining the protections described below. The wrapper
commit alone is **not a completed CI integration**: its committed workflow still
uses the earlier raw-output staging Wrangler step and pre-Queue standalone pin.
Do not operationally adopt that older caller as the new exact-pin flow.

No local tests, builds, provider calls, deployment, sending or hold change were
performed. This review authorizes none of those actions. Hosted synthetic test
success, provider response/readback acceptance, and separately authorized rollout
remain distinct requirements; GO is not a live deployment/privacy attestation.

## Assessed source behavior

* `deploy_production_mail.py:require_context` rejects missing output, wrong branch,
  unknown target, wrong staging confirmation and non-`api-only` topology before
  creating secrets or invoking Wrangler. Staging reuses `check_staging.check`
  and the `queue-api` binding contract. The combination checks the reviewed
  Identity/HTTP/Mail/ingress values, exact staged D1 and R2 targets, sole named
  Mail D1/body bucket, absence of `OFFICIAL_EMAIL`, exact one Queue producer and
  a syntactically valid reviewed Queue ID. Queue ownership is independently
  established by the caller; the wrapper does not claim to establish it.
* `main` keeps no-argument production on `refs/heads/main`, with unchanged
  env-free production Wrangler command, secret keys and public labels. Explicit
  staging always adds `--env staging`. There is no target inference or fallback.
  The imported binding helper performs no provider request at module import.
* Each invocation creates a random target-prefixed file under repository `.temp`,
  applies mode 0600 on the hosted Linux runner, writes only the three existing
  runtime secrets, and removes the file in `finally` on ordinary success,
  command failure, timeout and caught validation/IO failure. No role destination
  is added. Credential provenance is owned by protected workflow environment
  selection, not inferable from a secret's bytes.
* Exactly one `subprocess.run` executes, capturing stdout/stderr privately with
  a 600-second timeout. The combined character-length acceptance limit is checked
  before UUID publication. One lowercase complete UUID after the exact version
  label is published; duplicates, absent/malformed UUIDs and oversized output
  fail without a pin. The raw provider body and caught exception contents are
  not deliberately printed.
* A unique version on nonzero command exit is emitted as recovery metadata while
  returning failure. Neither that case nor timeout is retried. Success captures
  an identity; it does not establish current serving, immutable bindings,
  capture-off settings, Queue ownership or SMTP acceptance.
* `test_deploy_mail_realms.py` substitutes the provider operation and inspects
  actual command arguments, file location/content/cleanup, attempt count,
  branch/confirmation/Queue/secret denial, redacted output, timeout and recovery
  semantics. These tests were inspected, not executed. They use the actual
  repository staging guard and binding configuration, so they also depend on
  keeping that checked-out configuration valid.

## Narrow integration evidence and required boundaries

The observed working-tree staging job preserves exact branch/dispatch/confirmation,
`environment: staging`, the `INGRESS_SECRET_STAGING` mapping, and same-run Queue
outputs. It sets `AMAIL_TRACE_TOPOLOGY=api-only`, supplies the explicit confirmation,
names the wrapper step `api`, runs from repository root, and calls
`deploy_production_mail.py --target staging`.

After success it independently checks Queue ownership with `--topology api-only`,
pins `steps.api.outputs.version` with `--phase queue-api` and the same-run Queue ID,
then verifies API privacy, exact sink privacy and continued global send hold.
Pre-mutation and immediately pre-replacement hold checks remain present. Normal
GitHub failure propagation prevents subsequent acceptance steps after ambiguous
deployment; no automatic replay, rollback, route cutover or unhold is introduced.
The standalone serving-pin job also selects `queue-api` and the protected reviewed
Queue variable. Those details are necessary integration conditions, not cosmetic
step names.

## Limits, not new findings

The size check is a **bounded acceptance** rule, not a streaming memory cap:
`capture_output=True` buffers subprocess output before checking its length.
This behavior was preexisting and the documentation does not promise bounded
capture memory. Similarly, `finally` cannot guarantee cleanup after process/runner
termination or an unlink failure; no implementation can promise cleanup after
arbitrary host termination. The practical supported cleanup paths are ordinary
completion, caught errors and subprocess timeout on the hosted runner.

The reused config guard is not a complete arbitrary-TOML schema validator; the
strict immutable postdeployment allowlist and reviewed source remain necessary.
No new exploit or regression was demonstrated from the actual checked-out config.
The pin/readback is also not an atomic provider transaction, and this review does
not assess coordination with every external deployment writer. Freeze and recovery
must follow the established operational policy. Do not broaden this source verdict
to whole-workflow concurrency, unrelated production gate transitions, or live
privacy/delivery guarantees.

## External evidence

Cloudflare's current [Wrangler environments documentation](https://developers.cloudflare.com/workers/wrangler/environments/)
specifies explicit `--env` selection and non-inherited bindings, variables and
secrets. This supports the explicit staging command/config and protected secret
mapping, rather than assuming staging can inherit production configuration.
The [Workers best-practices reference](https://developers.cloudflare.com/workers/best-practices/workers-best-practices/)
was also retrieved; generic observability advice does not supersede this project's
stronger mail confidentiality/capture-off contract. No research claim is being
made by this bounded deployment-wrapper review.
