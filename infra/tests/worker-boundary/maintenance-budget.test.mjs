/** Actual built scheduled entry preserves later maintenance under outbound backlog. */
import assert from "node:assert/strict";
import test from "node:test";
import { fixture, accepted } from "./outbound-recovery-fixture.mjs";

/** SQL-trigger counts are lower-bound evidence, not remote-plan quota emulation. */
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
