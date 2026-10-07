/**
 * Synthetic-only hosted workerd contract reproductions for accepted-send recovery.
 * Shared native storage and fail-closed egress for recovery contracts.
 * No real OIDC, SMTP, Cloudflare, or OpenRouter endpoint is contacted.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Miniflare } from "miniflare";
import { applyMigrations, seedResourceAccount } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const worker = path.join(root, "crates/mail-worker");
/** Synthetic mailbox shared by isolated fixture seeding and collision tests. */
export const sender = "recovery-synthetic@mail-staging.moesegfault.dev";
const owner = "synthetic-recovery-owner";
/** Synthetic immutable owner issuer for fixture-only journal ownership. */
export const issuer = "https://synthetic.invalid";
export const text = "x".repeat(4_000_000); // Decimal 4MB, not 4MiB: 67 parts, 66 additional writes.

/** IEEE CRC32 for independent, dependency-free stored ZIP fixtures. */
function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** Build a standard noncompressed ZIP independently of the production archive packer. */
function draftZip(body) {
  const manifest = `version = 1\nfrom = '${sender}'\nto = ['synthetic@example.invalid']\nsubject = 'Synthetic recovery'\n`;
  const local = [], central = [];
  let offset = 0;
  for (const [filename, value] of [["manifest.toml", manifest], ["body.txt", body]]) {
    const name = Buffer.from(filename), data = Buffer.from(value), checksum = crc32(data);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50); header.writeUInt16LE(20, 4);
    header.writeUInt32LE(checksum, 14); header.writeUInt32LE(data.length, 18);
    header.writeUInt32LE(data.length, 22); header.writeUInt16LE(name.length, 26);
    local.push(header, name, data);
    const directory = Buffer.alloc(46);
    directory.writeUInt32LE(0x02014b50); directory.writeUInt16LE(20, 4); directory.writeUInt16LE(20, 6);
    directory.writeUInt32LE(checksum, 16); directory.writeUInt32LE(data.length, 20);
    directory.writeUInt32LE(data.length, 24); directory.writeUInt16LE(name.length, 28);
    directory.writeUInt32LE(offset, 42);
    central.push(directory, name);
    offset += header.length + name.length + data.length;
  }
  const directory = Buffer.concat(central), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50); end.writeUInt16LE(2, 8); end.writeUInt16LE(2, 10);
  end.writeUInt32LE(directory.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, directory, end]);
}

/** Fresh production schema plus strict local-only egress and real Rust scheduled(). */
export async function fixture(run, { observeR2 = false } = {}) {
  let unexpected = 0;
  const mf = new Miniflare({ cf: false, workers: [{
    name: "amail-recovery-synthetic", modules: true,
    scriptPath: observeR2 ? path.join(root, "infra/tests/worker-boundary/r2-archive-observer.mjs") : path.join(worker, "entry/maintenance.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules,
    compatibilityDate: "2026-08-06",
    bindings: { CF_ZONE_ID: "synthetic-zone", CF_EMAIL_ROUTING_TOKEN: "synthetic-token",
      MAIL_DOMAIN: "mail-staging.moesegfault.dev", EMAIL_INGRESS_WORKER_NAME: "synthetic-ingress" },
    d1Databases: ["MAIL_DB"], r2Buckets: ["MAIL_BODIES"],
    outboundService(request) {
      if (request.method === "GET" && request.url === "https://api.cloudflare.com/client/v4/zones/synthetic-zone/email/routing/rules?per_page=50&page=1") {
        return Response.json({ success: true, result: [], result_info: { total_pages: 1 } });
      }
      unexpected++;
      throw new Error("unexpected synthetic recovery egress");
    },
  }] });
  try {
    const { MAIL_DB: db, MAIL_BODIES: bucket } = await mf.getBindings();
    await applyMigrations(db, path.join(worker, "migrations"));
    await seedResourceAccount(db, issuer, owner);
    await db.prepare("INSERT INTO addresses(address,local_part,owner_iss,owner_sub,slot,state,created_at) VALUES(?1,'recovery-synthetic',?2,?3,0,'active',?4)")
      .bind(sender, issuer, owner, Date.now()).run();
    // Keep this test about persistence, not third-party embedding processing.
    await db.prepare("UPDATE embedding_dependency SET blocked_until=?1 WHERE id=1").bind(Date.now() + 86_400_000).run();
    const tick = async (scheduledTime) => { await (await mf.getWorker()).scheduled(scheduledTime === undefined ? undefined : { scheduledTime: new Date(scheduledTime) }); assert.equal(unexpected, 0); };
    const r2Stats = async () => {
      assert.ok(observeR2, "native R2 stats exist only in the isolated observer fixture");
      return (await mf.dispatchFetch("https://synthetic.invalid/r2-stats")).json();
    };
    await run({ db, bucket, tick, r2Stats });
  } finally { await mf.dispose(); }
}

/**
 * Seed accepted recovery through the production one-use held-canary SQL guard.
 * Each grant is confined to this fixture's fresh synthetic database and revoked
 * after insertion. Re-arming for multi-row workloads is setup, never a live
 * operator action or permission to send; all provider egress remains rejected.
 */
export async function accepted(db, bucket, id, body = text, archive = true) {
  const bytes = draftZip(body), now = Date.now();
  assert.ok(bytes.length < 5 * 1024 * 1024, "fixture satisfies service ZIP cap");
  await db.prepare("UPDATE send_release_gates SET canary_owner_iss=?1,canary_owner_sub=?2,canary_recipient_sha256=?3,canary_expires_at=unixepoch()+600,canary_used_by=NULL,actor='synthetic-fixture',case_ref='synthetic-accepted-recovery',updated_at=unixepoch() WHERE id=1")
    .bind(issuer, owner, createHash("sha256").update("synthetic@example.invalid").digest("hex")).run();
  await db.prepare("INSERT INTO send_requests(owner_iss,owner_sub,idem_key,payload_hash,message_id,provider_id,quota_reserved,state,created_at) VALUES(?1,?2,?3,?4,?3,?5,1,'accepted',?6)")
    .bind(issuer, owner, id, createHash("sha256").update(bytes).digest("hex"), `synthetic-provider-${id}`, now).run();
  const admitted = await db.prepare("SELECT p.state AS policy_state,g.canary_used_by,s.state AS request_state FROM send_policy p JOIN send_release_gates g ON g.id=1 JOIN send_requests s ON s.owner_iss=g.canary_owner_iss AND s.owner_sub=g.canary_owner_sub AND s.idem_key=g.canary_used_by WHERE p.scope='global' AND p.owner_iss='*' AND p.owner_sub='*' AND s.idem_key=?1")
    .bind(id).first();
  assert.deepEqual(admitted, { policy_state: "held", canary_used_by: id, request_state: "accepted" }, "production trigger consumes exactly this synthetic grant while global sending stays held");
  // Expire even the consumed grant before dispatching any scheduled work.
  await db.prepare("UPDATE send_release_gates SET canary_expires_at=unixepoch(),updated_at=unixepoch() WHERE id=1").run();
  await db.prepare("INSERT INTO storage_reservations(id,owner_iss,owner_sub,bytes,state,created_at) VALUES(?1,?2,?3,?4,'reserved',?5)")
    .bind(id, issuer, owner, bytes.length, now).run();
  if (archive) await bucket.put(`messages/${id}.zip`, bytes);
}

/** Read exact indexed body without relying on the implementation's reconstruction helper. */
export async function indexedText(db, id) {
  const message = await db.prepare("SELECT body_text FROM messages WHERE id=?1 AND deleted_at IS NULL").bind(id).first();
  if (!message) return null;
  const chunks = await db.prepare("SELECT chunk_index,body FROM message_text_chunks WHERE message_id=?1 ORDER BY chunk_index").bind(id).all();
  chunks.results.forEach((row, index) => assert.equal(row.chunk_index, index + 1));
  return message.body_text + chunks.results.map(row => row.body).join("");
}
