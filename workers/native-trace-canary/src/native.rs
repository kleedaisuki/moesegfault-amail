//! Minimal Rust bindings to the platform tracing namespace; no mail logic in JS.

use js_sys::{Function, Object, Reflect};
use wasm_bindgen::{prelude::wasm_bindgen, JsCast, JsValue};

#[wasm_bindgen(module = "cloudflare:workers")]
extern "C" {
    /// Resolve only inside the request; never capture active context at module scope.
    #[wasm_bindgen(js_namespace = tracing, js_name = getActiveSpan, catch)]
    fn get_active_span() -> Result<JsValue, JsValue>;
    /// Manual child spans inherit active context but do not themselves become active.
    #[wasm_bindgen(js_namespace = tracing, js_name = startSpan, catch)]
    fn start_span(name: &str) -> Result<JsValue, JsValue>;
}

/// Native interface failure is a source-owned stage, never raw JS exception text.
#[derive(Clone, Copy, Debug)]
pub enum Stage {
    /// Namespace getter failed (including an older runtime without the new API).
    Root,
    /// No request-active root exists.
    Context,
    /// Attributes could not be applied to the root.
    Attributes,
    /// Custom child creation failed.
    Child,
    /// Fixed exception recording failed.
    Exception,
    /// Explicit child completion failed.
    End,
}

impl Stage {
    /// Preserve actionable boundary rather than collapsing every failure to unavailable.
    pub fn label(self) -> &'static str {
        match self {
            Self::Root => "get_active_span",
            Self::Context => "request_context",
            Self::Attributes => "set_attributes",
            Self::Child => "start_span",
            Self::Exception => "record_exception",
            Self::End => "end_span",
        }
    }
}

/// Invocation-owned native handle; it stores no request/response/user payload.
pub struct Span(JsValue);

impl Span {
    /// A missing getter/root is not silently interpreted as successful tracing.
    pub fn active() -> Result<Self, Stage> {
        let value = get_active_span().map_err(|_| Stage::Root)?;
        if value.is_null() || value.is_undefined() {
            return Err(Stage::Context);
        }
        Ok(Self(value))
    }

    /// Create one source-named manual child under the current platform root.
    pub fn child() -> Result<Self, Stage> {
        start_span("amail.canary.operation")
            .map(Self)
            .map_err(|_| Stage::Child)
    }

    /// Observe actual sampling, not just namespace availability.
    pub fn sampled(&self) -> bool {
        Reflect::get(&self.0, &JsValue::from_str("isTraced"))
            .ok()
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
    }

    /// Apply only source-owned string/bool attributes, never request-derived text.
    pub fn attributes(&self, fields: &[(&str, JsValue)]) -> Result<(), Stage> {
        let values = Object::new();
        for (key, value) in fields {
            Reflect::set(&values, &JsValue::from_str(key), value).map_err(|_| Stage::Attributes)?;
        }
        self.call("setAttributes", Some(values.as_ref()))
            .map_err(|_| Stage::Attributes)
    }

    /// The fixed error object exercises native recording without error prose/stack leakage.
    pub fn fixed_exception(&self) -> Result<(), Stage> {
        let value = Object::new();
        for (key, text) in [
            ("code", "SYNTHETIC_FAILURE"),
            ("name", "CanaryFailure"),
            ("message", "Fixed infrastructure canary failure"),
        ] {
            Reflect::set(&value, &JsValue::from_str(key), &JsValue::from_str(text))
                .map_err(|_| Stage::Exception)?;
        }
        self.call("recordException", Some(value.as_ref()))
            .map_err(|_| Stage::Exception)
    }

    /// Explicitly complete manual children; invocation roots remain runtime-owned.
    pub fn end(&self) -> Result<(), Stage> {
        self.call("end", None).map_err(|_| Stage::End)
    }

    /// Reflective structural binding needs no guessed exported JS Span constructor.
    fn call(&self, name: &str, argument: Option<&JsValue>) -> Result<(), JsValue> {
        let method: Function = Reflect::get(&self.0, &JsValue::from_str(name))?.dyn_into()?;
        match argument {
            Some(argument) => method.call1(&self.0, argument),
            None => method.call0(&self.0),
        }
        .map(|_| ())
    }
}
