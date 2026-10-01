# Independent review: remote CLI attempt reader (4b12fbdb)

Reviewed PR 54 head `4b12fbdb3363f835226c49d86b76f590c5e43757` in `.temp/runtime-telemetry` on 2026-10-01. Scope: seven-file diff, shared Queue validation, Mail telemetry upload/reconstruction, actual native sink fixture contracts, current CLI flush serializer and request attempt call sites, and reader-first ledger. No local runtime tests/builds, provider operations, deployment, secrets reads or production edits.

## Verdict and compatibility

**No demonstrated substantive correctness or compatibility defect was found.** This is a source-review verdict, not hosted or deployed runtime acceptance.

* CLI upload `Event`/`flush` remains unchanged: it still selects the historical wire fields and does not send the new metadata. No producer flag, capability probe or new operational ceremony was introduced. New CLI binaries therefore do not depend on old Mail readers understanding enrichment.
* Shared Queue fields use `skip_serializing_if = Option::is_none`; older ordinary events retain their serialized shape. New enum strings are closed; arbitrary strings and unknown payload fields remain refused.
* `Event::valid_client` imposes the new `ClientAttempt` boundary validator only when client boundary/error metadata is present. Previously accepted exact-only CLI Queue clocks/status remain accepted. Upload admission is intentionally stricter for any newly supplied enrichment: elapsed plus a coherent boundary/cause pair is required. These distinct upload and historical Queue contracts must not be collapsed later.
* A response-body failure retains received exact HTTP status (including 200), but has `phase_failure` and `dependency_failure`. Complete HTTP 503 stays a completed exchange with server-error outcome. Auth/transport failures retain status zero because no headers existed. Status class must match any exact status.
* The top-level Event validator refuses client phase/error fields on non-CLI services before per-phase validation, preventing API/service records from borrowing client semantics.
* `RequestSpan::finish` freezes monotonic elapsed before telemetry opt-out/database initialization/SQLite waits. Both legacy clamp and exact local column use that same frozen duration. The upload clamp and journal ownership/opt-out behavior remain unchanged.

## Tests and limits

Shared Rust contracts cover valid/invalid client boundary pairs and precision; Mail tests exercise additive reader parsing and actual reconstructed Event validation. Existing native Queue tests now dispatch auth, transport, status200 body failure, complete success and complete HTTP error through the compiled Rust sink; their source checks include invalid metadata and poisoned payload rejection without logging/replay.

Optional valuable explicit coverage: add a historical **mail_cli exact-only** native positive fixture (the existing old/enriched positive fixtures are mail_api), and a valid closed client boundary injected into a mail_api negative fixture. Source reasoning finds both requested contracts implemented; this is coverage hardening, not a diagnosed defect. The deterministic frozen-duration test proves insertion uses the supplied frozen value; source ordering establishes snapshot-before-db. No actual SQLite contention timing experiment was run by this reviewer.

Reader rollout must precede enriched producer rollout; neither is authorized or proven deployed by this patch. Full auth/background/JSON/filesystem coverage and detached export-loss visibility remain incomplete and honestly documented. Current durable pending rows do not mean useful user-visible upload failure diagnostics. Do not mark full runtime observability complete or introduce a new framework to conceal that missing last-upload outcome.

## External grounding

[OpenTelemetry HTTP span conventions](https://opentelemetry.io/docs/specs/semconv/http/http-spans/) distinguish an observed HTTP response status from errors receiving the response/body and require explicit duration scope. This supports retaining status200 while recording attempt failure; it does not make these safe application Queue events native platform spans or establish deployed privacy.

The best next evidence is hosted full CI with current-source CLI and actual compiled native Queue tests, followed only by separately admitted reader-first rollout. The native tracing/provider privacy canary remains a distinct acceptance boundary.
