/** Native read-body rejection through the actual built Rust/Wasm scheduled entry. */
import assert from "node:assert/strict";
import test from "node:test";
import { fixture, accepted, indexedText, text } from "./outbound-recovery-fixture.mjs";

for (const [mode, reads] of [["metadata", 0], ["single", 1], ["total", 2]]) {
  /** Metadata/actual chunk caps reject before arrayBuffer/copying the bad chunk. */
  test(`accepted R2 ${mode} overflow is canceled and remains durable`, async () => fixture(async ({ db, bucket, tick, r2Stats }) => {
    const id = `archive-${mode}`;
    await accepted(db, bucket, id, "synthetic retained archive");
    await accepted(db, bucket, "healthy-following", "healthy after rejected stream");
    await db.exec(`UPDATE send_requests SET created_at=CASE WHEN message_id='${id}' THEN 1 ELSE 2 END;`);
    await tick();
    assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id=?1").bind(id).first()).state, "accepted");
    assert.equal(await indexedText(db, id), null);
    assert.ok(await bucket.get(`messages/${id}.zip`), "rejected read does not delete the retained source");
    assert.equal(await indexedText(db, "healthy-following"), "healthy after rejected stream");
    assert.deepEqual(await r2Stats(), { gets: 2, reads, cancels: 1, arrayBuffers: 0 });
  }, { observeR2: true }));
}

/** A healthy nineteen-second body must not be treated as a ten-second stall. */
test("66 native R2 chunks at 300ms finish one whole accepted archive", { timeout: 70_000 }, async () => fixture(async ({ db, bucket, tick, r2Stats }) => {
  await accepted(db, bucket, "archive-slow-valid");
  await accepted(db, bucket, "untouched-following", "following body");
  await db.exec("UPDATE send_requests SET created_at=CASE WHEN message_id='archive-slow-valid' THEN 1 ELSE 2 END;");
  const started = Date.now();
  await tick(1_680_000_300_000);
  assert.ok(Date.now() - started >= 19_800, "actual platform timers, not an accelerated logical clock");
  assert.equal(await indexedText(db, "archive-slow-valid"), text);
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='archive-slow-valid'").first()).state, "sent");
  assert.equal((await db.prepare("SELECT index_next_attempt_at FROM send_requests WHERE message_id='untouched-following'").first()).index_next_attempt_at, 0);
  assert.deepEqual(await r2Stats(), { gets: 1, reads: 67, cancels: 0, arrayBuffers: 0 });
}, { observeR2: true }));

/** A pending native read shares one thirty-second absolute body deadline. */
test("stalled native R2 body is canceled without publication or next-item admission", { timeout: 45_000 }, async () => fixture(async ({ db, bucket, tick, r2Stats }) => {
  await accepted(db, bucket, "archive-stall", "retained stalled body");
  await accepted(db, bucket, "untouched-following", "following body");
  await db.exec("UPDATE send_requests SET created_at=CASE WHEN message_id='archive-stall' THEN 1 ELSE 2 END;");
  const started = Date.now();
  await tick(1_680_000_300_000);
  assert.ok(Date.now() - started >= 29_000 && Date.now() - started < 40_000);
  assert.equal(await indexedText(db, "archive-stall"), null);
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='archive-stall'").first()).state, "accepted");
  assert.ok(await bucket.get("messages/archive-stall.zip"));
  assert.equal((await db.prepare("SELECT index_next_attempt_at FROM send_requests WHERE message_id='untouched-following'").first()).index_next_attempt_at, 0);
  assert.deepEqual(await r2Stats(), { gets: 1, reads: 1, cancels: 1, arrayBuffers: 0 });
}, { observeR2: true }));

/** Expiration while awaiting GET cannot buy a renewed body/parse allowance. */
test("late native R2 GET cancels returned body before its first read", async () => fixture(async ({ db, bucket, tick, r2Stats }) => {
  await accepted(db, bucket, "archive-late-get", "late object body");
  await tick(1_680_000_300_000);
  assert.equal(await indexedText(db, "archive-late-get"), null);
  assert.deepEqual(await r2Stats(), { gets: 1, reads: 0, cancels: 1, arrayBuffers: 0 });
}, { observeR2: true }));

/** Cancellation may be initiated, but its untrusted promise cannot own Cron. */
test("never-settling native R2 cancel cannot block following healthy work", { timeout: 15_000 }, async () => fixture(async ({ db, bucket, tick, r2Stats }) => {
  await accepted(db, bucket, "archive-cancel-stall", "oversized metadata");
  await accepted(db, bucket, "healthy-following", "healthy after untrusted cancel");
  await db.exec("UPDATE send_requests SET created_at=CASE WHEN message_id='archive-cancel-stall' THEN 1 ELSE 2 END;");
  await tick(1_680_000_300_000);
  assert.equal(await indexedText(db, "healthy-following"), "healthy after untrusted cancel");
  assert.deepEqual(await r2Stats(), { gets: 2, reads: 0, cancels: 1, arrayBuffers: 0 });
}, { observeR2: true }));
