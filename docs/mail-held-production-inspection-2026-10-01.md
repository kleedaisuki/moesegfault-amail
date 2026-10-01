# Held production inspection and exact schema contract

## Decision and scope

Build one credential-free source-derived schema verifier and one separately guarded
hosted production inspection. This advances the preferred first-fenced-production
bootstrap path without modifying historical staging data or pretending elapsed
sleep can drain unfenced HTTP work. The inspection makes no provider changes,
object GET, mailbox read, migration, account registration, grant, release or send.

Source-derived schema verification applies the checked-in chain in hosted in-memory
SQLite only, then compares exact sqlite_master objects, material SQL tokens, table
columns/defaults, index uniqueness/order and the recorded migration chain. Before
separately authorized migration it accepts only a complete exact prefix at least
0006; a fenced runtime requires the entire chain including 0010. A migration-name
row alone is not structure evidence. Conservative SQL normalization ignores layout,
comments and simple identifier quoting while preserving literal case/whitespace.

Production inspection reads the exact reviewed config. It rejects staging storage,
wrong first-party coordinates and non-paused API source. A successful complete
current Worker inventory must contain no production Mail API/maintenance/role and
no current direct production store binding/service caller. The intended public
Mail route/domain must be unattached. The whole R2 bucket is enumerated using the
Cloudflare documented S3 client, without prefixes, delimiters, object contents or
mutations. The existing repository S3 Secret names are reused: no second token,
manual digest Secret or per-environment Secret migration is required.

The D1 structure must be an exact recorded source prefix; global send is held,
all release/grant bits are zero, and journals, reservations, addresses, messages
and complete R2 inventory are empty. Used/ambiguous state selects recovery and is
not erased. Two full observations must have identical canonical digests. These
are bounded **current facts**, not universal historical absence or old-work end.
The only persisted artifact contains source/run identity, digests, aggregate counts
and explicit `historical_absence=UNVERIFIED`, `old_work_end=UNVERIFIED`,
`admission=NOT_GRANTED`. Raw settings, inventories and provider envelopes never
enter the artifact or workflow logs.

## Execution and ownership

The new workflow has a credential-free synthetic job on scoped PRs. The provider
job can run only on a first-attempt main manual dispatch with exact confirmation.
It shares `amail-production-graph-writer` with production deployment, so controlled
GitHub writers cannot race it. This lock does not claim to prevent Dashboard or
external-token changes; no out-of-band writer should run during the observation.
Credentials are scoped to the sole final inspection step; SDK installation and
synthetic tests have no provider secrets. The S3 account endpoint is constructed
from the validated account ID rather than a caller/environment redirect target.
Provider exceptions are reduced to a fixed failure label.

A discarded draft proposed independent human review through extra Environment
hash Secrets and universally complete historical proof. That is not shipped: it
adds operator chores without proving truth of historical records. Inspection facts
are bound by immutable successful GitHub execution, and any later admission must
combine real first-deploy/resource provenance with these facts. If retained-store
history remains consequentially ambiguous, a fresh source-reviewed storage epoch
is the actionable alternative, not an invented pristine/drained flag.

## Tests and limits

Hosted synthetic tests cover full/prefix schema, SQL literals, indexes, triggers,
columns, duplicate objects and migration provenance, plus first-party resource
validation, held empty state, complete S3 pagination, malformed inventory, current
store/service callers, absent Worker selection, query mutation rejection, dispatch
isolation and artifact privacy. Local checks are AST and git whitespace only;
no local test imports, builds or toolchain/SDK installation.

The inspection still depends on actual Cloudflare permissions and response shapes.
A green synthetic job cannot establish production facts. A successful provider
inspection is not deployed-runtime PKCE, SMTP receipt/ZIP/search acceptance,
second-principal isolation, ten-address quota, feedback, retained-trace privacy,
Cron CPU/memory/wall or public release acceptance. These remain explicit next work.

## Primary grounding

- [Cloudflare R2 boto3](https://developers.cloudflare.com/r2/examples/aws/boto3/):
  account-scoped S3 endpoint, explicit access credentials and region auto.
- [SQLite PRAGMA](https://www.sqlite.org/pragma.html): schema/index introspection.
- [SQLite schema table](https://www.sqlite.org/schematab.html): normalization and
  stored schema SQL are structural facts, not user/mail data.

The implementation uses mature platform mechanisms rather than a new deployment
framework. No academic novelty or speculative historical-proof abstraction is
claimed; discriminating observable contracts are the appropriate method here.

## First actual inspection and privacy-preserving diagnostics

Manual main run 36828109460 used source6527c82982c1252025f942da9bd8fd924c0e84a2.
Its 6 schema +11 inventory contracts passed, the pinned SDK installed successfully,
and the sole actual inspection step returned UNVERIFIED after about4.1seconds.
No provider write/deploy/migration/grant/send occurred and no success artifact was
produced. The original verdict collapsed every failure stage, so it does not yet
identify the cause and must not be described as a proven missing permission.

Add invocation-local enum stages and closed reason bins (own contract codes,
selected HTTP statuses and selected SDK refusal codes). Never return arbitrary
SDK message/URL/body/code, object key, address or token. Two negative/mock tests
prove prose and malformed codes remain unexpected, while403/AccessDenied remain
useful fixed diagnostics. This changes no provider read, admission or Secret scope.
The next identical bounded inspection is warranted only after hosted source checks
accept this diagnostic patch; no blind permission request or repeated full test
campaign is appropriate. Its Python-only stacked PR also exercises the new
conservative CI scope before main integration; main full checks remain required.

### Second actual inspection narrows the unresolved boundary

Run36830581802 (main201c9fa,07:29UTC) passed6schema+13inventory contracts.
The actual read reached route_inventory, then failed with reason=unexpected.
It therefore passed SDK/R2/current-Worker inventory boundaries, but it does not
prove route/domain absence, schema or held-state acceptance. The reused custom-
domain checker has its own closed ValueError codes and preserves chained HTTP
statuses; the initial classifier did not recognize those codes. Add separate
reader-import/custom-domain stages, map only those two known legacy codes and
bounded numeric HTTP causes, and distinguish missing local dependencies without
returning module names. One mock covers private/cyclic causes and malformed status.
No extra remote read, mutation, broad permission request or admission is introduced.

Official domain endpoint remains account-wide GET /workers/domains with Workers
Scripts Read/Write authorization and optional generic result_info:
https://developers.cloudflare.com/api/resources/workers/subresources/domains/methods/list/ .
Its documentation does not establish this actual failure's cause; the next fixed
bin must decide whether the problem is transport, protocol or local dependency.

### Third actual inspection: custom-domain protocol rejection

Run 36832211353 (main bed07c395cf81ecb6b80dc217a9a0564f95c7d03,
07:46 UTC) passed 6 schema + 14 inventory contracts. The actual read failed at
custom_domain_inventory with custom_domain_inventory_unverified, not an HTTP
permission refusal. SDK, whole-bucket R2, current Worker inventory, zone ownership
and Workers routes progressed before that boundary. Domain absence, D1 schema,
held empty state and deployment admission remain unverified; no mutation occurred.
Main full CI 36832207613 subsequently completed successfully.

Extract the existing complete-list validator without loosening its acceptance
rules. Its ValueError subclass preserves sink_domains_unverified for existing
callers, while one closed enum identifies the rejected structural rule. The
inspector uses its own bounded no-redirect transport and the extracted validator,
so there is still exactly one domain request and no raw response artifact. Hosted
tests cover every structural bin, malformed/partial lists, private attributes and
the single-read transport. The next actual inspection can discriminate identifier
format from generic pagination metadata without printing hostnames, IDs, values or
provider prose. Documentation alone does not yet identify which rule is wrong;
do not request a Token change or permissively accept a partial inventory.
