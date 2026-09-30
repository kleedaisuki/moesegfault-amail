/** Validate the pinned stable Miniflare option shape before the costly Rust build. */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { stripSqlLineComments } from "./sql-comments.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

let outboundCalls = 0;
const here = path.dirname(fileURLToPath(import.meta.url));
const originalCwd = process.cwd();
// Miniflare defaults modulesRoot to cwd, not the entrypoint's directory.
// Use the nested cwd so removing the explicit root reproduces the Rust graph failure.
process.chdir(path.join(here, "module-smoke"));
let mf;
try {
  mf = new Miniflare({
    cf: false,
    workers: [{
      name: "amail-config-smoke",
      modules: true,
      scriptPath: path.join(here, "module-smoke/entry.mjs"),
      modulesRoot: here,
      modulesRules: workerModuleRules,
      // Stable v4's workerd supports dates only through 2026-08-06.
      compatibilityDate: "2026-08-06",
      d1Databases: ["MAIL_DB"],
      outboundService(request) {
        assert.equal(request.url, "https://fixture.invalid/ok");
        outboundCalls++;
        return new Response("ok");
      },
    }],
  });
  const response = await mf.dispatchFetch("http://synthetic.invalid/");
  assert.equal(await response.text(), "ok");
  assert.equal(outboundCalls, 1, "synthetic fetch must use the local egress handler");
  const { MAIL_DB: db } = await mf.getBindings();
  assert.equal(typeof db.prepare, "function");
  assert.equal(stripSqlLineComments("SELECT '-- kept'; -- dropped\nSELECT 1;"),
    "SELECT '-- kept'; \nSELECT 1;");
  const migrationsDir = path.resolve(here, "../../../crates/mail-worker/migrations");
  await applyMigrations(db, migrationsDir);
  const table = await db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='addresses'").first();
  assert.equal(table?.name, "addresses", "commented migrations must apply to local D1");
  const column = await db.prepare("SELECT name FROM pragma_table_info('addresses') WHERE name='next_reconcile_at'").first();
  assert.equal(column?.name, "next_reconcile_at", "the latest migration must apply to local D1");
} finally {
  try {
    await mf?.dispose();
  } finally {
    process.chdir(originalCwd);
  }
}
