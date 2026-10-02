/** Accepted projection integrity through built Rust/Wasm and isolated D1/R2. */
import assert from "node:assert/strict";
import test from "node:test";
import { fixture, accepted, indexedText, text, sender, issuer } from "./outbound-recovery-fixture.mjs";

/** Provider acceptance is never replayed; indexing replay preserves content and quota. */
test("accepted 4MB stored ZIP converges exactly; repeated Cron is idempotent", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "success");
  await tick();
  assert.equal(await indexedText(db, "success"), text);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks").first()).n, 66);
  const before = await db.prepare("SELECT used_bytes FROM storage_usage").first();
  await tick();
  assert.deepEqual(await db.prepare("SELECT used_bytes FROM storage_usage").first(), before);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages").first()).n, 1);
  assert.equal((await db.prepare("SELECT state FROM send_requests").first()).state, "sent");
}));

/** A failed chunk write must remain accepted and be repaired without duplicate bytes. */
test("partial chunk failure remains durable and repairs on a later tick", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "partial");
  await db.exec("CREATE TRIGGER fail_chunk BEFORE INSERT ON message_text_chunks WHEN NEW.chunk_index=3 BEGIN SELECT RAISE(FAIL,'synthetic chunk fault'); END;");
  await tick();
  assert.equal((await db.prepare("SELECT state FROM send_requests").first()).state, "accepted");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages").first()).n, 0);
  // Cleanup/rollback may remove staged chunks; durability concerns accepted state,
  // invisibility and exact eventual repair, not preservation of orphan rows.
  const staged = (await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks WHERE message_id='partial'").first()).n;
  assert.ok(staged >= 0 && staged <= 2, `chunk-3 fault permits at most two staged chunks, saw ${staged}`);
  await db.exec("DROP TRIGGER fail_chunk;");
  // Explicitly model the durable five-minute due slot expiring; no wall wait.
  await db.exec("UPDATE send_requests SET index_next_attempt_at=0 WHERE message_id='partial';");
  await tick();
  assert.equal(await indexedText(db, "partial"), text);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks").first()).n, 66);
}));

/** A user tombstone must remain authoritative even if accepted indexing is retried. */
test("existing user tombstone is not made visible by accepted recovery", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "deleted", "short");
  await tick();
  await db.exec("UPDATE messages SET deleted_at=1 WHERE id='deleted';");
  await db.exec("UPDATE send_requests SET state='accepted',index_next_attempt_at=0 WHERE message_id='deleted';");
  await tick();
  assert.equal(await indexedText(db, "deleted"), null);
}));

/**
 * Missing-archive fairness is a documented workload, not an immediate-tick test:
 * a bounded scheduler may use LIMIT5 and future retry times. A hosted fairness
 * fixture needs an explicit cap/cadence/backoff contract and clock control.
 */

/** A surviving exact-owned tombstone terminalizes without re-staging content. */
test("owned accepted tombstone with archive terminalizes without chunk staging", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "race");
  await tick();
  await db.exec("UPDATE messages SET deleted_at=1 WHERE id='race';");
  await db.exec("UPDATE send_requests SET state='accepted',index_next_attempt_at=0 WHERE message_id='race';");
  assert.ok(await bucket.get("messages/race.zip"), "archive still exists before tombstone recovery");
  await db.exec("CREATE TABLE tombstone_chunk_audit(n INTEGER NOT NULL);");
  await db.exec("INSERT INTO tombstone_chunk_audit VALUES(0);");
  await db.exec("CREATE TRIGGER count_tombstone_staging BEFORE INSERT ON message_text_chunks WHEN NEW.message_id='race' BEGIN UPDATE tombstone_chunk_audit SET n=n+1; END;");
  await tick();
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='race'").first()).state, "sent");
  assert.equal(await indexedText(db, "race"), null);
  assert.equal((await db.prepare("SELECT n FROM tombstone_chunk_audit").first()).n, 0, "terminalizing a surviving tombstone must not stage body chunks");
  await tick();
  for (const [table, key] of [["messages", "id"], ["message_text_chunks", "message_id"], ["storage_reservations", "id"], ["embedding_work", "message_id"]]) {
    assert.equal((await db.prepare(`SELECT COUNT(*) AS n FROM ${table} WHERE ${key}='race'`).first()).n, 0);
  }
  assert.equal(await bucket.get("messages/race.zip"), null);
}));

/** A delete arriving after INSERT and before sent must win over later indexing. */
test("delete between message insert and send transition stays absent on retry", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "late-delete", "short");
  await db.exec("CREATE TRIGGER delete_after_insert AFTER INSERT ON messages WHEN NEW.id='late-delete' BEGIN UPDATE messages SET deleted_at=1 WHERE id=NEW.id; END;");
  await tick();
  await tick();
  assert.equal(await indexedText(db, "late-delete"), null);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks WHERE message_id='late-delete'").first()).n, 0);
}));

/** A durable accepted journal does not authorize another owner's reservation. */
test("accepted recovery refuses a storage reservation belonging to another owner", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "lost-owner", "short");
  await db.exec("UPDATE storage_reservations SET owner_sub='foreign-owner' WHERE id='lost-owner';");
  await tick();
  assert.equal(await indexedText(db, "lost-owner"), null);
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='lost-owner'").first()).state, "accepted");
}));

/** ID collisions must not overwrite/search-corrupt foreign content or mark it sent. */
test("accepted recovery cannot mutate a foreign existing message row", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "foreign-row");
  await db.prepare("INSERT INTO messages(id,address,owner_iss,owner_sub,direction,sender,recipients_json,subject,body_text,metadata_json,received_at,is_read,has_html,has_text,attachment_count,r2_key,size_bytes,storage_bytes) VALUES('foreign-row',?1,?2,'foreign-owner','inbound',?1,'[]','Foreign fixture','original foreign text','{}',?3,0,0,1,0,'messages/foreign-row.zip',21,21)")
    .bind(sender, issuer, Date.now()).run();
  await tick();
  assert.equal(await indexedText(db, "foreign-row"), "original foreign text");
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='foreign-row'").first()).state, "accepted");
}));

/** Final projection publication and terminal journal state must fail atomically. */
test("failure of final sent transition does not expose a partial projection", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "final-fault", "short");
  await db.exec("CREATE TRIGGER fail_final BEFORE UPDATE OF state ON send_requests WHEN NEW.message_id='final-fault' AND NEW.state='sent' BEGIN SELECT RAISE(ABORT,'synthetic final publication fault'); END;");
  await tick();
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages WHERE id='final-fault'").first()).n, 0, "failed final batch must roll back message publication");
  assert.equal((await db.prepare("SELECT state FROM storage_reservations WHERE id='final-fault'").first()).state, "reserved");
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='final-fault'").first()).state, "accepted");
  await db.exec("DROP TRIGGER fail_final;");
  await db.exec("UPDATE send_requests SET index_next_attempt_at=0 WHERE message_id='final-fault';");
  await tick();
  assert.equal(await indexedText(db, "final-fault"), "short");
}));

/** An unexpired projection lease is exclusive; expiry permits durable recovery. */
test("active projection lease defers Cron; expired lease is replaced and repaired", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "lease", "lease body");
  await db.prepare("UPDATE send_requests SET index_projection_token='synthetic-old-token',index_projection_lease_until=?1 WHERE message_id='lease'").bind(Date.now() + 20 * 60_000).run();
  await tick();
  assert.equal(await indexedText(db, "lease"), null);
  const active = await db.prepare("SELECT state,index_projection_token FROM send_requests WHERE message_id='lease'").first();
  assert.equal(active.state, "accepted");
  assert.equal(active.index_projection_token, "synthetic-old-token");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks WHERE message_id='lease'").first()).n, 0);
  // Deterministically model deadline expiry, not an immediate-tick time assumption.
  await db.exec("UPDATE send_requests SET index_projection_lease_until=0 WHERE message_id='lease';");
  await tick();
  assert.equal(await indexedText(db, "lease"), "lease body");
  const finished = await db.prepare("SELECT state,index_projection_token,index_projection_lease_until FROM send_requests WHERE message_id='lease'").first();
  assert.equal(finished.state, "sent");
  assert.equal(finished.index_projection_token, null);
  assert.equal(finished.index_projection_lease_until, 0);
}));

/** Legacy accepted projection repair revokes stale semantics and preserves read state. */
test("legacy accepted repair clears vectors, revokes embedding lease and removes stale suffix", async () => fixture(async ({ db, bucket, tick }) => {
  const replacement = "correct projection ".repeat(8000);
  await accepted(db, bucket, "legacy", replacement);
  await tick();
  const oldVector = JSON.stringify([1, ...Array(255).fill(0)]);
  await db.prepare("UPDATE messages SET body_text='obsolete projection',is_read=0,embedding_json=?1,embedding_model='qwen/qwen3-embedding-8b',embedding_dimensions=256,embedding_input_version=1,embedding_truncated=0 WHERE id='legacy'").bind(oldVector).run();
  await db.exec("INSERT INTO message_text_chunks(message_id,chunk_index,body) VALUES('legacy',99,'obsolete suffix');");
  await db.exec("UPDATE send_requests SET state='accepted',index_next_attempt_at=0 WHERE message_id='legacy';");
  await db.prepare("INSERT INTO embedding_work(message_id,owner_iss,owner_sub,received_at,attempts,lease_until,lease_token) VALUES('legacy',?1,?2,?3,7,?4,'synthetic-old-embedding-token')")
    .bind("https://synthetic.invalid", "synthetic-recovery-owner", Date.now(), Date.now() + 900_000).run();
  await tick();
  assert.equal(await indexedText(db, "legacy"), replacement);
  const message = await db.prepare("SELECT is_read,embedding_json,embedding_model,embedding_dimensions,embedding_input_version,embedding_truncated FROM messages WHERE id='legacy'").first();
  assert.equal(message.is_read, 0, "repair preserves the user's unread flag");
  for (const key of ["embedding_json", "embedding_model", "embedding_dimensions", "embedding_input_version", "embedding_truncated"]) assert.equal(message[key], null, `${key} belongs to the obsolete projection`);
  const work = await db.prepare("SELECT attempts,lease_until,lease_token FROM embedding_work WHERE message_id='legacy'").first();
  assert.deepEqual(work, { attempts: 0, lease_until: 0, lease_token: null });
  // Exercise the persisted lease fence of a response that was already in flight.
  const late = await db.prepare("UPDATE messages SET embedding_json=?1 WHERE id='legacy' AND deleted_at IS NULL AND EXISTS(SELECT 1 FROM embedding_work WHERE message_id='legacy' AND lease_token='synthetic-old-embedding-token')").bind(oldVector).run();
  assert.equal(late.meta.changes, 0);
  assert.equal((await db.prepare("SELECT embedding_json FROM messages WHERE id='legacy'").first()).embedding_json, null);
}));

/** Missing ZIP with a surviving exact-owned tombstone is recoverable deletion intent. */
test("accepted owned tombstone terminalizes after legacy GC already deleted ZIP", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "zipless-tombstone", "deleted body");
  await tick();
  await db.exec("UPDATE messages SET deleted_at=1 WHERE id='zipless-tombstone';");
  await db.exec("UPDATE send_requests SET state='accepted',index_next_attempt_at=0 WHERE message_id='zipless-tombstone';");
  await bucket.delete("messages/zipless-tombstone.zip");
  await tick();
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='zipless-tombstone'").first()).state, "sent");
  assert.equal(await indexedText(db, "zipless-tombstone"), null);
  await tick();
  for (const [table, key] of [["messages", "id"], ["message_text_chunks", "message_id"], ["storage_reservations", "id"], ["embedding_work", "message_id"]]) {
    assert.equal((await db.prepare(`SELECT COUNT(*) AS n FROM ${table} WHERE ${key}='zipless-tombstone'`).first()).n, 0);
  }
}));

/** UTF-8 byte limits must not split multibyte content during accepted projection. */
test("maximum mixed-width UTF-8 survives native staging and replay exactly", async () => fixture(async ({ db, bucket, tick }) => {
  const body = "火🔥".repeat(571_428) + "xxxx";
  assert.equal(Buffer.byteLength(body), 4_000_000);
  await accepted(db, bucket, "utf8", body);
  await tick();
  assert.equal(await indexedText(db, "utf8"), body);
  const usage = await db.prepare("SELECT used_bytes FROM storage_usage").first();
  await tick();
  assert.equal(await indexedText(db, "utf8"), body);
  assert.deepEqual(await db.prepare("SELECT used_bytes FROM storage_usage").first(), usage);
}));
