# Control-plane observability

Status: source implementation under hosted synthetic validation. No provider
probe/deployment or application tracing acceptance is implied. Infrastructure
foundation takes priority over further mailbox/debug campaigns.

## Mechanism

Use source/run-bound JSON operation records, not a second logging service.
control_plane_trace.span emits start/end with UTC time, exact monotonic duration,
source SHA, GitHub run/attempt/job, trace/span/parent identifiers and outcome.
Nested operations share context within a process; separate CI steps join by
source/run. These are application operation records, not native Cloudflare spans.
An observed HTTP status and CF-Ray join the specific Cloudflare request. No retry
is added; log-stream failure cannot change an operation's result or replay it.

The first consumers are the bootstrap inspector's bounded provider transport and
the private trace-sink deployment helper. This fixes diagnostic blindness without
resuming the inspector or fixing/changing its deferred custom-domain validator.
Sink deployment retains its existing command, timeout, pin extraction and refusal
rules. An opaque deployment refusal now has realm, phase, process exit code,
version count and explicit reason. Provider HTTP failure retains actual status,
request ID and exception class. JSON/schema failure distinguishes decode failure,
body limit, expected object versus actual type, unsuccessful provider response
and numeric API codes. Original exception text is never needed for those facts.

## Field-level privacy and compatibility

Retain account/zone/database IDs and static Worker script names where their
meaning is public operational infrastructure. Endpoint families come from
reviewed routes; query strings, unknown paths, SQL, credentials, headers other
than CF-Ray and full response/error bodies are excluded. Numeric provider codes
are useful; accompanying message/source objects may carry personal values and
are not emitted. Use static source-owned reason/schema labels rather than raw
provider values. Additional coordinates must be explicitly admitted by the
helper's field set; do not add a generic metadata/body dictionary.

Existing fixed terminal verdicts and provider acceptance checks remain unchanged.
The new records explain the cause; they do not grant writes, treat failed reads
as absence, prove deploy success from a start event, or replace readback/recovery.
Synthetic tests assert nested identity/timing, exact safe HTTP context, diagnostic
transport failure isolation, unchanged single deployment attempt and no poison
body/query/token/error text. Runtime tests belong on GitHub Actions only.

## Remaining integration

Apply this boundary to normal deployment/resource/readback/recovery helpers as
their lifecycle and tested-artifact flow are repaired, not by blindly dumping
every legacy research probe. SDK and Wrangler failures need typed useful status,
exit and recovery coordinates; full raw output is not a substitute. Top-level
precondition/schema diagnostics need their own source-owned expected/actual
context. Native Mail/maintenance/CLI causality and the platform-enrichment canary
remain separate in runtime-observability-foundation.md.
