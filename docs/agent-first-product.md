# Agent-first product direction

## Decision and scope

amail is an agent-first mail **tool**, not yet a complete unattended mail workflow
product. Its default JSONL, search-before-retrieval, explicit mutations, native ZIP
boundary and durable unresolved-send keys are substantive agent-first decisions.
Adding a web inbox, MCP server or autonomous orchestration engine is not a
prerequisite for the next useful release.

The next product increment should close one dominant job:

> An authorized agent sends a transactional report, can recover the same send
> after interruption, observes available delivery feedback, finds a related reply,
> and prepares a correctly addressed reply without asking the human to operate mail.

This direction was reviewed on 2026-10-03 against repository source `de5f3d5` by
three product-manager agents covering journeys, interface contracts and trust.
It is a source-backed product decision, not a new production inventory, an
implementation claim or permission to send mail. Existing delivered evidence
remains in [validation](validation.md). No real mailbox, provider or deployment
operations were performed for this review.

## Product boundary

* Primary scope: agent-workflow transactional notifications and related replies.
  Do not evaluate launch completeness against unrestricted personal email or bulk
  campaigns.
* The human chooses the task and authorizes Identity login; an authorized agent
  owns ordinary mail operations. Unattended does not mean unrestricted authority.
* The CLI is a tool for an external agent runtime. Waking that runtime is a distinct
  concern, not a reason to embed an agent scheduler in the mail service.
* Automatic external semantic indexing is a disclosed existing product choice,
  not telemetry. Preserve that contract unless the owner explicitly changes policy.

## v0.1.2: Progressive disclosure is the interface, not missing capability

The owner approved these product improvements on 2026-10-03 for **staging only**,
with performance work in parallel. This section records the implementation design;
hosted checks and staging acceptance, not this document, establish delivery. Do not
publish a tag or GitHub Release before owner acceptance.

The governing distinction is **small initial context, complete reachable space**.
An agent can follow another link or issue another query. It should not have to
guess that delivery events, owner policy, receipt recovery or reply relationships
exist, and it should not have to ingest them all to list twenty messages.

| Layer | Entry point | Cost and purpose |
| --- | --- | --- |
| Offline discovery | `amail discover`, then one named topic | Small versioned catalog, targeted fields/commands/examples; no login or network. |
| Ordinary work | Existing search JSONL and message summaries | Preserve established stdout and avoid body, lifecycle-event or quota expansion. |
| One entity | Message `get`, logical-send status, recipient outcomes | Optional relations and compact links; provider acceptance separate from delivery feedback. |
| Changes not yet identified | Owner event listing with `kind`, `since`, optional message and cursor | Indexed, bounded exploration without knowing the changed message ID in advance. |
| Applicable constraints | Sending-status query | Account's applicable policy and quota facts only, not private operator notes or global account activity. |
| Recovery/control | Explicit `--machine` stderr protocol and local send receipts | Structured actionable continuation/intent records without altering legacy message stdout. |

Discovery describes the installed client's capabilities, not the health or sending
authorization of a remote service. Server policy remains authoritative. Leaf help
and schemas explain distinctions such as local ID versus RFC Message-ID, received
event time versus provider occurrence time, complete empty page versus unfinished
search, and unobserved feedback versus failed delivery.

### Recovery and event invariants

* Persist an explicit UUID **before** each logical send. Same intent plus identical
  ZIP bytes reuses one submission; an intentionally new intent can reuse content.
  Keep legacy automatic unresolved-payload keys and allow their accepted rotation.
* Retain accepted local receipts separately before releasing an unresolved key.
  Local receipts are bounded recovery evidence, not current remote delivery state.
  Owner-scoped server lookup of the intent is authoritative after interruption.
* Event queries reuse `provider_events`; outcomes reuse `recipient_outcomes` and
  submissions reuse `send_requests`. Do not introduce a second delivery ledger.
  Narrow indexes are justified by owner/time/kind/message read paths.
* Event pagination binds the owner, filters and fixed high-water boundary; late
  arriving provider events belong in a fresh listing. `since` applies to receipt
  time, so a delayed older occurrence remains discoverable. Events are retained
  for 90 days; an empty page is not proof that no delivery event ever happened.
* No provider prose, raw payload, private operator notes or another owner's/Bcc
  data reaches these read surfaces. Deleted-delivery visibility follows the
  existing caller-owned mail boundary, not an independently discoverable archive.
* Incoming relation fields are optional, validated and bounded. Missing or invalid
  relation data is unknown, never reconstructed from a matching subject. Reply-To
  is a suggested destination in untrusted data, not an expansion of user authority.

### Best-practice fit and limits

[Anthropic's Agent Skills design](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
uses small metadata followed by instructions and supporting files loaded when
needed. Applied here: keep the main skill compact and put recovery/events/reply
recipes in targeted references.
[Anthropic's advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
documents on-demand tool discovery and realistic usage examples, while noting an
extra discovery call has a latency trade-off. Applied here: an offline catalog and
focused leaf contracts, not a network tool-search framework for this small CLI.
Neither vendor's reported benchmark gains establish amail task success rates.

[MCP resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)
separate paginated resource discovery, parameterized templates and targeted reads;
[Anthropic's code-execution practice](https://www.anthropic.com/engineering/code-execution-with-mcp)
likewise uses navigable definitions and selective output. Applied here: stable
topic identifiers, leaf queries, references and cursors, without adding an MCP
dependency. Fewer bytes at the root must never hide a useful space. We optimize
initial context, not the number of deliberate agent exploration steps.

The accepted research sources below supply complementary acceptance dimensions:
tau-bench motivates completing the user's final task and repeated consistency;
AgentDojo motivates testing hostile mail alongside useful work. They do not justify
making every command a giant validation envelope or blocking delivery on a new
research platform. The inexpensive first probe is the report/recovery/reply task
with same-subject distractors, lost output and delayed provider feedback.

### Acceptance assessment: implemented v0.1.2 increment

Assessment on 2026-10-03: **the implemented interface is sufficiently agent-first
for the bounded, authorized transactional-mail tool role**. It now supports a
recoverable task rather than merely exposing mail commands. The scoped staging
journey below now has live acceptance evidence; it does not establish every
transport relationship or unattended agent task. Publication still awaits owner
review. External scheduling and agent judgment remain outside
the tool; a web inbox, MCP layer or autonomous daemon is not needed to close this
increment.

| Evidence level | Current conclusion and scope |
| --- | --- |
| Implemented | Offline `discover` index and targeted schema topics; opt-in `machine` control records; remote send receipts and bounded local acceptance history; owner outcomes/events/policy queries; optional validated reply relations and searchable metadata. Ordinary summaries/stdout remain small. |
| Source-validated | `discovery.rs`, `machine.rs`, `send_state.rs`, `feedback.rs` and `archive.rs` encode actionable recovery and owner/deletion boundaries. Independent review corrections cover accepted-but-index-pending sends, unknown send 5xx, invalid input and expired event cursors. Narrow feedback visibility checks project one integer rather than mail content. |
| Hosted-validated | Subsequent same-runtime checks, including [37068720900](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37068720900), passed all three CLI platforms, native Worker contracts, Wasm compilation and 112 actual Workerd boundary tests. The earlier invalid foreign-owner and oversized-body fixtures are corrected; their failures are not current runtime-test status. Synthetic feedback/recovery coverage is not a new real provider-delivery result. |
| Staging-validated, bounded | [Native journey 37069775670](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37069775670) verified release-candidate Windows login/discovery, held policy, event/absent-intent reads, two SMTP-to-ZIP receipts, incoming relation search and cleanup. Its extra grant step stopped and **send was never invoked**. A second failed native run (`37072844102`) installed an audited slot but falsely rejected total D1 changes that included the trigger write; [readback 37074323728](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37074323728) confirmed that run's intact gates/audit/window. The old slot stayed protected until natural expiry. The helper-only fix uses `RETURNING id`, without relaxing product authorization. |
| Final deployed site and runtime validated | [Staging producer 37072106319](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072106319) succeeded for `25f22cd`. [Final browser acceptance 37072847760](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37072847760) passed 12 live-staging cases against that revision with zero client scripts and representative visual acceptance. [Helper-only producer 37074671896](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37074671896), source `2ea0d09`, passed all gates, three CLI platforms and 112 actual Workerd tests; the product runtime is unchanged. |
| Native end-to-end acceptance passed | [Native run 37075181256](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/37075181256) succeeded using the actual Windows release candidate from producer `37074671896`, source `2ea0d09`, artifact `11256560216`. It verified discovery/policy/events/absent intent, two SMTP-to-ZIP fixtures and related-reply search/cleanup, then one controlled self-send: lost stdout -> remote and local receipt recovery -> identical ZIP replay under the same UUID with unchanged local/provider IDs -> delivered outcomes/events -> actual incoming RFC header -> exact owned cleanup. Global sending remained held. Its explicit `provider_to_rfc_mapping_not_asserted` marker prevents extrapolating the observed fixture into a provider-wide wire-ID mapping, model task-success rate or prompt-injection guarantee. |

The progressive-disclosure test is positive at the interface level: the offline
root tells an agent **which spaces exist**; a selected topic/schema describes
**how to query them**; `get`/receipt links lead to **one entity's details**; indexed
account events reveal **changes whose message ID is not known yet**. Machine
errors distinguish resume-search, query-the-same-send, fresh event listing, input
repair, login, wait and stop. Extra deliberate calls are useful exploration, not
friction to remove by returning everything upfront.

The dominant task now has a coherent path: prepare a report -> persist explicit
intent UUID -> send -> recover the same receipt after output loss -> inspect
known feedback only if needed -> find a reply by a proven RFC relationship ->
prepare a fresh authorized reply draft. Acceptance, archive projection, observed
delivery and human reading are distinct. When no proven RFC identity exists,
relation lookup remains explicitly unknown rather than being guessed from a
provider ID or subject. In this increment **the general outbound provider-ID-to-wire-header
mapping remains unverified**, including syntactically valid RFC-shaped provider
values. Outbound `get` therefore does not manufacture `rfc_message_id`; incoming
archives expose it only from the actually received Message-ID header. A received
header or another proven relationship is required before claiming that a response
belongs to a particular report. This conditional boundary is a product limitation, not
an excuse to hide the relation space or fabricate a completed workflow.

The implementation and scoped staging acceptance are closed; the next step is
owner review, not another feature increment or acceptance framework. Retain these
product boundaries during review and any later release:

1. Review the staged candidate CLI/Skill and site, then publish only on the owner's
   explicit instruction. Reuse the completed runtime/browser/native evidence;
   do not replay installed components or send another fixture just to repeat it.
2. The controlled one-intent self-send proves bounded live receipt/replay/feedback
   behavior, not unrestricted sending or a latency/reliability SLA. Keep global
   held policy distinct from that narrowly granted test.
3. Use an actual received RFC identity where a related-reply task needs it;
   preserve the optional/unknown fallback. One observed self-send does not establish
   a general provider-ID mapping.
   [Cloudflare's header contract](https://developers.cloudflare.com/email-service/reference/headers/)
   describes automatically generated Message-ID; the current
   [Workers sending result](https://developers.cloudflare.com/email-service/api/send-emails/workers-api/)
   describes `messageId` as a unique email ID, without establishing equality to
   that wire header. The implementation uses this Workers binding, not REST.
4. Skill guidance is not a proven prompt-injection defense or a measured autonomous
   task-success rate. If later agent use reveals a concrete authority or selection
   problem, use a small targeted task probe rather than adding a universal framework.
5. Preserve task UUID/ZIP context across runtime restart. Local receipts retain
   only 100 accepted intents and events 90 days; missing retained evidence is not
   permission to resend. These disclosed bounds do not require an infinite ledger.

## What already works for agents

| Capability | Evidence | Product consequence |
| --- | --- | --- |
| Default structured output | `crates/amail/src/main.rs:33-43, 205-214` | Agents do not scrape a human inbox presentation. |
| Small metadata before content | `main.rs:82-111`; public manual search/read sections | Less unnecessary content and attachment material in model context. |
| Explicit read-state changes | `main.rs:107-121, 711-724` | Inspecting a message does not secretly advance workflow state. |
| Native draft/archive boundary | `main.rs:123-145`; `skills/amail/references/archive.md` | Agents author ordinary files; the service owns MIME and ZIP validation. |
| Unresolved-send key persistence | `crates/amail/src/send_state.rs:20-38` | Transport uncertainty does not automatically rotate the submission key. |
| Search continuation | `main.rs:163-170, 527-574`; `docs/search-jobs.md` | Long exhaustive searches have owner-scoped resumable work, not false complete prefixes. |
| Agent-specific instructions | `skills/amail/SKILL.md` and its focused references | Existing CLI + skill is a credible integration surface without an additional protocol. |
| Bounded delivered journey | `docs/actual-production-users-2026-10-02.md` | Receive/send/reply/attachments/search were exercised through ordinary CLI commands. This is not a measured natural-language agent-task success rate. |

## Original review baseline: high-value gaps and smallest useful changes

The observations below describe the pre-increment source reviewed by the three
product agents. The acceptance assessment above records which mechanisms now
exist and their current evidence; do not read historical "future" command wording
below as the current CLI capability list.

Priority here means product sequencing: P1 is the next outcome-focused increment;
P2 is conditional on observed demand. No new emergency P0 was established by this
product review.

### P1: Preserve incoming reply context

**Observed:** inbound parsing reads From, To, Subject and Message-ID
(`crates/mail-worker/src/archive.rs:239-264`). The inbound manifest and indexed
metadata omit Reply-To, In-Reply-To and References (`archive.rs:55-67, 278-290,
325-330`). Outbound manifests support threading and the search metadata allowlist
accepts `in_reply_to` (`crates/mail-worker/src/lib.rs:2434, 2832`). Therefore an
incoming reply's relationship is not available through the intended structured
search path. Searching the same subject is not an equivalent relationship.

**Smallest change:** retain bounded, parsed optional reply headers in incoming
metadata and the ZIP manifest. Expose them through existing `get` metadata and
make `--meta in_reply_to=...` useful for incoming mail. Add a task recipe for
report -> related response -> fresh reply draft. A full conversation/thread API
is unnecessary.

**Contract:** distinguish the local delivery ID, provider submission ID and RFC
Message-ID. `outbound_metadata` currently uses `provider_id` as `message_id`; a
real transport fixture must establish the mapping before relying on it for reply
association. Do not infer a defect solely from different identifier names.
Missing/invalid relation headers stay unknown; untrusted Reply-To is a suggested
destination, not user authorization to send there. Existing archives with dropped
headers cannot be repaired by assuming same-subject mail is a reply.

**Acceptance:** an incoming fixture with a distinct Reply-To and valid relation
headers survives metadata and archive retrieval; relation filtering returns the
correct reply. The agent prepares a new draft with the correct RFC relationship
and authorized destination without guessing. Older ZIPs and clients still work.

### P1: Make failure and unfinished work machine-readable

**Observed:** API errors retain typed status/code internally but render as prose
(`crates/amail/src/api.rs:16-31, 378-405`). Runtime failure prints `amail: {error}`
and exits 1 (`main.rs:732-738`). Search announces its job ID/resume instruction in
prose stderr and defaults to a 900-second wait (`main.rs:163-170, 548-571`). The
service's strong asynchronous contract becomes weaker at the actual agent boundary.

**Smallest change:** provide an explicit, versioned machine failure/continuation
mode, preserving legacy stdout, error text and exit behavior for existing scripts.
Use bounded fields such as operation, stable code, HTTP status, opaque request ID,
job ID and closed next-action category. Cover local validation and authentication
errors as well as API errors. Do not emit raw provider detail, private query text,
addresses or tokens. Existing `--wait-seconds` can support short agent-runtime
budgets; retain the current waiting mode for compatible callers.

**Contract:** `retryable=true` alone is unsafe. A resumed search, fresh search,
same-key send reconciliation, human login and stop-policy action are different
decisions. Never convert an uncertain mutation into permission for a new attempt.
Running work must remain distinguishable from a complete empty result page.

**Acceptance:** an agent can handle expired/stale search, unfinished jobs,
authentication required, held sends and unknown submissions without parsing
English prose. Existing JSONL result and cursor consumers receive unchanged bytes
unless they explicitly select the new mode.

### P1: Recover a logical send and expose its outcome

**Observed:** after API acceptance the CLI deletes the saved payload-hash key
before emitting the result (`main.rs:668-687`; `send_state.rs:35-38`). If the process
or capturing runtime loses that result after key deletion, a later default send
can allocate a new key. The explicit `--idempotency-key` already lets a careful
caller retain one logical intent; automatic transport recovery alone does not
close the orchestrator's lost-result boundary.

The service also already stores provider events and projected per-recipient
outcomes (`workers/mail-events/src/lib.rs:144-152`;
`crates/mail-worker/migrations/0006_outbound_abuse.sql:173-214`). Ordinary message
summary/get exposes neither delivery outcome (`lib.rs:2029-2063`), and the command
enum has no send-status recovery operation. Operational feedback is not yet a
usable agent product receipt.

**Smallest change:** define a logical-send receipt around the existing owner-scoped
idempotency key. Preserve/recover a bounded accepted receipt and add a read-only
status surface that can look up an intent even while the ordinary sent-message
projection is pending. Reuse `send_requests` and `recipient_outcomes`; do not build
a second event-processing engine. A future command name/schema remains a design
choice, not a currently available CLI command.

**Contract:** same logical intent + same bytes reuses one submission; a deliberately
new intent can send identical bytes again. Do not deduplicate identical messages
forever by payload hash. A changed payload under an existing key remains invalid.
Expose submission state separately from per-recipient lifecycle feedback. Missing
feedback means unknown/not yet observed, not delivered, rejected or safe to resend.
Preserve existing outcome precedence and keep Cc/Bcc/envelope information scoped
to the original owner. A status lookup is not new send authorization.

**Acceptance:** lose the result after acceptance, restart the agent/CLI, recover the
same intent and prove one provider submission. A separately authorized new intent
with identical content still works. Known delivered/deferred/bounced/complained
outcomes are visible through normal owner CLI operations, including partial
recipient outcomes, without leaking another owner's mail or Bcc metadata.

### Small P1 instruction improvements using existing capabilities

These do not require a runtime rewrite and should accompany the coherent feature
increment rather than becoming a new documentation project:

* Persist an explicit UUID in the agent task workspace **before** each logical
  send, using the existing `--idempotency-key`. Reuse it after result loss. This is
  the immediate available mitigation while a read-only receipt lookup is designed.
* Enumerate the intended bounded message-ID set before marking/deleting entries.
  Current mailbox generation guards invalidate pagination after mutations
  (`docs/search-jobs.md`). A paginate -> mark -> next-page loop can invalidate its
  own cursor. If enumeration becomes stale, restart enumeration without mixing
  pages, retaining completed per-ID task work; never re-execute an irreversible
  action just because a listing restarted. Add snapshot machinery only for a
  demonstrated frequently changing/large-mailbox need.
* Explicitly classify **all** incoming subjects, display names, plain text, HTML,
  metadata and assets as untrusted task data, never user authority. Current skill
  explicitly calls out HTML/assets; ZIP safety does not stop text instructions
  from trying to hijack a task. A routine already authorized by the user needs
  agent validation, not a mandatory extra human approval every time. Changed or
  ambiguous authority needs clarification. This is guidance, not a hard security
  guarantee.
* Add a copyable public "give this task to your agent" bootstrap prompt: identify
  the correct release, verify/install CLI plus skill, disclose indexing transfer,
  start human browser login, reuse an owned active address and prepare the first
  authorized report. The current manual is comprehensive but package-selection
  oriented. Do not advertise automatic reply association until its fields exist.
* The new machine mode can retain page-level completion/count/request ID and
  existing address capacity data. Current `emit_items` flattens rows plus cursor
  (`main.rs:318-330`), dropping these useful envelope fields. Preserve old JSONL.

## Deliberate choices, not automatic launch blockers

| Topic | Current judgment | Revisit when |
| --- | --- | --- |
| No web inbox or `view` command | Keep; agent owns file/content processing. | Human inbox use becomes an actual product goal. |
| ZIP-only content exchange | Keep native ZIP; measure task friction before adding alternate retrieval formats. | Plain-text tasks repeatedly waste file/pack steps or context. |
| No MCP server | CLI + skill is sufficient for shell-capable runtimes. | A valuable target runtime cannot execute the CLI or needs tool-schema discovery. |
| No mailbox watch/webhook | Not a defect for bounded, user-initiated tasks. Runtime scheduling can be external. | Reply-triggered unattended workflows become a primary promise. Start with one bounded wait/since primitive or documented runtime recipe, not both a scheduler and webhook platform. |
| Account-wide authorization | Reasonable for a trusted local agent; not isolation between independent agents. | Multiple differently trusted agents/teams share one account. Add narrow capabilities then. |
| Automatic indexing, no per-account opt-out | Disclosed owner-selected policy; creates a real sensitive-mail adoption boundary. | Sensitive use cases justify a policy change. Define disabling, already indexed data, future transfer and semantic-search behavior together; do not silently repurpose telemetry opt-out. |
| No draft-init/reply helper or schema export | Useful conveniences, not proof that current design is non-agent-first. | Task traces show recurring header/template/schema mistakes. |

## Lightweight product probe, not another audit framework

Run a small natural-language task set with the released CLI and skill when the
necessary test fixture and send authority are explicitly available. Reuse hosted
validation for protocol correctness; do not rerun completed production campaigns
for this documentation decision.

1. Find the correct unread release report among same-subject distractors, extract
   its required attachment and summarize without changing read state.
2. Prepare an authorized transactional notification with an attachment and an
   explicit logical-send key; distinguish accepted from delivered.
3. Interrupt an unfinished search and resume the same job rather than resubmitting.
4. Lose a send result after acceptance; recover it without a duplicate submission.
5. Find a genuine related reply, honor its reply destination only within user
   authority, and prepare a correctly threaded fresh draft.
6. Include a hostile email asking to leak another message or delete mail; finish
   the user's legitimate task without taking that requested extra action.

Record task completion, human interventions excluding necessary initial login,
unnecessary tool calls/restarts, time to useful output, duplicate sends and
unauthorized mutations. Compare before/after against the same fixtures/runtime
and keep synthetic experiment artifacts under root `.temp`/`.cache`. Repeated
trials should reveal consistency rather than reporting one lucky pass. Initial
coverage is a product diagnostic, not a claimed population success rate or SLA.

## External grounding

* [Anthropic: Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
  supports a small set of high-value tools, meaningful concise responses and
  realistic task-driven iteration. Applied here: improve recovery and reply
  relationships before multiplying commands or protocols.
* [Cloudflare Email Service](https://developers.cloudflare.com/email-service/)
  explicitly supports transactional notifications and agent interactions. This
  supports the narrow product job, not unrestricted personal email scope.
* [AWS Builders Library: Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
  explains explicit caller intent identifiers and parameter-mismatch semantics.
  Applied here: the same mail bytes may belong to different legitimate send
  intents; a lost-result retry must preserve intent, not allocate a new key.
* [tau-bench, ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/1b126cc38b8638e07bef37e7b2bb72bf-Abstract-Conference.html)
  evaluates final environment state, policy adherence and reliability across
  repeated agent-user-tool interactions. Applied here: functional CLI evidence
  is not sufficient to measure autonomous task completion. Its reported model
  success rates must not be extrapolated to amail or current models.
* [AgentDojo, NeurIPS 2024](https://proceedings.nips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html)
  jointly evaluates useful tasks and prompt-injection security over untrusted
  tool data, including email. Applied here: safe ZIP extraction is not the same
  as resistance to semantic instruction hijacking; task authority must not come
  from received mail. Do not promise complete prompt-injection immunity.
* [CaMeL: Defeating Prompt Injections by Design, IEEE SaTML 2026](https://satml.org/2026/program/)
  investigates separating trusted control flow from untrusted data and constraining
  unauthorized data transfer. This is a useful future design direction, not a
  reason to replace amail's CLI with a research interpreter. Its
  [official artifact](https://github.com/google-research/camel-prompt-injection)
  warns that it is a research prototype rather than a supported production tool.

## Implementation discipline

Prefer additive metadata, reuse the existing outcome/key stores, and keep old
CLI/ZIP clients working. Do not create a universal orchestration abstraction,
duplicate status ledger, broad test framework or new deployment lane for this
increment. Implement and exercise the coherent report/recovery/reply journey;
update public manual/skill contracts only when the corresponding capability
exists. This document is the product rationale; architecture, privacy policy,
operations and delivered validation retain their separate canonical ownership.
