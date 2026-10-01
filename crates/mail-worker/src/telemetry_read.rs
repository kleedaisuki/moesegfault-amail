//! Bounded native request-body admission for the new attempts telemetry route only.

use wasm_bindgen::{JsCast, JsValue};

use crate::{platform, AppError, AppResult};

/// Generous headroom for 100 fixed-schema events; the CLI uploads at most 20.
/// Actual stream bytes are authoritative, never Content-Length or event count.
const MAX_BYTES: usize = 256 * 1024;

/// Inspect chunk length before copying into Wasm, then release native reader ownership.
/// Legacy telemetry keeps its established parser. No body, field or exception text
/// escapes this boundary, including unknown JSON keys and rejected chunk contents.
pub(crate) async fn read(req: &worker::Request) -> AppResult<Vec<u8>> {
    let stream = req.inner().body().ok_or_else(invalid)?;
    let stream = JsValue::from(stream);
    let reader = method(&stream, "getReader")?
        .call0(&stream)
        .map_err(|_| invalid())?;
    let result = chunks(&reader).await;
    platform::finish_native_reader(&reader, result.is_err());
    result
}

/// Stop on the first over-limit native chunk without copying it or reading a successor.
async fn chunks(reader: &JsValue) -> AppResult<Vec<u8>> {
    let read = method(reader, "read")?;
    let mut bytes = Vec::new();
    loop {
        let pending = read.call0(reader).map_err(|_| invalid())?;
        let result = wasm_bindgen_futures::JsFuture::from(js_sys::Promise::resolve(&pending))
            .await
            .map_err(|_| invalid())?;
        match js_sys::Reflect::get(&result, &JsValue::from_str("done"))
            .map_err(|_| invalid())?
            .as_bool()
        {
            Some(true) => return Ok(bytes),
            Some(false) => {}
            None => return Err(invalid()),
        }
        let chunk = js_sys::Reflect::get(&result, &JsValue::from_str("value"))
            .and_then(|value| value.dyn_into::<js_sys::Uint8Array>())
            .map_err(|_| invalid())?;
        if chunk.length() as usize > MAX_BYTES.saturating_sub(bytes.len()) {
            return Err(AppError::bad("invalid_telemetry"));
        }
        bytes.extend(chunk.to_vec());
    }
}

/// Reflection failures use a fixed code rather than rendering attacker-controlled text.
fn method(target: &JsValue, name: &str) -> AppResult<js_sys::Function> {
    js_sys::Reflect::get(target, &JsValue::from_str(name))
        .and_then(|value| value.dyn_into::<js_sys::Function>())
        .map_err(|_| invalid())
}

/// Preserve the route's established malformed-body error without private details.
fn invalid() -> AppError {
    AppError::bad("invalid_json")
}
