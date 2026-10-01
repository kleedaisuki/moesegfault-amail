# Conservative PR compilation scope

## Why this changes iteration cost

The realm-harness corrections changed Python-only code but each automatic PR run
still executed three CLI platforms, native/Wasm builds and every workerd suite.
Actual final Queue/Routing/embedding timeout discriminators deliberately consume
real timer durations, so cache hits cannot remove their runtime. This is avoidable
for a proven unrelated Python correction, not a reason to shorten useful tests.

Keep the existing infrastructure/source/workflow contracts mandatory and select
only the expensive CLI, Worker and Astro PR lanes with a complete committed Git
diff. Component paths map to their consumers. Workspace/Cargo, toolchain,
workflow, selection/cache machinery, shared and unknown inputs request all lanes.
Infrastructure Python/provider/deployment scripts run in the existing full
infrastructure lane. Site content runs Astro; native boundary fixtures run Worker.
Main/trusted push, manual checks, deployment/release prerequisites remain full,
regardless of changed paths. The existing long-lived staging branch predicate
and manual provider confirmations are not changed.

## Contract and failure behavior

`infra/ci/pr_scope.py` validates both event SHAs and invokes git with argument
arrays, NUL-delimited paths, bounded output and a timeout. It never interpolates
untrusted filenames into a shell and emits only three fixed boolean outputs.
Missing/invalid metadata, failed/truncated diff, invalid UTF-8 or unknown inputs
fall back to full. A fresh credential-free checkout owns scope selection. No
secrets, provider operation, job environment, dispatch permission, cache write or
acceptance artifact is added to the selector. Infrastructure still runs and tests
the selector and all workflow contracts even when expensive lanes are skipped.

Skipped PR lanes are not exact-SHA tested artifacts or release acceptance. The
full main/manual run remains the source for promotion and live artifact reuse;
never substitute a scoped PR green badge for an unexecuted suite. Existing exact
Worker build cache semantics are retained, including trusted-push-only saves.

## Verification and limitations

Seven hosted synthetic contracts cover path consumers, unrelated Python/docs,
unknown/shared/full selection, unions, non-PR full behavior, complete diff and
failure fallback, and workflow guard/credential isolation. Local work is Python
AST/whitespace and source inspection only. The implementation first PR itself
changes workflow/selector inputs, so it correctly requests all source lanes.
Hosted CI is required before merge; actual latency improvement must be observed
on a later Python-only PR, not inferred from selector unit tests alone.

This is mature dependency-oriented CI design, not an early-exit acceptance hack.
Paths remain a conservative interface: a new consumer hidden behind an existing
Python path must either extend the rules or choose the default full path. The
main/manual full lane provides the independent integration check.
