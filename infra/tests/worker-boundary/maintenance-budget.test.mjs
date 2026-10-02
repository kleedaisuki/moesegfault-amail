/** Actual built scheduled entry preserves later maintenance under outbound backlog. */
import assert from "node:assert/strict";
import test from "node:test";
import { fixture, accepted, indexedText } from "./outbound-recovery-fixture.mjs";

/** Outbound backlog must not starve privacy retention cleanup. */
test("shared maintenance grant bounds accepted backlog and preserves later cleanup", async () => fixture(async ({ db, bucket, tick }) => {
  for (let n = 0; n < 20; n++) await accepted(db, bucket, `maintenance-${String(n).padStart(2, "0")}`);
  await db.exec("CREATE TABLE maintenance_chunk_audit(n INTEGER NOT NULL);");
  await db.exec("INSERT INTO maintenance_chunk_audit VALUES(0);");
  await db.exec("CREATE TRIGGER maintenance_count_chunks AFTER INSERT ON message_text_chunks BEGIN UPDATE maintenance_chunk_audit SET n=n+1; END;");
  // This fixed existing cleanup target is serviced after the outbound phase.
  await db.prepare("INSERT INTO provider_events(event_id,provider_id,local_message_id,owner_iss,owner_sub,recipient,kind,occurred_at,received_at) VALUES('maintenance-old-event','synthetic-provider','synthetic-message','https://synthetic.invalid','synthetic-owner','synthetic@example.invalid','delivered',0,0)").run();
  await tick();
  const { n } = await db.prepare("SELECT n FROM maintenance_chunk_audit").first();
  assert.equal(n, 5 * 66, "five maximum-valid texts consume their own grant, not the other phases'");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM send_requests WHERE state='sent'").first()).n, 5);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM send_requests WHERE state='accepted'").first()).n, 15);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM provider_events WHERE event_id='maintenance-old-event'").first()).n, 0, "later privacy retention keeps its independent statement grant");
}));

/** Missing, malformed and foreign-owned poison prefixes rotate before R2/parse. */
test("accepted due order services healthy work behind three poison batches", async () => fixture(async ({ db, bucket, tick }) => {
  for (let n = 0; n < 5; n++) await accepted(db, bucket, `poison-missing-${n}`, "missing", false);
  for (let n = 0; n < 5; n++) {
    const id = `poison-corrupt-${n}`;
    await accepted(db, bucket, id, "corrupt");
    await bucket.put(`messages/${id}.zip`, "not the immutable committed ZIP");
  }
  for (let n = 0; n < 5; n++) {
    const id = `poison-foreign-${n}`;
    await accepted(db, bucket, id, "foreign");
    await db.prepare("UPDATE storage_reservations SET owner_sub='synthetic-foreign' WHERE id=?1").bind(id).run();
  }
  for (let n = 0; n < 3; n++) await accepted(db, bucket, `healthy-${n}`, `healthy body ${n}`);
  // Make the ordering independent of fixture preparation/clock resolution.
  await db.exec("UPDATE send_requests SET created_at=CASE WHEN message_id LIKE 'poison-missing-%' THEN 1 WHEN message_id LIKE 'poison-corrupt-%' THEN 2 WHEN message_id LIKE 'poison-foreign-%' THEN 3 ELSE 4 END;");
  for (let turn = 0; turn < 3; turn++) {
    await tick();
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM send_requests WHERE index_next_attempt_at>0").first()).n, (turn + 1) * 5);
    assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM messages").first()).n, 0);
  }
  await tick();
  for (let n = 0; n < 3; n++) assert.equal(await indexedText(db, `healthy-${n}`), `healthy body ${n}`);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM send_requests WHERE state='accepted'").first()).n, 15);
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM message_text_chunks WHERE message_id LIKE 'poison-%'").first()).n, 0);
}));

/** A live foreground projection lease consumes no due slot or Cron item limit. */
test("five live projection leases do not hide an unleased accepted item", async () => fixture(async ({ db, bucket, tick }) => {
  for (let n = 0; n < 5; n++) await accepted(db, bucket, `leased-${n}`, "leased");
  await accepted(db, bucket, "unleased", "unleased body");
  await db.prepare("UPDATE send_requests SET index_projection_token='synthetic-live-token',index_projection_lease_until=?1 WHERE message_id LIKE 'leased-%'").bind(Date.now() + 1_200_000).run();
  await tick();
  assert.equal(await indexedText(db, "unleased"), "unleased body");
  assert.equal((await db.prepare("SELECT COUNT(*) AS n FROM send_requests WHERE message_id LIKE 'leased-%' AND state='accepted' AND index_next_attempt_at=0 AND index_projection_token='synthetic-live-token'").first()).n, 5);
}));

/** A failed item preserves its retry journal but does not abort the selected batch. */
test("accepted projection fault still permits the following due item", async () => fixture(async ({ db, bucket, tick }) => {
  await accepted(db, bucket, "fault-first", "a".repeat(180_000));
  await accepted(db, bucket, "good-next", "good after fault");
  await db.exec("UPDATE send_requests SET created_at=CASE WHEN message_id='fault-first' THEN 1 ELSE 2 END;");
  await db.exec("CREATE TRIGGER maintenance_poison_chunk BEFORE INSERT ON message_text_chunks WHEN NEW.message_id='fault-first' AND NEW.chunk_index=2 BEGIN SELECT RAISE(FAIL,'synthetic item fault'); END;");
  await tick();
  assert.equal((await db.prepare("SELECT state FROM send_requests WHERE message_id='fault-first'").first()).state, "accepted");
  assert.equal(await indexedText(db, "fault-first"), null);
  assert.equal(await indexedText(db, "good-next"), "good after fault");
}));
