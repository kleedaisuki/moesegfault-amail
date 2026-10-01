//! Bounded accepted-archive reads through the native R2 stream reader.
//! Native chunk length is inspected before copying into Wasm memory.

use wasm_bindgen::{JsCast, JsValue};
use worker::{Error, Object, ResponseBody, Result};

use crate::archive::MAX_ZIP;
use crate::{maintenance, platform};

/// Invalid retained content is durable deferral; transport failures are separate.
enum Failure {
    /// No accepted service archive exceeds the existing compressed ZIP limit.
    Invalid,
    /// Native stream contract or an awaited read failed without exposing details.
    Dependency,
}

/// Read only an admitted retained object. No HEAD/second GET/retry is introduced.
/// `None` preserves accepted state for missing/oversized/inconsistent content.
/// The caller captures a thirty-second absolute cutoff before GET, clipped to
/// the original sixty-second setup/item allowance and invocation cutoff. Native
/// stream cancellation never implies cancellation of GET or an R2/D1 write.
pub(crate) async fn read(
    object: &Object,
    deadline: maintenance::ExternalDeadline<'_>,
) -> Result<Option<Vec<u8>>> {
    let Some(body) = object.body() else {
        return Ok(None);
    };
    let stream = match body.response_body().map_err(|_| failed())? {
        ResponseBody::Stream(stream) => JsValue::from(stream),
        _ => return Ok(None),
    };
    let duration = match deadline.remaining() {
        Ok(duration) => duration,
        Err(error) => {
            // The binding GET is not cancelable. Release its late returned body
            // without a first read, copy, parse, or renewed deadline.
            platform::finish_native_reader(&stream, true);
            return Err(error);
        }
    };
    if object.size() > MAX_ZIP as u64 {
        // A rejected GET body must not occupy an open stream/connection slot.
        // Cancel without requesting a chunk or allocating an archive buffer.
        platform::finish_native_reader(&stream, true);
        return Ok(None);
    }
    let reader = method(&stream, "getReader")
        .and_then(|method| method.call0(&stream).map_err(|_| Failure::Dependency))
        .map_err(|_| failed())?;
    // One absolute timer covers the entire body, never one fresh timeout per
    // chunk. Keep reader ownership outside the raced future, including on stall.
    let result = {
        let body = Box::pin(read_chunks(&reader));
        let timer = Box::pin(worker::Delay::from(duration));
        match futures_util::future::select(body, timer).await {
            futures_util::future::Either::Left((result, timer)) => {
                drop(timer);
                result
            }
            futures_util::future::Either::Right((_, body)) => {
                drop(body);
                platform::finish_native_reader(&reader, true);
                return Err(maintenance::deferred());
            }
        }
    };
    // Initiate cancellation before releasing the lock; an untrusted cancel
    // promise must not hold Cron after its absolute deadline.
    platform::finish_native_reader(&reader, result.is_err());
    match result {
        Ok(bytes) if bytes.len() as u64 == object.size() => Ok(Some(bytes)),
        Ok(_) | Err(Failure::Invalid) => Ok(None),
        Err(Failure::Dependency) => Err(failed()),
    }
}

/// Reflection failures never stringify JS errors or retain archive keys.
fn method(target: &JsValue, name: &str) -> std::result::Result<js_sys::Function, Failure> {
    js_sys::Reflect::get(target, &JsValue::from_str(name))
        .and_then(|value| value.dyn_into::<js_sys::Function>())
        .map_err(|_| Failure::Dependency)
}

/// Stop before copying the first over-limit native chunk; never request another.
async fn read_chunks(reader: &JsValue) -> std::result::Result<Vec<u8>, Failure> {
    let read = method(reader, "read")?;
    let mut bytes = Vec::new();
    loop {
        let pending = read.call0(reader).map_err(|_| Failure::Dependency)?;
        let result = wasm_bindgen_futures::JsFuture::from(js_sys::Promise::resolve(&pending))
            .await
            .map_err(|_| Failure::Dependency)?;
        let done = js_sys::Reflect::get(&result, &JsValue::from_str("done"))
            .map_err(|_| Failure::Dependency)?;
        match done.as_bool() {
            Some(true) => return Ok(bytes),
            Some(false) => {}
            None => return Err(Failure::Dependency),
        }
        let chunk = js_sys::Reflect::get(&result, &JsValue::from_str("value"))
            .and_then(|value| value.dyn_into::<js_sys::Uint8Array>())
            .map_err(|_| Failure::Dependency)?;
        if !fits(bytes.len(), chunk.length() as usize) {
            return Err(Failure::Invalid);
        }
        bytes.extend(chunk.to_vec());
    }
}

/// Checked remaining-space arithmetic also rejects hostile large-length values.
fn fits(buffered: usize, incoming: usize) -> bool {
    buffered <= MAX_ZIP && incoming <= MAX_ZIP - buffered
}

/// The sole returned transport code has no native error/body/resource context.
fn failed() -> Error {
    Error::RustError("accepted_archive_read_failed".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Exact-cap archives remain valid; oversized chunks/totals cannot wrap.
    #[test]
    fn chunk_admission_preserves_zip_limit_without_overflow() {
        assert!(fits(0, MAX_ZIP));
        assert!(fits(MAX_ZIP, 0));
        assert!(fits(MAX_ZIP - 8, 8));
        assert!(!fits(0, MAX_ZIP + 1));
        assert!(!fits(MAX_ZIP - 8, 9));
        assert!(!fits(MAX_ZIP + 1, 0));
        assert!(!fits(0, usize::MAX));
    }
}
