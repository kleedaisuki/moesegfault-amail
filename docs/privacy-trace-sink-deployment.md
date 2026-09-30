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
all bounded provider pages, creates only absent queues, and verifies retention.
Existing drift fails; it never updates, purges or deletes resources. Ambiguous
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
   normal hosted CI. Sink deployment is a prerequisite of API deployment.
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
- [Queue consumer schema](https://developers.cloudflare.com/api/resources/queues/subresources/consumers/)
- [Workers Logs](https://developers.cloudflare.com/workers/observability/logs/workers-logs/)

The consumer API uses `script_name`; queue producer entries use `script`.
Wrangler timeout seconds are attested against API `max_wait_time_ms`. Provider
schema omissions are verification failures rather than assumed defaults for the
explicit retention/retry/privacy boundary.
