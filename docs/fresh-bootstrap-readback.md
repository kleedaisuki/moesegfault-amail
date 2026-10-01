# Fresh paused graph and receipt readback

Source-only implementation, 2026-10-02. No provider reads/writes, mail/account
operations, local runtime tests or builds were performed for this workstream.
Hosted CI must execute the new synthetic tests before integration acceptance.

## Admission sequence

The protected controller owns successful storage creation and full same-run
artifact verification. `Scope` construction is syntax, not creation authority.
After submitting the fixed trace sink, it calls:

```python
verify_sink_reader(scope, sink_version, queue_id, dlq_id, provider)
# Only now may the controller submit the paused maintenance and fetch-only API.
graph = verify(scope, pins, queue_id, dlq_id, provider)
persist(scope, graph, queue_id, dlq_id, receipt_path)
```

The first check positively requires one installed private Queue consumer, zero
producers, exact single100 serving deployment/version, immutable queue-only
handler with no bindings, independent Logs/Traces/Issues checks, disabled preview
and workers.dev, empty Cron, and complete no-domain/no-route public surfaces.
It brackets deployment and Queue observations. It neither sends nor consumes a
message. Protocol compatibility is provided by the controller's original full
same-run checked module artifact, not by an API queue binding or provider name.
A native artifact/queue-binding-only result is not sufficient release admission.

The final graph requires exactly the API and maintenance producer pair, one
private sink consumer, an unused DLQ, no extra sink subscription, API's exact
`mail.moesegfault.dev` custom domain and no ordinary routes or private-sibling
public surface. Fixed three-script deployment IDs and versions bracket all reads;
a changed deployment fails even if its version is unchanged. API and maintenance
immutable binding predicates override only the response-owned D1/R2 identities.
Normal source coordinates and v1 policy are never modified.

NEW D1 is read directly by its response-owned UUID using SELECT/PRAGMA only.
Full migration/schema/column/index provenance and every application-table count
are compared with a migration-only reference; held policy and all grant fields
are verified explicitly. This includes owner projections, contacts and audit
rows, not just messages/addresses. Migrations already insert held defaults: an
unconditional held-policy UPDATE adds trigger audit rows and is not admitted.
Two complete whole-bucket R2 metadata-empty observations are required through
`provider.r2_empty(bucket)`. Two external forwarding snapshots must match through
`provider.forward_snapshot(account)`, supplied by the existing direct-forward
reader with its separate project routing token. Unknown/malformed reads remain
failures, never absence. Identity/account stores are outside this verifier.

## Receipt boundary

`VerifiedGraph` retains a private invocation-local canonical witness bound to
scope/Queue/DLQ. Direct ordinary construction, plain dicts or caller-mutated graph
content cannot accidentally become success records. This is not a security
boundary against malicious Python execution; authority is the reviewed protected
producer and admitted GitHub artifact provenance.

V2 has closed keys, exact compiler/source/run/artifact/hash identities, positive
creation/readback claims, exact fresh resource and graph pins, paused schedules,
held sending, original stores retained, `source_adoption=REQUIRED`,
`activation=NOT_GRANTED`, and `old_work_end=UNVERIFIED`. Persistence requires the
first-attempt main `ci.yml` job context and exclusive/fsynced `receipt.json` under
repository `.temp`; no overwrite/retry/delete/adoption command exists.

`load(run_id)` checks completed successful first-attempt main dispatch from the
exact repository and protected `Fresh held production bootstrap` job before
selecting the single immutable artifact ID named `mail-fresh-bootstrap-<run>-1`.
Only one bounded regular unencrypted ZIP member `receipt.json` is decoded;
duplicate JSON keys, incomplete inventories, wrong source/run, multiple members,
path traversal and expired/ambiguous artifacts fail. Loaded backing JSON is
immutable and each `.value` returns an independent copy. V1 readers are unchanged.

Fresh storage is not proof that old invocations or shared routing/sending work
ended. The current opaque custom-domain ID predicate is intentionally preserved;
known reader debt remains a blocking error, not an absence/adoption exception.

## Evidence and external mechanisms

* [Cloudflare Queues architecture](https://developers.cloudflare.com/queues/reference/how-queues-works/)
  distinguishes the producer's sending capability from the consumer's deployed
  processing role. Reader-first checks enforce both actual immutable reader and
  complete subscription graph before writer introduction.
* [Workers Issues control](https://developers.cloudflare.com/workers/observability/issues/investigate/)
  explicitly documents `observability.issues.enabled=false` as the disable
  control. Sink logs enabled does not make its independent Issues capture safe.
* [Workers Traces](https://developers.cloudflare.com/workers/observability/traces/)
  describes separately controlled tracing; top-level sampling is not a substitute
  for checking every independent capture switch.
* Source contracts reused: `check_mail_maintenance.py`, `pin_staging_mail.py`,
  `mail_schema_contract.py`, `ensure_trace_queues.py`, `check_observability.py`,
  `check_trace_sink_isolation.py`, and `mail_lifecycle_receipt.py`.

New hosted synthetic tests cover full fresh graph, NEW-only D1 targeting, all-table
population, scope-independent grants/capture, strict Queue pair, exact ingress,
same-version deployment replacement, absent reader/existing writer/public reader,
private witness mutation, closed v2 data, protected provenance, immutable artifact
selection and hostile archives. Local validation was restricted to AST parsing
and `git diff --check`; this document claims no executed test pass.
