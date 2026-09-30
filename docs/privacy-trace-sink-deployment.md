# Private trace sink deployment and rollback

Status: source rollout contract; not a live privacy attestation.

## Resource ownership

| Realm | Queue | DLQ | Sole Worker consumer | Sole bound producer |
| --- | --- | --- | --- | --- |
| staging | amail-trace-events-staging | amail-trace-dlq-staging | amail-trace-sink-staging | amail-mail-staging |
| production | amail-trace-events | amail-trace-dlq | amail-trace-sink | amail-mail |

Both queues explicitly retain messages for 86400 seconds. The sink has no HTTP
route, workers.dev address, preview URL, D1/R2 binding or runtime secret. Its
consumer uses batch size 10, timeout 1 second, three retries, retry delay 30
seconds and concurrency two. DLQs have no consumer or bound producer. Do not
attach a diagnostic HTTP-pull consumer: it changes the reviewed ownership and
creates a second payload access path.

`infra/deploy/ensure_trace_queues.py --target staging --phase queues` inventories
the bounded unfiltered single-page Queue endpoint, creates only absent queues, captures each returned ID, configures one-day
retention using the documented PATCH on only that fresh ID, and verifies retention.
Existing drift fails; it never updates existing resources, purges or deletes queues. Preexisting
resources additionally require exact reviewed project variables
`AMAIL_TRACE_QUEUE_ID_STAGING`/`AMAIL_TRACE_DLQ_ID_STAGING` (or `_PRODUCTION`).
These non-secret IDs must come from the successful provisioning evidence; name
equality alone cannot adopt an unrelated empty queue. Counts and resource
identity must match complete producer/consumer arrays on detail readback. Ambiguous
POST failure stops without retry. Reconcile inventory before a later run.
`--phase readback` is read-only and verifies exact consumer, retry/DLQ settings
and API producer ownership after API deployment. It never fetches a message.
Only fixed result labels are printed, never provider bodies or queue payloads.

## Ordered migration

1. Deploy the separately reviewed **containment-only** API commit: existing
   handlers with all API observability disabled, no trace Queue producer.
   Record its 100%-serving version and use the existing serving-version pin and
   both effective settings readbacks. Do not deploy producer changes first.
2. Only after containment is live may the producer/sink source be pushed for
   hosted source CI without automatically deploying the new sink or API producer.
   Established unrelated staging site, role-monitor and private-inbox jobs may
   still redeploy on a source push; their existing deployment policy is unchanged.
   Sink/producer deployment is manual only: dispatch
   `ci.yml` with `target=staging`, `confirm=RUN_STAGING_TRACE_SINK_ROLLOUT`,
   `trace_containment_run=<successful-run-id>` and
   `expected_worker_version=<exact-contained-version-uuid>`. The guard verifies
   immutable successful first-attempt run/SHA/deploy-job/version output, historical safe TOML,
   stable 100% serving deployment and current effective safe settings. It does
   not accept a mutable repository variable as deployment provenance. Sink
   deployment is a prerequisite of API deployment.
   The staging sink job checks API containment before queue creation. The API
   job checks containment again immediately before migration/build/deploy.
3. Provision one-day queues, deploy the queue-only sink, then read back private
   sink settings/triggers. Deploy the producer API with explicit disabled
   observability and TRACE_EVENTS binding, then verify queue ownership and API
   settings. A sink failure prevents API deployment. A producer failure leaves
   API containment intact.
4. Pin both serving versions and run the whole-retained-record synthetic privacy
   canary. Settings/queue ownership checks alone are not a privacy pass. Require
   both API non-retention and sink marker-free retained causal events.

Production has no prior deployed public API in this rollout; its first version
must use safe settings, and the private sink must precede it. Secrets stay
repository/project-managed; sink provisioning reuses the existing deployment
credential and introduces no new runtime secret.

## Rollback and ambiguity

Never roll back to a logging-on API version. If the producer fails, deploy the
known containment-only API version (or a new reviewed safe-settings fix) and
read back 100% serving/settings. Queue/sink loss must not alter mail API results;
it is an observation gap, not permission to restore HTTP-context retention.
Do not purge queues or DLQs on rollback: bounded expiry handles queued safe
records. Keep the sink available until queued records expire or are consumed.
Do not fetch arbitrary DLQ payloads to debug delivery. Review fixed counters and
provider ownership/settings first; any replay tooling needs separate review.

An interrupted create/deploy must be reconciled by inventory and serving version
readback, not blindly rerun. Global workflow/ref serialization and per-service
concurrency prevent concurrent hosted rollouts; out-of-band deployments still
require an operator freeze during live version-pinned canaries.

## Verification evidence and sources

No local tests/builds or live provisioning were executed for this source change.
Python synthetic contracts run through the infrastructure CI job; Rust schema,
sink tests, Wasm compile and bundle run through the Worker CI job. Independent
source review and hosted results remain required before deploying.

Cloudflare official contracts consulted on 2026-09-30:
- [Queue configuration](https://developers.cloudflare.com/queues/configuration/configure-queues/)
- [List Queues](https://developers.cloudflare.com/api/resources/queues/methods/list/)
- [Create Queue](https://developers.cloudflare.com/api/resources/queues/methods/create/)
- [Official Queue SDK (SyncSinglePage, no paging query)](https://github.com/cloudflare/cloudflare-python/blob/main/src/cloudflare/resources/queues/queues.py)
- [Queue consumer schema](https://developers.cloudflare.com/api/resources/queues/subresources/consumers/)
- [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)

The consumer API uses `script_name`; queue producer entries use `script`.
Wrangler timeout seconds are attested against API `max_wait_time_ms`. Provider
schema omissions are verification failures rather than assumed defaults for the
explicit retention/retry/privacy boundary.
