/** Apply the production migrations to isolated test D1 in filename order. */
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { stripSqlLineComments } from "./sql-comments.mjs";

/** Keep smoke and Rust boundary setup on the same D1 migration contract. */
export async function applyMigrations(db, migrationsDir) {
  const names = (await readdir(migrationsDir)).filter((name) => /^\d{4}_.*\.sql$/.test(name)).sort();
  assert.ok(names.length >= 8, "address scheduling migration is required");
  for (let n = 0; n < names.length; n++) {
    const name = names[n];
    assert.equal(name.slice(0, 4), String(n + 1).padStart(4, "0"), "migrations must be contiguous");
    const sql = await readFile(path.join(migrationsDir, name), "utf8");
    await db.exec(stripSqlLineComments(sql));
  }
}
