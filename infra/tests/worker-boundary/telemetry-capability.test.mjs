/**
 * Hosted compiled Rust API boundaries; only synthetic OIDC and diagnostic Queue traffic.
 * No mail database, account store or real provider exists in this fixture. A native
 * Queue consumer observes Rust-produced records, not a JavaScript reimplementation.
 * Delivery uses an arrival barrier: maxBatchTimeout is runtime configuration, not
 * an assertion sleep. This proves source behavior, not deployed sink retention or
 * native Cloudflare tracing/privacy. The unknown-path case is current dispatch
 * evidence, not an execution of a historical rollback binary.
 * Queue fixture mechanism: https://developers.cloudflare.com/workers/testing/miniflare/core/queues/
 */
import { apiVersionHeaders } from "./api-version.mjs";
import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { Miniflare } from "miniflare";
import { workerModuleRules } from "./worker-module-rules.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const issuer = "https://identity-staging.moesegfault.dev";
const origin = "https://mail-staging.moesegfault.dev";
const client = "amail-cli-staging";
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const traceId = "0123456789abcdef0123456789abcdef";
const spanId = "abcdef0123456789";

/** Keep production signature, issuer, audience and token-kind verification in the path. */
function token(audience = client) {
  const encode = value => Buffer.from(JSON.stringify(value)).toString("base64url");
  const input = `${encode({ alg: "RS256", typ: "JWT", kid: "synthetic-capability" })}.${encode({
    iss: issuer, sub: "synthetic-capability-subject", aud: audience,
    exp: Math.floor(Date.now() / 1000) + 300, token_use: "access",
  })}`;
  return `${input}.${sign("RSA-SHA256", Buffer.from(input), privateKey).toString("base64url")}`;
}

/** CLI wire operations use dots; retained Queue enums use underscores. No fabricated clocks. */
function legacy() {
  return { operation: "messages.list", status: 200, duration_ms: 8,
    bytes_bucket: 64, trace_id: traceId, span_id: spanId };
}

/** Source time and body failure intentionally disagree with the superficially successful status. */
function attempt() {
  return { ...legacy(), started_at_ms: 1_790_000_000_123, elapsed_ms: 121_007,
    phase: "response_body", error_kind: "decode" };
}

/** Missing native delivery fails the test instead of silently accepting an empty capture. */
async function bounded(promise) {
  let timer;
  try {
    return await Promise.race([promise, new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error("synthetic telemetry Queue delivery missing")), 10_000);
    })]);
  } finally { clearTimeout(timer); }
}

/** Fresh runtime, no business stores, one-use Identity mocks and a real native Queue producer. */
async function fixture(run, { queueBinding = true } = {}) {
  const records = [], waiters = [];
  let unexpected = 0;
  const jwk = publicKey.export({ format: "jwk" });
  const exchanges = [
    { url: `${issuer}/.well-known/openid-configuration`, body: { issuer, jwks_uri: `${issuer}/jwks` }, used: false },
    { url: `${issuer}/jwks`, body: { keys: [{ ...jwk, kid: "synthetic-capability", alg: "RS256", use: "sig" }] }, used: false },
  ];
  const outboundService = request => {
    const exchange = exchanges.find(item => !item.used && request.method === "GET" && request.url === item.url);
    if (!exchange) {
      unexpected++;
      throw new Error("unexpected synthetic capability egress");
    }
    exchange.used = true;
    return Response.json(exchange.body);
  };
  const api = {
    name: "api", modules: true,
    scriptPath: path.join(root, "crates/mail-worker/entry/api.mjs"),
    modulesRoot: root, modulesRules: workerModuleRules, compatibilityDate: "2026-08-06",
    bindings: { IDENTITY_ISSUER: issuer, OIDC_CLIENT_ID: client }, outboundService,
    ...(queueBinding ? { queueProducers: { TRACE_EVENTS: "synthetic-capability-trace" } } : {}),
  };
  const workers = [api];
  if (queueBinding) workers.push({
    name: "capture", modules: true, compatibilityDate: "2026-08-06",
    // This observer does not reconstruct records: assertions inspect the actual Rust-produced body.
    script: `export default {
      async queue(batch, env) {
        await env.CAPTURE.fetch("https://synthetic.invalid/telemetry", {
          method: "POST", body: JSON.stringify(batch.messages.map(message => message.body)),
        });
        batch.ackAll();
      }
    };`,
    queueConsumers: { "synthetic-capability-trace": { maxBatchSize: 1, maxBatchTimeout: 1, maxRetries: 0 } },
    serviceBindings: { CAPTURE: async request => {
      assert.equal(request.method, "POST");
      assert.equal(request.url, "https://synthetic.invalid/telemetry");
      records.push(...await request.json());
      for (const waiter of waiters) waiter();
      return new Response(null, { status: 204 });
    } },
    outboundService() { throw new Error("synthetic Queue capture cannot contact providers"); },
  });
  const mf = new Miniflare({ cf: false, workers });
  try {
    const request = async (pathname, { auth = token(), body, method = "POST", version = "2" } = {}) =>
      mf.dispatchFetch(`${origin}${pathname}`, { method,
        headers: { ...(version === null ? {} : { ...apiVersionHeaders, "x-amail-api-version": version }), ...(auth === null ? {} : { Authorization: `Bearer ${auth}` }), "Content-Type": "application/json" },
        ...(body === undefined ? {} : {
          body: typeof body === "string" || body instanceof ReadableStream ? body : JSON.stringify(body),
          ...(body instanceof ReadableStream ? { duplex: "half" } : {}),
        }),
      });
    const clientRecords = () => records.filter(row => row.service === "mail_cli");
    const delivered = async count => {
      await bounded(new Promise(resolve => {
        const check = () => { if (clientRecords().length >= count) resolve(); };
        waiters.push(check);
        check();
      }));
      return clientRecords();
    };
    await run({ request, delivered, records, exchanges });
    assert.equal(unexpected, 0, "no real Identity, mail provider or foreign egress");
  } finally { await mf.dispose(); }
}

/** Headers are schema support, not Queue retention or principal authorization. */
function capable(response) {
  assert.equal(response.headers.get("x-amail-telemetry"), "attempts-v1");
}

/** Unsupported clients stop before authentication, body parsing or business work. */
test("missing and old API versions require upgrade before any dependency call", async () => {
  await fixture(async ({ request, exchanges }) => {
    for (const version of [null, "1", "0.1.2", "3", "2.0"]) {
      const response = await request("/v1/billing/sessions", {
        version, body: "SYNTHETIC_INVALID_JSON",
      });
      assert.equal(response.status, 426, `unsupported protocol ${version}`);
      assert.equal((await response.json()).code, "required_client_version");
    }
    assert.ok(exchanges.every(item => !item.used), "upgrade rejection never calls Identity or Billing");
  });
});

/** Health remains usable by deployment monitors that are not native clients. */
test("health remains public without the incompatible client protocol header", async () => {
  await fixture(async ({ request, exchanges }) => {
    const response = await request("/health", { method: "GET", auth: null, version: null });
    assert.equal(response.status, 200);
    assert.equal((await response.json()).status, "ok");
    assert.ok(exchanges.every(item => !item.used));
  });
});

test("authenticated legacy telemetry keeps its ACK and announces exact capability", async () => {
  await fixture(async ({ request, delivered }) => {
    const response = await request("/v1/telemetry", { body: { events: [legacy()] } });
    assert.equal(response.status, 202);
    capable(response);
    const ack = await response.json();
    assert.equal(ack.accepted, 1);
    assert.match(ack.request_id, /^[0-9a-f-]{36}$/);
    const [record] = await delivered(1);
    assert.equal(record.trace_id, traceId);
    assert.equal(record.span_id, spanId);
    assert.equal(record.outcome, "success");
    for (const key of ["occurred_at_ms", "duration_ms", "http_status", "client_phase", "client_error_kind"]) {
      assert.equal(record[key], undefined, "legacy client clocks and phase remain unknown");
    }
  });
});

test("versioned route reconstructs exact source body failure despite HTTP200", async () => {
  await fixture(async ({ request, delivered }) => {
    const response = await request("/v1/telemetry/attempts", { body: { events: [attempt(), legacy()] } });
    assert.equal(response.status, 202);
    capable(response);
    assert.equal((await response.json()).accepted, 2);
    const records = await delivered(2);
    const failed = records.find(row => row.client_phase === "response_body");
    assert.ok(failed, "positive control proves enriched reader and Queue send ran");
    assert.equal(failed.occurred_at_ms, attempt().started_at_ms);
    assert.equal(failed.duration_ms, attempt().elapsed_ms);
    assert.equal(failed.http_status, 200);
    assert.equal(failed.http_status_class, 2);
    assert.equal(failed.outcome, "phase_failure");
    assert.equal(failed.client_error_kind, "decode");
    assert.equal(failed.error_code, "dependency_failure");
    assert.equal(failed.trace_id, traceId);
    assert.equal(failed.span_id, spanId);
    assert.equal(records.find(row => !row.client_phase).occurred_at_ms, undefined);
  });
});

test("public health never announces capability even when binding and bearer exist", async () => {
  await fixture(async ({ request, exchanges }) => {
    for (const auth of [null, token()]) {
      const response = await request("/health", { method: "GET", auth });
      assert.equal(response.status, 200);
      assert.equal(response.headers.get("x-amail-telemetry"), null);
      assert.equal((await response.json()).status, "ok");
    }
    assert.ok(exchanges.every(item => !item.used), "public route does not authenticate");
  });
});

test("both telemetry routes authenticate before poisoned JSON and do not announce", async () => {
  await fixture(async ({ request, exchanges }) => {
    for (const pathname of ["/v1/telemetry", "/v1/telemetry/attempts"]) {
      const response = await request(pathname, { auth: null, body: "SYNTHETIC_INVALID_JSON" });
      assert.equal(response.status, 401);
      assert.equal(response.headers.get("x-amail-telemetry"), null);
      assert.equal((await response.json()).code, "unauthorized");
    }
    assert.ok(exchanges.every(item => !item.used));
  });
});

test("a signed wrong-audience token cannot turn capability into authority", async () => {
  await fixture(async ({ request, exchanges }) => {
    const response = await request("/v1/telemetry/attempts", {
      auth: token("synthetic-wrong-client"), body: { events: [attempt()] },
    });
    assert.equal(response.status, 401);
    assert.equal(response.headers.get("x-amail-telemetry"), null);
    assert.equal((await response.json()).code, "unauthorized");
    assert.ok(exchanges.every(item => item.used), "real signature verifier consulted synthetic keys");
  });
});

test("missing Queue binding disables announcement and rejects attempts before parsing", async () => {
  await fixture(async ({ request }) => {
    for (const body of ["SYNTHETIC_INVALID_JSON", { events: [attempt()] }]) {
      const response = await request("/v1/telemetry/attempts", { body });
      assert.equal(response.status, 503);
      assert.equal(response.headers.get("x-amail-telemetry"), null);
      assert.equal((await response.json()).code, "service_unavailable");
    }
    const legacyResponse = await request("/v1/telemetry", { body: { events: [legacy()] } });
    assert.equal(legacyResponse.status, 202, "existing legacy acknowledgement semantics stay unchanged");
    assert.equal(legacyResponse.headers.get("x-amail-telemetry"), null);
    assert.equal((await legacyResponse.json()).accepted, 1);
  }, { queueBinding: false });
});

test("versioned reader rejects unknown fields and impossible source phase metadata", async () => {
  await fixture(async ({ request }) => {
    for (const [label, event] of [
      ["unknown phase", { ...attempt(), phase: "SYNTHETIC_PRIVATE_PHASE" }],
      ["unknown event field", { ...attempt(), private_body: "SYNTHETIC_PRIVATE_CONTENT" }],
      ["contradictory cause", { ...attempt(), error_kind: "credential_unavailable" }],
      ["missing elapsed", { ...attempt(), elapsed_ms: null }],
    ]) {
      const response = await request("/v1/telemetry/attempts", { body: { events: [event] } });
      assert.equal(response.status, 400, label);
      capable(response);
      assert.ok(["invalid_json", "invalid_telemetry"].includes((await response.json()).code));
    }
    const response = await request("/v1/telemetry/attempts", {
      body: { events: [attempt()], private_body: "SYNTHETIC_PRIVATE_CONTENT" },
    });
    assert.equal(response.status, 400, "unknown batch field");
    capable(response);
    assert.equal((await response.json()).code, "invalid_json");

    // Exercise actual streamed bytes without Content-Length, not just a JSON event-count cap.
    const encoder = new TextEncoder();
    const oversized = new ReadableStream({ start(controller) {
      controller.enqueue(encoder.encode('{"events":[],"private_body":"'));
      controller.enqueue(encoder.encode("S".repeat(256 * 1024)));
      controller.enqueue(encoder.encode('"}'));
      controller.close();
    } });
    const tooLarge = await request("/v1/telemetry/attempts", { body: oversized });
    assert.equal(tooLarge.status, 400, "actual chunked body limit");
    capable(tooLarge);
    assert.equal((await tooLarge.json()).code, "invalid_telemetry");

    const atLimit = JSON.stringify({ events: [attempt()] }).padEnd(256 * 1024, " ");
    const accepted = await request("/v1/telemetry/attempts", { body: atLimit });
    assert.equal(accepted.status, 202, "exact byte-limit positive control");
    assert.equal((await accepted.json()).accepted, 1);

    const legacyExtension = await request("/v1/telemetry", {
      body: { events: [{ ...legacy(), private_body: "SYNTHETIC_PRIVATE_CONTENT" }] },
    });
    assert.equal(legacyExtension.status, 202, "legacy platform parser remains unchanged");
    assert.equal((await legacyExtension.json()).accepted, 1);
  });
});

test("ordinary authenticated not-found response announces without requiring business stores", async () => {
  await fixture(async ({ request }) => {
    const response = await request("/v1/synthetic-unknown", { method: "GET" });
    assert.equal(response.status, 404);
    capable(response);
    assert.equal((await response.json()).code, "not_found");
  });
});

test("unknown future upload path returns authenticated404 without invoking telemetry parser", async () => {
  await fixture(async ({ request }) => {
    const response = await request("/v1/telemetry/synthetic-future", { body: "SYNTHETIC_INVALID_JSON" });
    assert.equal(response.status, 404);
    capable(response);
    assert.equal((await response.json()).code, "not_found");
  });
});
