//! Shared TLS trust policy for Identity and Mail, including enterprise CA bundles.

use anyhow::{Context, Result};
use reqwest::{blocking::ClientBuilder, Certificate};

pub(crate) fn client_builder() -> Result<ClientBuilder> {
    let mut builder = ClientBuilder::new();
    if let Some(path) = std::env::var_os("SSL_CERT_FILE") {
        let pem = std::fs::read(path).context("reading SSL_CERT_FILE CA bundle")?;
        let certificates =
            Certificate::from_pem_bundle(&pem).context("parsing SSL_CERT_FILE CA bundle")?;
        for certificate in certificates {
            builder = builder.add_root_certificate(certificate);
        }
    }
    Ok(builder)
}
