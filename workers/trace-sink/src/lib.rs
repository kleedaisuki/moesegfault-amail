//! Private Queue-only application trace sink. No fetch, scheduled or mail entrypoint.
//! Never log Queue envelopes, deserialization errors, request context or unchecked values.

use amail_trace_schema::Event;
use worker::{event, Env, MessageBatch, MessageExt, Result};

/// Validate each message independently; malformed payloads are dropped, not replayed into DLQ.
/// Valid events preserve producer IDs even if at-least-once delivery logs them twice.
#[event(queue)]
pub async fn queue(
    batch: MessageBatch<serde_json::Value>,
    _env: Env,
    _ctx: worker::Context,
) -> Result<()> {
    for raw in batch.raw_iter() {
        let body = match serde_wasm_bindgen::from_value::<serde_json::Value>(raw.body()) {
            Ok(body) => body,
            Err(_) => {
                // Decoding failed before a typed message exists. Avoid error/body serialization.
                // Acknowledgement uses the raw message; do not retry malformed untrusted data.
                raw.ack();
                continue;
            }
        };
        let Some(event) = Event::from_value(body) else {
            raw.ack();
            continue;
        };
        match serde_json::to_string(&event) {
            Ok(encoded) => {
                worker::console_log!("{}", encoded);
                raw.ack();
            }
            Err(_) => raw.retry(),
        }
    }
    Ok(())
}
