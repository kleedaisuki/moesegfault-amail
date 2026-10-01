/** Historical budget reproduction, now assigned to the hosted resource-contract suite. */
import assert from "node:assert/strict";
import test from "node:test";
import { fixture, accepted } from "./outbound-recovery-fixture.mjs";

/** The writes alone must not exceed Paid's entire per-invocation D1 allowance. */
test("twenty accepted 4MB archives obey a thousand-query invocation lower bound", async () => fixture(async ({ db, bucket, tick }) => {
  for (let n = 0; n < 20; n++) await accepted(db, bucket, `budget-${n}`);
  await db.exec("CREATE TABLE chunk_write_audit(n INTEGER NOT NULL);");
  await db.exec("INSERT INTO chunk_write_audit VALUES(0);");
  await db.exec("CREATE TRIGGER count_chunks AFTER INSERT ON message_text_chunks BEGIN UPDATE chunk_write_audit SET n=n+1; END;");
  await tick();
  const { n } = await db.prepare("SELECT n FROM chunk_write_audit").first();
  assert.ok(n <= 1000, `extra chunk statements alone consumed ${n}; other Cron statements also need allowance`);
}));
