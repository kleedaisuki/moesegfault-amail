/** Production Rust/Wasm embedding boundary; all egress is synthetic and denied by default. */
import { apiVersionHeaders } from "./api-version.mjs";
import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Log, LogLevel, Miniflare } from "miniflare";
import { applyMigrations } from "./migration-fixture.mjs";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const worker = path.join(root, "crates/mail-worker");
const issuer = "https://identity-staging.moesegfault.dev";
const endpoint = "https://openrouter.ai/api/v1/embeddings";
const querySentinel = "SYNTHETIC_PRIVATE_QUERY_8dacf2";
const bodySentinel = "SYNTHETIC_PRIVATE_PROVIDER_BODY_0613";
const keySentinel = "SYNTHETIC_PRIVATE_KEY_bf6a";
const model = "qwen/qwen3-embedding-8b";
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

/** The real OIDC verifier checks an ephemeral locally signed token. */
function token() {
  const header = Buffer.from(JSON.stringify({ alg: "RS256", kid: "synthetic" })).toString("base64url");
  const payload = Buffer.from(JSON.stringify({ iss: issuer, sub: "synthetic", aud: "amail-cli-staging",
    token_use: "access", exp: Math.floor(Date.now() / 1000) + 300 })).toString("base64url");
  const input = `${header}.${payload}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

/** Capture runtime diagnostics without printing private synthetic sentinels. */
class PrivateLog extends Log {
  constructor(records) { super(LogLevel.DEBUG); this.records = records; }
  logWithLevel(_level, message) { this.records.push(String(message)); }
}

/** Dispatch the production semantic API with a real local D1 and fake provider. */
async function exercise(providerResponse) {
  const calls = [];
  const logs = [];
  let foreign = 0;
  const jwk = publicKey.export({ format: "jwk" });
  const mf = new Miniflare({ cf: false, log: new PrivateLog(logs), workers: [{
    name: "embedding-synthetic", modules: true, scriptPath: path.join(worker, "entry/api.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules,
    compatibilityDate: "2026-08-06", d1Databases: ["MAIL_DB"],
    bindings: { IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: "amail-cli-staging",
      OPENROUTER_API_KEY: keySentinel, OPENROUTER_EMBEDDING_MODEL: model,
      MAIL_DOMAIN: "mail-staging.moesegfault.dev" },
    async outboundService(request) {
      calls.push({ method: request.method, url: request.url });
      if (request.url === `${issuer}/.well-known/openid-configuration`) {
        return Response.json({ issuer, jwks_uri: `${issuer}/jwks` });
      }
      if (request.url === `${issuer}/jwks`) {
        return Response.json({ keys: [{ ...jwk, kid: "synthetic", alg: "RS256", use: "sig" }] });
      }
      if (request.url !== endpoint) { foreign++; throw new Error("synthetic forbidden egress"); }
      assert.equal(request.method, "POST");
      assert.equal(request.headers.get("authorization"), `Bearer ${keySentinel}`);
      const input = await request.json();
      assert.equal(input.input, querySentinel);
      assert.equal(input.dimensions, 256);
      assert.equal(input.model, model);
      assert.equal(input.input_type, "search_query");
      return providerResponse();
    },
  }] });
  try {
    const { MAIL_DB: db } = await mf.getBindings();
    await applyMigrations(db, path.join(worker, "migrations"));
    const response = await mf.dispatchFetch("https://mail-staging.moesegfault.dev/v1/messages/search", {
      method: "POST", headers: { ...apiVersionHeaders, authorization: `Bearer ${token()}`, "content-type": "application/json" },
      body: JSON.stringify({ semantic: querySentinel }),
    });
    const text = await response.text();
    const diagnostic = `${text}\n${JSON.stringify([...response.headers])}\n${logs.join("\n")}`;
    for (const sentinel of [querySentinel, bodySentinel, keySentinel]) {
      assert.equal(diagnostic.includes(sentinel), false, "private sentinel entered diagnostic output");
    }
    assert.equal(foreign, 0, "redirects or unexpected egress must never leave the approved endpoint");
    assert.equal(calls.filter((call) => call.url === endpoint).length, 1);
    return { status: response.status, body: JSON.parse(text) };
  } finally { await mf.dispose(); }
}

/** Preserve the public error code for every provider body failure. */
function unavailable(result) {
  assert.equal(result.status, 503);
  assert.equal(result.body.code, "semantic_unavailable");
}

for (const status of [301, 302, 303, 307, 308]) {
  test(`embedding refuses ${status} foreign redirect without following credentials or query`, async () => {
    unavailable(await exercise(() => new Response(bodySentinel, {
      status, headers: { location: "https://foreign.invalid/stolen" },
    })));
  });
}

test("valid 256D Qwen JSON at exactly 64 KiB is accepted", async () => {
  const envelope = { data: [{ embedding: Array(256).fill(2) }], padding: "" };
  const base = JSON.stringify(envelope);
  envelope.padding = "x".repeat(64 * 1024 - Buffer.byteLength(base));
  const body = JSON.stringify(envelope);
  assert.equal(Buffer.byteLength(body), 64 * 1024);
  const result = await exercise(() => new Response(body));
  assert.equal(result.status, 200);
});

/** The public API rejects an over-limit provider body without private diagnostics. */
test("oversized embedding without Content-Length remains unavailable", async () => {
  unavailable(await exercise(() => new Response("x".repeat(65_537))));
});

for (const body of [bodySentinel, '{"data":[{"embedding":[1,2', JSON.stringify({ data: [{ embedding: [1] }] })]) {
  test("malformed, truncated, or wrong-dimension embedding remains private and unavailable", async () => {
    unavailable(await exercise(() => new Response(body)));
  });
}
