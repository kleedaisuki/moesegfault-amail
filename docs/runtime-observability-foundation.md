# Diagnostics and privacy

## Private causal spans, not automatic request capture

CLI bounded SQLite diagnostics and local command spans join opaque API request/
trace coordinates. Typed events cross the private Queue to a queue-only sink.
Local command UUID, request ID and native W3C span are different coordinates.
Upload acceptance is not retained delivery or a complete native trace waterfall.
v0.2.0 adds exact API/dependency clocks, stable pre-transport Billing client span
IDs, and scheduled root/stage spans; these are real application spans, not native
Cloudflare auto-instrumentation. See [v0.2.0 tracing](v0.2.0/observability.md) for
the shared causal contract and bounded retained-log witness.

Preserve legacy readers and typed capability negotiation. New closed wire shapes
must be parsed explicitly at the actual workers-rs boundary, not rely on a struct
attribute that may skip unknown keys. Capability headers prove parser support, not
sink delivery. Deploy compatible readers before announcing producers.

## Retention boundary

API and scheduled maintenance disable independent Logs, invocation Logs, Traces,
Issues and inappropriate public previews/workers.dev/Logpush/tails. Raw context
can leak path/query/SQL/R2 metadata even when a custom message is safe. Only the
private queue-only sink retains validated events. The active split graph has
exactly API plus maintenance producers; no dormant role producer.

Allow fixed kinds, bounded times/durations, source/version/run, status, numeric
provider codes and opaque causal IDs. Exclude tokens, OAuth URLs, addresses,
recipients, subjects, bodies/assets, SQL, R2 keys, private destinations and
arbitrary provider prose. No free-form metadata dictionary. Credentials belong
in separate auth.sqlite3, not diagnostics.

Control-plane events record source/run-bound phase, UTC/monotonic time, observed
exit/status and exact version when available. Typed failures retain useful recovery
coordinates without bodies. Logging failure cannot trigger write replay.

## Interpretation

Accepted PATCH is not effective all-off acceptance; missing Issues is not explicit
false. Failed reads are UNKNOWN, not absence. Historical settings/capture probes
are not authority to repeat PATCH, broaden credentials, weaken edge policy or
launch adaptive queries. Positive immutable serving/binding/capture/surface readback
is required. Native-tracing experiments are not ordinary maintenance requirements.

For regressions inspect existing journals, identify a product boundary and add one
discriminating reproduction with owned synthetic data in existing hosted lanes.
Do not create general capture services/incident workflows without a concrete
delivery decision. See [validation](validation.md) and [operations](operations.md).
