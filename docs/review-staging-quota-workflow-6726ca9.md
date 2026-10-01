# Independent review: supervised retained-escrow workflow wiring

Date: 2026-10-01. Reviewed commit: `6726ca9d811ea981ca50ba1a39e097d888451dba`, based on `5ded982`.

## Decision

**GO for hosted source validation only. No substantive blocking defect found in this wiring slice. Live dispatch remains separately NO-GO until its recorded staffed admission, source CI, effective privacy, global hold, protected Environment and writer exclusion are independently satisfied.** This review neither supplies supervision nor validates provider state.

## Scope and evidence

Inspected the three-file diff, complete acceptance workflow and workflow contract tests, and executable callers in `staging_ten_address_acceptance.py`, `staging_ten_address_artifact.py`, and `staging_ten_address_provenance.py`. Read the new admission runbook and existing retained-recovery review. `git diff --check 5ded982..6726ca9` succeeded. No project tests/builds, provider calls, dispatch, push or production modifications were performed locally.

- Eight distinct dispatch inputs are present: mode, confirm, source_run, prior_run, artifact_id, supervised_by, mail_phase, queue_id. The current official GitHub maximum is 25. Mode is explicit and legacy `accept` remains default.
- The job is manual, exact feature-branch, attempt 1, GitHub-hosted Windows, staging Environment, 80-minute timeout and shared concurrency with cancel-in-progress disabled. These are executable controls, not proof of Environment protection configuration or global exclusion of unrelated writers.
- Mode-specific confirmations and coordinates are rejected before explicit private credentials. Escrow additionally binds a syntactically bounded supervised_by to the actual GITHUB_ACTOR. Actor matching establishes attribution, not continuous watch; the runbook explicitly requires staffed admission and acknowledged handoff separately.
- Dependency setup and synthetic real-cipher/composition tests precede step-level private provider, native-login and retained-key credentials. No scheduled/workflow_run replay, continue-on-error, Secrets-based supervision token or automatic fallback is introduced.
- Explicit supervised-escrow selects prepare-escrow then campaign-escrow. Both the prepare outcome and upload outcome must be success before campaign. Upload is exact one-file ciphertext, non-overwriting, error-on-missing with 30-day retention. No wildcard plaintext artifact is introduced.
- Before campaign, a bounded GET of the exact immutable artifact ID compares ID, explicit nonexpired status, exact run-derived name, current run ID, checkout SHA, and upload-action digest against independent REST metadata. Any failure uses fixed labels and prevents coordinator invocation; no raw payload or signed URL is printed. The coordinator independently validates metadata, branch/repository relationship, lifetime, archive digest and one-file ZIP bytes, then authenticates the envelope and D1 relation before arm/add. A malformed REST value cannot authorize add solely through the workflow comparison because the coordinator revalidates it strictly.
- Explicit recover-escrow requires distinct original run, empty artifact ID, correct recovery confirmation and actor binding. It selects only retained D1 recovery. The coordinator requires completed original attempt provenance, fresh native checks, source lock/service relation/effective privacy/held checks, verifies the receipt and retains all ciphertext. It exposes neither add capability nor per-chunk purge on this transport.
- Legacy accept/recover continue to choose their existing selectors; legacy recover still passes the exact artifact ID. The added upload receipt binding strengthens campaign admission without replacing its immutable artifact authentication. No original-run rerun is enabled.

## Test interpretation and limits

The changed workflow tests are static contract tests: they check selectors, guards, ordering and receipt expressions, not real GitHub expression evaluation or PowerShell REST runtime. Existing artifact/coordinator tests cover their own injected-reader and composition contracts. Hosted execution is still required; a source-green result must not be described as a real supervised campaign, cleanup proof, autonomous watchdog proof, public-send admission or release acceptance.

Optional maintenance: coordinator docstrings still use phrases such as “existing workflow does not activate” for seams now explicitly wired by this commit. Update them in a future documentation slice to distinguish registered-but-unadmitted workflow wiring from live use. This does not affect executable authority and is not a merge blocker.

## Official references checked

- GitHub workflow dispatch inputs: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onworkflow_dispatchinputs (25-property limit, choice strings).
- GitHub artifact metadata REST API: https://docs.github.com/en/rest/actions/artifacts#get-an-artifact (Actions read permission, digest and workflow_run relation).
- Exact upload-artifact v4 action metadata: https://raw.githubusercontent.com/actions/upload-artifact/v4/action.yml (artifact-id/digest outputs, overwrite and hidden-file behavior).

No conclusion is drawn about Cloudflare Issues capture, actual Environment review rules, real account/route state, a supervisor's availability, or continuous 24-hour recovery intake.
