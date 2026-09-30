/** Apply the production migrations to isolated test D1 in filename order. */
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { stripSqlLineComments } from "./sql-comments.mjs";

/** Frame this repository's migrations as one-line statements for D1.exec(). */
export function migrationStatements(sql) {
  const statements = [];
  let lines = [];
  let trigger = false;
  for (const raw of sql.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (lines.length === 0) trigger = /^CREATE\s+TRIGGER\b/i.test(line);
    lines.push(line);
    const semicolon = line.indexOf(";");
    if (!trigger && semicolon >= 0) {
      assert.equal(semicolon, line.length - 1,
        "unsupported multiple or quoted semicolons in one migration line");
    }
    const complete = trigger ? /^END;$/i.test(line) : semicolon >= 0;
    if (!complete) continue;
    statements.push(lines.join(" "));
    lines = [];
  }
  assert.equal(lines.length, 0, "migration ended with an incomplete statement");
  assert.ok(statements.length > 0, "migration has no SQL statements");
  return statements;
}

/** Keep smoke and Rust boundary setup on the same D1 migration contract. */
export async function applyMigrations(db, migrationsDir) {
  const names = (await readdir(migrationsDir)).filter((name) => /^\d{4}_.*\.sql$/.test(name)).sort();
  assert.ok(names.length >= 8, "address scheduling migration is required");
  for (let n = 0; n < names.length; n++) {
    const name = names[n];
    assert.equal(name.slice(0, 4), String(n + 1).padStart(4, "0"), "migrations must be contiguous");
    const sql = await readFile(path.join(migrationsDir, name), "utf8");
    // D1.exec splits on newlines, not SQL statement boundaries.
    for (const statement of migrationStatements(stripSqlLineComments(sql))) {
      await db.exec(statement);
    }
  }
}
