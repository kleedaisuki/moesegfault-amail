# Native receipt atomicity integration review

Date: 2026-10-02. Root review bound to PR80 exact source
`cbb4e0a0380f491a1a77da9ef9d69ecb825363aa`, base `c874231`.
No substantive defect found in the bounded three-file source delta.

The receipt is the ownership/recovery boundary preceding external mutations.
Direct truncation could destroy a previously complete nonce/resource journal.
The new local writer serializes first, writes a unique same-directory temporary
file, flushes and fsyncs it, closes before replacement, atomically replaces the
receipt, and syncs the parent directory on POSIX. It retains the JSON schema and
single-writer policy rather than introducing a persistence framework.

Static review confirmed failures before replacement leave the old bytes intact;
cleanup never deletes the old receipt. Directory-sync failure after replacement
leaves the complete new receipt and raises, preventing subsequent side effects;
it is not falsely labelled a rollback. Windows closes the temporary file before
replacement but has no claimed portable directory-fsync/power-loss guarantee.

Exact-source [CI36903987695](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36903987695)
and [syntax36903987310](https://github.com/kleedaisuki/moesegfault-amail/actions/runs/36903987310)
passed. Seven new hosted fixtures exercise partial write, file sync, replacement,
serialization and directory-sync failures, and mutation-admission ordering.
They use repository-local temporary state. Actual provider operations and Windows
filesystem runtime acceptance were not performed or inferred.

This is source/hosted fault acceptance, not a new native trace or live cleanup
verdict. Actual run36896672169 remains a pre-write SSL403 refusal; current source
still requires the complete TLS/absence gates. No local runtime/build/install,
provider request, additional dispatch or mail action was part of this review.
