/** Check the test-only D1 migration adapter against SQL quoting and real files. */
import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { migrationStatements } from "./migration-fixture.mjs";
import { stripSqlLineComments } from "./sql-comments.mjs";

const migrationsDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)),
  "../../../crates/mail-worker/migrations");

test("line comments are removed without changing quoted SQL", () => {
  const source = "-- heading;\nSELECT '-- text', \"id--name\", `tick--name`, [bracket--name], 'it''s -- text'; -- tail;\n";
  assert.equal(stripSqlLineComments(source),
    "SELECT '-- text', \"id--name\", `tick--name`, [bracket--name], 'it''s -- text';");
});

test("all production migrations retain SQL statements after normalization", async () => {
  const names = (await readdir(migrationsDir)).filter((name) => /^\d{4}_.*\.sql$/.test(name)).sort();
  assert.ok(names.length >= 8);
  for (const name of names) {
    const sql = stripSqlLineComments(await readFile(path.join(migrationsDir, name), "utf8"));
    assert.ok(sql.length > 0, `${name} became empty`);
    assert.match(sql, /\b(?:CREATE|ALTER|INSERT|UPDATE)\b/, `${name} lost its statements`);
    const statements = migrationStatements(sql);
    assert.ok(statements.every((statement) => !/\r|\n/.test(statement) && statement.endsWith(";")),
      `${name} must contain complete one-line statements for D1.exec`);
  }
});
