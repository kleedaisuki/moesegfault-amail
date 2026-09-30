//! Strict Identity access-token validation. / 严格校验 Identity 访问令牌。

use std::cell::RefCell;

use jsonwebtoken::{decode, decode_header, Algorithm, DecodingKey, Validation};
use serde::Deserialize;
use worker::{Env, Fetch, Request, Result, Url};

const PROD_ISSUER: &str = "https://identity.moesegfault.dev";
const STAGE_ISSUER: &str = "https://identity-staging.moesegfault.dev";
const CACHE_MS: f64 = 300_000.0;

thread_local! {
    static JWKS: RefCell<Option<(f64, Vec<Jwk>)>> = const { RefCell::new(None) };
}

/// Immutable identity key; email and display name are never authorization keys. / 不可变身份键；邮件地址和昵称绝不用作授权键。
#[derive(Clone)]
pub struct Principal {
    pub iss: String,
    pub sub: String,
}

#[derive(Clone, Deserialize)]
struct Jwk {
    kid: String,
    kty: String,
    n: String,
    e: String,
    alg: Option<String>,
    #[serde(rename = "use")]
    usage: Option<String>,
    key_ops: Option<Vec<String>>,
}

#[derive(Deserialize)]
struct Jwks {
    keys: Vec<Jwk>,
}

#[derive(Deserialize)]
struct Discovery {
    issuer: String,
    jwks_uri: String,
}

#[derive(Deserialize)]
struct Claims {
    iss: String,
    sub: String,
    #[allow(dead_code)]
    aud: serde_json::Value,
    #[allow(dead_code)]
    exp: usize,
    token_use: String,
}

/// Validate signature, issuer, native-client audience, token kind and expiry. / 校验签名、签发者、原生客户端受众、令牌类型与期限。
pub async fn authenticate(req: &Request, env: &Env) -> Result<Principal> {
    let bearer = req.headers().get("Authorization")?.unwrap_or_default();
    let token = bearer.strip_prefix("Bearer ").ok_or_else(unauthorized)?;
    if token.len() > 8192 {
        return Err(unauthorized());
    }
    let header = decode_header(token).map_err(|_| unauthorized())?;
    if header.alg != Algorithm::RS256 {
        return Err(unauthorized());
    }
    let kid = header.kid.ok_or_else(unauthorized)?;
    let client_id = env.var("OIDC_CLIENT_ID")?.to_string();
    let issuer = env.var("IDENTITY_ISSUER")?.to_string();
    if issuer != PROD_ISSUER && issuer != STAGE_ISSUER {
        return Err(unauthorized());
    }
    if client_id.is_empty() || client_id == "UNCONFIGURED" {
        return Err(unauthorized());
    }
    let mut keys = jwks(&issuer, false).await?;
    let mut key = keys.iter().find(|key| key.kid == kid && compatible(key));
    if key.is_none() {
        keys = jwks(&issuer, true).await?;
        key = keys.iter().find(|key| key.kid == kid && compatible(key));
    }
    let key = key.ok_or_else(unauthorized)?;
    let decoding = DecodingKey::from_rsa_components(&key.n, &key.e).map_err(|_| unauthorized())?;
    let mut validation = Validation::new(Algorithm::RS256);
    validation.set_issuer(&[&issuer]);
    validation.set_audience(&[client_id]);
    validation.leeway = 30;
    validation.validate_nbf = true;
    validation.required_spec_claims.insert("sub".into());
    let claims = decode::<Claims>(token, &decoding, &validation)
        .map_err(|_| unauthorized())?
        .claims;
    if claims.iss != issuer || claims.sub.is_empty() || claims.token_use != "access" {
        return Err(unauthorized());
    }
    Ok(Principal {
        iss: claims.iss,
        sub: claims.sub,
    })
}

fn compatible(key: &Jwk) -> bool {
    key.kty == "RSA"
        && key.alg.as_deref().is_none_or(|s| s == "RS256")
        && key.usage.as_deref().is_none_or(|s| s == "sig")
        && key
            .key_ops
            .as_ref()
            .is_none_or(|ops| ops.iter().any(|op| op == "verify"))
}

async fn jwks(issuer: &str, force: bool) -> Result<Vec<Jwk>> {
    let now = js_sys::Date::now();
    if !force {
        if let Some(keys) = JWKS.with(|cell| {
            cell.borrow()
                .as_ref()
                .filter(|(until, _)| *until > now)
                .map(|(_, keys)| keys.clone())
        }) {
            return Ok(keys);
        }
    }
    let url = Url::parse(&format!("{issuer}/.well-known/openid-configuration"))?;
    let mut response = Fetch::Url(url).send().await?;
    if response.status_code() != 200 {
        return Err(unauthorized());
    }
    let discovery: Discovery = response.json().await.map_err(|_| unauthorized())?;
    if discovery.issuer != issuer {
        return Err(unauthorized());
    }
    let jwks_url = Url::parse(&discovery.jwks_uri).map_err(|_| unauthorized())?;
    let issuer_url = Url::parse(issuer).map_err(|_| unauthorized())?;
    if jwks_url.scheme() != "https" || jwks_url.host_str() != issuer_url.host_str() {
        return Err(unauthorized());
    }
    let mut response = Fetch::Url(jwks_url).send().await?;
    if response.status_code() != 200 {
        return Err(unauthorized());
    }
    let set: Jwks = response.json().await.map_err(|_| unauthorized())?;
    if set.keys.len() > 32 {
        return Err(unauthorized());
    }
    JWKS.with(|cell| *cell.borrow_mut() = Some((now + CACHE_MS, set.keys.clone())));
    Ok(set.keys)
}

fn unauthorized() -> worker::Error {
    worker::Error::RustError("unauthorized".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Reject signing keys intended for encryption or another algorithm. / 拒绝加密用途或其他算法的密钥。
    #[test]
    fn rejects_wrong_key_metadata() {
        let mut key = Jwk {
            kid: "k".into(),
            kty: "RSA".into(),
            n: "n".into(),
            e: "e".into(),
            alg: Some("RS256".into()),
            usage: Some("sig".into()),
            key_ops: None,
        };
        assert!(compatible(&key));
        key.usage = Some("enc".into());
        assert!(!compatible(&key));
    }
}
