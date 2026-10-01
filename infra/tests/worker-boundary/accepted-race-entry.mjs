/** Test-only WorkerEntrypoint adapter; import the actual built Rust shim unchanged. */
import BuiltWorker from "./shim.mjs";

const acceptedSql = "UPDATE send_requests SET state='accepted',provider_id=?1,sender=?2,envelope_json=?3,request_id=?4 WHERE owner_iss=?5 AND owner_sub=?6 AND idem_key=?7 AND state='submitting'";

/** Preserve native statement semantics, intercepting only a committed acceptance. */
function statement(native, sql, control, pauseClaim) {
  return new Proxy(native, {
    get(target, key) {
      if (key === "constructor") return target.constructor;
      if (key === "bind") return (...args) => statement(target.bind(...args), sql, control, pauseClaim);
      if (key === "run" && sql.replace(/\s+/g, " ").trim() === acceptedSql) {
        return async () => {
          const result = await target.run();
          if (result.success && result.meta?.changes === 1) {
            const response = await control.fetch("https://test.invalid/after-accepted", { method: "POST" });
            if (!response.ok) throw new Error("synthetic acceptance barrier failed");
          }
          return result;
        };
      }
      if (key === "run" && pauseClaim && sql.replace(/\s+/g, " ").trim().startsWith("UPDATE send_requests SET index_projection_token=?9,index_projection_lease_until=?11")) {
        return async () => {
          const result = await target.run();
          if (result.success && result.meta?.changes === 1) {
            const response = await control.fetch("https://test.invalid/after-claim", { method: "POST" });
            if (!response.ok) throw new Error("synthetic lease barrier failed");
          }
          return result;
        };
      }
      const value = Reflect.get(target, key, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

/** Keep constructor identity and all SQL/storage execution in real local D1. */
function database(native, control, pauseClaim) {
  return new Proxy(native, {
    get(target, key) {
      if (key === "constructor") return target.constructor;
      if (key === "prepare") return sql => statement(target.prepare(sql), sql, control, pauseClaim);
      const value = Reflect.get(target, key, target);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

/** Replace external provider send and one await boundary; no production hooks. */
export default class AcceptedRaceWorker extends BuiltWorker {
  constructor(ctx, env) {
    super(ctx, {
      ...env,
      MAIL_DB: database(env.MAIL_DB, env.TEST_CONTROL, env.RACE_CLAIM_BARRIER === "1"),
      EMAIL: {
        /** The real Rust SendEmailBuilder still crosses the JS binding boundary. */
        async send(builder) {
          if (!builder || typeof builder.subject !== "string") throw new Error("synthetic builder contract");
          const response = await env.TEST_CONTROL.fetch("https://test.invalid/send", { method: "POST" });
          if (!response.ok) throw new Error("synthetic provider failure");
          return response.json();
        },
      },
    });
  }
}
