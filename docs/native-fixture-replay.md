# Native fixture replay

Status: source under hosted validation; a diagnostic run is not source/release
acceptance. Use this lane when one Miniflare/workerd fixture changes but Rust,
SDK/build scripts, compiler/lockfiles and generated-product inputs do not.

Normal CI still builds once and runs every native suite. Replaying a failed source
run's **successful producer** is useful to diagnose a fixture SDK-shape mismatch;
it does not turn that failed CI into success. The manual diagnostic workflow
selects one known package-owned test file, downloads the original producer's
fixed artifact ID, checks compiler/source/run/file hashes and rejects any changed
compilation/unknown input before restoring. Current fixture source and original
build source/run are reported separately. There are no provider Secrets, Rust
build, mailbox action or deployment permissions in this lane.

Example after source validation/merge:

    gh workflow run native-fixture.yml --ref <reviewed-fixture-branch> \
      -f build_run_id=<completed-source-run> -f fixture=trace-sink.test.mjs

The conservative changed-file allowance covers repo docs/skills and native test
.mjs files, plus this diagnostic helper/workflow/test. It is not a compiler input
hash framework or a general old-artifact promotion mechanism. Unknown changes,
CI/build-policy changes or expired/ambiguous artifacts require normal CI. The
original artifact helper retains its strict source/run/attempt checks; replay
uses those original coordinates explicitly only after the unchanged-build-input
check. Full current-source CI remains required before merge/release.

This lane directly addresses fixture iteration latency: prior native Queue
investigations rebuilt unchanged Rust and executed 102 unrelated core tests to
learn about one three-test fixture. Observe the real replay duration/cache output
before claiming a speedup. Source-only tests check changed-input refusal, owned
file selection and read-only workflow contracts. Actual hosted replay acceptance
is still required; never run native tests on the developer machine.
