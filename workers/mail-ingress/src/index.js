/**
 * Minimal Email-event transport adapter; all mail policy lives in the Rust Worker.
 * 最小化 Email 事件传输适配器；所有邮件策略均位于 Rust Worker。
 */
export default {
  /**
   * Forward bounded MIME bytes over a private service binding, without logging envelope data.
   * 通过私有服务绑定转发有界 MIME 字节，不记录信封数据。
   *
   * @param {ForwardableEmailMessage} message Incoming Cloudflare email event. / Cloudflare 来信事件。
   * @param {{MAIL_API: Fetcher, INGRESS_SECRET: string, MAIL_API_ORIGIN: string}} env Private bindings. / 私有绑定。
   */
  async email(message, env) {
    if (message.rawSize > 25 * 1024 * 1024) {
      message.setReject("Message exceeds the amail 25 MiB limit");
      return;
    }
    const bytes = await new Response(message.raw).arrayBuffer();
    const traceId = [...crypto.getRandomValues(new Uint8Array(16))].map((b) => b.toString(16).padStart(2, "0")).join("");
    const spanId = [...crypto.getRandomValues(new Uint8Array(8))].map((b) => b.toString(16).padStart(2, "0")).join("");
    const response = await env.MAIL_API.fetch(`${env.MAIL_API_ORIGIN}/internal/inbound`, {
      method: "POST",
      headers: {
        "content-type": "message/rfc822",
        "x-amail-ingress-secret": env.INGRESS_SECRET,
        "x-amail-envelope-to": message.to,
        traceparent: `00-${traceId}-${spanId}-01`,
      },
      body: bytes,
    });
    if (response.status >= 400 && response.status < 500) {
      message.setReject("Recipient unavailable or message invalid");
      return;
    }
    if (!response.ok) {
      throw new Error(`amail ingestion failed (${response.status})`);
    }
  },
};
