/** Native read-body rejection through the actual built Rust/Wasm scheduled entry. */
import assert from "node:assert/strict";
import test from "node:test";
import { fixture, accepted, indexedText } from "./outbound-recovery-fixture.mjs";

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
