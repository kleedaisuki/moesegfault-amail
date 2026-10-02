//! ZIP/MIME boundary. / ZIP 与 MIME 信任边界。

use std::collections::HashSet;
use std::io::{Cursor, Read, Write};

use mailparse::{MailHeaderMap, ParsedMail};
use serde::{Deserialize, Serialize};
use zip::{write::SimpleFileOptions, ZipArchive, ZipWriter};

/// Maximum compressed archive accepted by the service. / 服务接受的最大压缩包。
pub const MAX_ZIP: usize = 5 * 1024 * 1024;
const MAX_EXPANDED: usize = 12 * 1024 * 1024;
const MAX_FILES: usize = 40;
const MAX_RELATION_HEADER: usize = 8192;
const MAX_RELATION_IDS: usize = 100;
const MAX_MESSAGE_ID: usize = 512;

/// One referenced attachment or inline asset. / 一个附件或内联资源。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AssetMeta {
    pub path: String,
    pub content_type: String,
    pub disposition: String,
    pub cid: Option<String>,
    pub filename: Option<String>,
}

/// User-authored outbound manifest; never accepts envelope headers. / 用户编写的发送清单，不接受信封头。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SendManifest {
    pub version: u8,
    pub from: String,
    pub to: Vec<String>,
    #[serde(default)]
    pub cc: Vec<String>,
    #[serde(default)]
    pub bcc: Vec<String>,
    pub subject: String,
    pub reply_to: Option<String>,
    pub in_reply_to: Option<String>,
    #[serde(default)]
    pub references: Vec<String>,
    #[serde(default)]
    pub assets: Vec<AssetMeta>,
}

/// Validated outbound parts and their parsed manifest. / 已校验的发送内容和清单。
pub struct Draft {
    pub manifest: SendManifest,
    pub text: String,
    pub html: Option<String>,
    pub assets: Vec<(AssetMeta, Vec<u8>)>,
}

/// Immutable fields in an inbound ZIP manifest; read state stays in D1. / 来信 ZIP 清单只含不可变字段；已读状态保存在 D1。
#[derive(Serialize)]
struct InboundManifest<'a> {
    version: u8,
    id: &'a str,
    direction: &'static str,
    #[serde(rename = "from")]
    sender: &'a str,
    to: &'a [String],
    subject: &'a str,
    received_at: &'a str,
    /// Legacy raw header value; callers must not infer validated RFC identity.
    message_id: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    rfc_message_id: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    reply_to: Option<&'a str>,
    #[serde(skip_serializing_if = "Option::is_none")]
    in_reply_to: Option<&'a str>,
    #[serde(skip_serializing_if = "empty_references")]
    references: &'a [String],
    assets: &'a [AssetMeta],
}

/// Omit an unknown reference chain rather than asserting an empty relationship.
fn empty_references(value: &[String]) -> bool {
    value.is_empty()
}

/// Accept one bounded header only; duplicates are ambiguous, not a reason to
/// reject an otherwise receivable message. Mailparse unfolds header whitespace.
fn relation_header(parsed: &ParsedMail<'_>, name: &str, limit: usize) -> Option<String> {
    let mut values = parsed.headers.get_all_values(name).into_iter();
    let value = values.next()?;
    (values.next().is_none() && value.len() <= limit).then_some(value)
}

/// Preserve a suggested destination only when it is exactly one usable mailbox.
/// A Reply-To value is untrusted data and does not authorize sending to it.
fn inbound_reply_to(parsed: &ParsedMail<'_>) -> Option<String> {
    let value = relation_header(parsed, "Reply-To", 998)?;
    let addresses = mailparse::addrparse(&value).ok()?;
    if addresses.len() != 1 {
        return None;
    }
    match &addresses[0] {
        mailparse::MailAddr::Single(mailbox) if crate::valid_address(&mailbox.addr) => {
            Some(mailbox.addr.clone())
        }
        _ => None,
    }
}

/// Read modern RFC 5322 message IDs, preserving order and brackets. Unsupported
/// obsolete syntax, malformed tokens or excessive chains remain unknown; no
/// provider ID, subject or partial chain is substituted for missing evidence.
fn relation_ids(value: &str) -> Option<Vec<String>> {
    if value.len() > MAX_RELATION_HEADER || !value.is_ascii() {
        return None;
    }
    let mut rest = value;
    let mut ids = Vec::new();
    loop {
        rest = skip_relation_cfws(rest)?;
        if rest.is_empty() {
            return (!ids.is_empty()).then_some(ids);
        }
        let mut literal = false;
        let end = rest.bytes().position(|byte| {
            match byte {
                b'[' => literal = true,
                b']' => literal = false,
                _ => {}
            }
            byte == b'>' && !literal
        })? + 1;
        let id = &rest[..end];
        if ids.len() == MAX_RELATION_IDS || !valid_relation_id(id) {
            return None;
        }
        ids.push(id.to_owned());
        rest = &rest[end..];
    }
}

/// Normalize exactly one syntactically proven RFC 5322 message ID, retaining
/// brackets while removing external comments/whitespace. Opaque provider IDs
/// and ambiguous multi-ID values cannot establish a reply relationship.
pub(crate) fn normalized_rfc_message_id(value: &str) -> Option<String> {
    relation_ids(value)
        .filter(|ids| ids.len() == 1)
        .and_then(|ids| ids.into_iter().next())
}

/// Skip folding whitespace and bounded nested comments outside message IDs.
fn skip_relation_cfws(mut value: &str) -> Option<&str> {
    loop {
        value = value.trim_start_matches([' ', '\t']);
        if !value.starts_with('(') {
            return Some(value);
        }
        let mut depth = 0;
        let mut escaped = false;
        let mut end = None;
        for (index, byte) in value.bytes().enumerate() {
            if byte.is_ascii_control() && byte != b'\t' {
                return None;
            }
            if escaped {
                escaped = false;
                continue;
            }
            match byte {
                b'\\' => escaped = true,
                b'(' => depth += 1,
                b')' => depth -= 1,
                _ => {}
            }
            if depth > 8 {
                return None;
            }
            if depth == 0 {
                end = Some(index + 1);
                break;
            }
        }
        value = &value[end?..];
    }
}

/// RFC 5322 section 3.6.4 modern msg-id: dot-atom left, dot-atom or no-fold
/// domain literal right. The size cap matches the existing outbound contract.
fn valid_relation_id(id: &str) -> bool {
    if id.len() > MAX_MESSAGE_ID {
        return false;
    }
    let Some(inner) = id.strip_prefix('<').and_then(|s| s.strip_suffix('>')) else {
        return false;
    };
    let Some((left, right)) = inner.split_once('@') else {
        return false;
    };
    let literal = right.strip_prefix('[').and_then(|s| s.strip_suffix(']'));
    valid_id_atom(left)
        && literal.map_or_else(
            || valid_id_atom(right),
            |s| s.bytes().all(|b| matches!(b, 33..=90 | 94..=126)),
        )
}

/// A dot atom has nonempty segments and only RFC atext bytes.
fn valid_id_atom(value: &str) -> bool {
    value.split('.').all(|part| {
        !part.is_empty()
            && part
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b"!#$%&'*+-/=?^_`{|}~".contains(&b))
    })
}

/// Parse an untrusted ZIP with path, ratio and shape bounds. / 在路径、压缩比和结构限制下解析不可信 ZIP。
pub fn parse_draft(bytes: &[u8]) -> Result<Draft, String> {
    if bytes.is_empty() || bytes.len() > MAX_ZIP {
        return Err("archive_size".into());
    }
    let mut zip = ZipArchive::new(Cursor::new(bytes)).map_err(|_| "invalid_zip")?;
    if zip.len() == 0 || zip.len() > MAX_FILES {
        return Err("archive_entries".into());
    }
    let mut files = std::collections::HashMap::new();
    let mut seen = HashSet::new();
    let mut total = 0usize;
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i).map_err(|_| "invalid_entry")?;
        let name = entry.name().to_string();
        if !valid_path(&name) || !seen.insert(name.clone()) || entry.is_dir() {
            return Err("invalid_path".into());
        }
        if entry
            .unix_mode()
            .is_some_and(|mode| mode & 0o170000 == 0o120000)
            || !matches!(
                entry.compression(),
                zip::CompressionMethod::Stored | zip::CompressionMethod::Deflated
            )
        {
            return Err("unsupported_entry".into());
        }
        if entry.size() > MAX_EXPANDED.saturating_sub(total) as u64 {
            return Err("archive_expanded_size".into());
        }
        let remaining = MAX_EXPANDED - total;
        let mut content = Vec::new();
        entry
            .take((remaining + 1) as u64)
            .read_to_end(&mut content)
            .map_err(|_| "invalid_entry")?;
        total += content.len();
        if total > MAX_EXPANDED {
            return Err("archive_expanded_size".into());
        }
        files.insert(name, content);
    }
    let manifest_bytes = files.remove("manifest.toml").ok_or("missing_manifest")?;
    let manifest_text = std::str::from_utf8(&manifest_bytes).map_err(|_| "manifest_utf8")?;
    let manifest: SendManifest = toml::from_str(manifest_text).map_err(|_| "manifest_schema")?;
    if manifest.version != 1 || manifest.subject.trim().is_empty() || manifest.subject.len() > 998 {
        return Err("manifest_invalid".into());
    }
    let text = files
        .remove("body.txt")
        .map(|b| String::from_utf8(b).map_err(|_| "body_utf8"))
        .transpose()?;
    let html = files
        .remove("body.html")
        .map(|b| String::from_utf8(b).map_err(|_| "body_utf8"))
        .transpose()?;
    if text.is_none() && html.is_none() {
        return Err("missing_body".into());
    }
    let mut assets = Vec::new();
    let mut cids = HashSet::new();
    for asset in &manifest.assets {
        if !asset.path.starts_with("assets/")
            || !valid_path(&asset.path)
            || asset.content_type.contains(['\r', '\n'])
            || !matches!(asset.disposition.as_str(), "inline" | "attachment")
            || (asset.disposition == "inline" && asset.cid.is_none())
        {
            return Err("asset_manifest".into());
        }
        if let Some(cid) = &asset.cid {
            if cid.is_empty()
                || !cid
                    .chars()
                    .all(|c| c.is_ascii_alphanumeric() || "._-".contains(c))
                || !cids.insert(cid.clone())
            {
                return Err("asset_cid".into());
            }
        }
        let content = files.remove(&asset.path).ok_or("missing_asset")?;
        assets.push((asset.clone(), content));
    }
    if !files.is_empty() {
        return Err("unlisted_entry".into());
    }
    let safe_html = html.map(|raw| sanitize_html(&raw)).transpose()?;
    let text = text.unwrap_or_else(|| {
        html2text::from_read(safe_html.as_deref().unwrap_or_default().as_bytes(), 80)
            .unwrap_or_default()
    });
    Ok(Draft {
        manifest,
        text,
        html: safe_html,
        assets,
    })
}

/// Inline local CSS and retain safe CID images without fetching linked resources. / 内联本地 CSS 并保留安全 CID 图片，不获取外部资源。
fn sanitize_html(raw: &str) -> Result<String, String> {
    let inlined = css_inline::CSSInliner::options()
        .load_remote_stylesheets(false)
        .build()
        .inline(raw)
        .map_err(|_| "html_compile")?;
    let allowed_styles = [
        "color",
        "background-color",
        "font-family",
        "font-size",
        "font-style",
        "font-weight",
        "text-align",
        "text-decoration",
        "line-height",
        "width",
        "height",
        "padding",
        "margin",
        "border",
        "border-color",
        "border-style",
        "border-width",
        "display",
        "vertical-align",
    ]
    .into_iter()
    .collect();
    Ok(ammonia::Builder::default()
        .add_url_schemes(&["cid"])
        .add_tags(&["img", "table", "thead", "tbody", "tr", "td", "th"])
        .add_tag_attributes("img", &["src", "alt", "width", "height"])
        .add_generic_attributes(&["style"])
        .filter_style_properties(allowed_styles)
        .clean(&inlined)
        .to_string())
}

fn valid_path(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && !path.contains('\\')
        && !path.contains('\0')
        && path
            .split('/')
            .all(|p| !p.is_empty() && p != "." && p != "..")
        && !path.contains(':')
}

/// Build a portable agent-facing archive from a parsed inbound message. / 从解析后的来信构造可移植归档。
pub fn inbound_archive(
    raw: &[u8],
    id: &str,
    received_at: &str,
) -> Result<
    (
        Vec<u8>,
        String,
        String,
        Vec<String>,
        String,
        bool,
        bool,
        serde_json::Value,
    ),
    String,
> {
    let parsed = mailparse::parse_mail(raw).map_err(|_| "invalid_mime")?;
    let sender = parsed.headers.get_first_value("From").unwrap_or_default();
    let to_header = parsed.headers.get_first_value("To").unwrap_or_default();
    let recipients = mailparse::addrparse(&to_header)
        .ok()
        .map(|addrs| {
            addrs
                .iter()
                .flat_map(|address| match address {
                    mailparse::MailAddr::Single(mailbox) => vec![mailbox.addr.clone()],
                    mailparse::MailAddr::Group(group) => group
                        .addrs
                        .iter()
                        .map(|mailbox| mailbox.addr.clone())
                        .collect(),
                })
                .collect()
        })
        .unwrap_or_else(|| vec![to_header]);
    let subject = parsed
        .headers
        .get_first_value("Subject")
        .unwrap_or_default();
    let message_id = parsed
        .headers
        .get_first_value("Message-ID")
        .unwrap_or_default();
    let reply_to = inbound_reply_to(&parsed);
    let rfc_message_id = relation_header(&parsed, "Message-ID", MAX_RELATION_HEADER)
        .and_then(|value| normalized_rfc_message_id(&value));
    let in_reply_to = relation_header(&parsed, "In-Reply-To", MAX_RELATION_HEADER)
        .and_then(|value| normalized_rfc_message_id(&value));
    let references = relation_header(&parsed, "References", MAX_RELATION_HEADER)
        .and_then(|value| relation_ids(&value))
        .unwrap_or_default();
    let mut text = None;
    let mut html = None;
    let mut assets = Vec::new();
    collect_parts(&parsed, &mut text, &mut html, &mut assets)?;
    if text.is_none() && html.is_none() {
        text = Some(String::new());
    }
    let has_html = html.is_some();
    let has_text = text.is_some();
    let body_text = text.clone().unwrap_or_else(|| {
        html2text::from_read(html.as_deref().unwrap_or_default().as_bytes(), 80).unwrap_or_default()
    });
    let asset_meta = assets.iter().map(|(m, _)| m.clone()).collect::<Vec<_>>();
    let manifest = InboundManifest {
        version: 1,
        id,
        direction: "inbound",
        sender: &sender,
        to: &recipients,
        subject: &subject,
        received_at,
        message_id: &message_id,
        rfc_message_id: rfc_message_id.as_deref(),
        reply_to: reply_to.as_deref(),
        in_reply_to: in_reply_to.as_deref(),
        references: &references,
        assets: &asset_meta,
    };
    let manifest_toml = toml::to_string(&manifest).map_err(|_| "manifest_encode")?;
    let mut out = Cursor::new(Vec::new());
    {
        let mut writer = ZipWriter::new(&mut out);
        let opts =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        writer
            .start_file("manifest.toml", opts)
            .map_err(|_| "zip_write")?;
        writer
            .write_all(manifest_toml.as_bytes())
            .map_err(|_| "zip_write")?;
        if let Some(value) = text {
            writer
                .start_file("body.txt", opts)
                .map_err(|_| "zip_write")?;
            writer
                .write_all(value.as_bytes())
                .map_err(|_| "zip_write")?;
        }
        if let Some(value) = html {
            writer
                .start_file("body.html", opts)
                .map_err(|_| "zip_write")?;
            writer
                .write_all(value.as_bytes())
                .map_err(|_| "zip_write")?;
        }
        for (meta, data) in &assets {
            writer
                .start_file(&meta.path, opts)
                .map_err(|_| "zip_write")?;
            writer.write_all(data).map_err(|_| "zip_write")?;
        }
        writer.finish().map_err(|_| "zip_write")?;
    }
    let mut metadata = serde_json::json!({
        "message_id":message_id,
        "content_type":parsed.ctype.mimetype,
        "attachment_name":asset_meta.iter().filter_map(|m|m.filename.as_deref()).collect::<Vec<_>>().join(" "),
        "attachments":asset_meta,
    });
    if let Some(value) = rfc_message_id {
        metadata["rfc_message_id"] = value.into();
    }
    if let Some(value) = reply_to {
        metadata["reply_to"] = value.into();
    }
    if let Some(value) = in_reply_to {
        metadata["in_reply_to"] = value.into();
    }
    if !references.is_empty() {
        metadata["references"] = serde_json::json!(references);
    }
    Ok((
        out.into_inner(),
        sender,
        subject,
        recipients,
        body_text,
        has_html,
        has_text,
        metadata,
    ))
}

fn collect_parts(
    part: &ParsedMail<'_>,
    text: &mut Option<String>,
    html: &mut Option<String>,
    assets: &mut Vec<(AssetMeta, Vec<u8>)>,
) -> Result<(), String> {
    if !part.subparts.is_empty() {
        for child in &part.subparts {
            collect_parts(child, text, html, assets)?;
        }
        return Ok(());
    }
    let mime = part.ctype.mimetype.to_ascii_lowercase();
    let disp = part.get_content_disposition();
    let attachment =
        disp.disposition == mailparse::DispositionType::Attachment || !mime.starts_with("text/");
    if !attachment && mime == "text/plain" && text.is_none() {
        *text = Some(part.get_body().map_err(|_| "mime_body")?);
    } else if !attachment && mime == "text/html" && html.is_none() {
        *html = Some(sanitize_html(&part.get_body().map_err(|_| "mime_body")?)?);
    } else {
        if assets.len() >= 32 {
            return Err("too_many_attachments".into());
        }
        let filename = disp
            .params
            .get("filename")
            .cloned()
            .unwrap_or_else(|| format!("part-{}", assets.len() + 1));
        let safe = filename
            .chars()
            .map(|c| {
                if c.is_ascii_alphanumeric() || "._-".contains(c) {
                    c
                } else {
                    '_'
                }
            })
            .collect::<String>();
        let path = format!("assets/{}-{}", assets.len() + 1, safe);
        let cid = part
            .headers
            .get_first_value("Content-ID")
            .map(|s| s.trim_matches(['<', '>']).to_string());
        let meta = AssetMeta {
            path,
            content_type: mime,
            disposition: if cid.is_some() {
                "inline"
            } else {
                "attachment"
            }
            .into(),
            cid,
            filename: Some(filename),
        };
        assets.push((meta, part.get_body_raw().map_err(|_| "mime_body")?));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Receipt fixtures exercise both indexed metadata and the immutable ZIP.
    fn receipt(headers: &str) -> (serde_json::Value, toml::Value) {
        let raw = format!("From: sender@example.org\r\nTo: receiver@example.org\r\nSubject: report\r\nMessage-ID: <receipt@example.org>\r\n{headers}\r\nbody");
        let result = inbound_archive(raw.as_bytes(), "opaque-id", "2026-10-03T00:00:00Z").unwrap();
        let mut zip = ZipArchive::new(Cursor::new(result.0)).unwrap();
        let mut manifest = String::new();
        zip.by_name("manifest.toml")
            .unwrap()
            .read_to_string(&mut manifest)
            .unwrap();
        (result.7, toml::from_str(&manifest).unwrap())
    }

    /// A distinct suggested mailbox and folded relation chain survive receipt;
    /// immutable archives still contain no mutable read state or provider ID.
    #[test]
    fn preserves_inbound_reply_context() {
        let (metadata, manifest) = receipt("Reply-To: Replies <reply@example.org>\r\nIn-Reply-To: (parent) <report@example.org>\r\nReferences: <root@example.org>\r\n\t<report@example.org>\r\n");
        assert_eq!(metadata["reply_to"], "reply@example.org");
        assert_eq!(metadata["in_reply_to"], "<report@example.org>");
        assert_eq!(
            metadata["references"],
            serde_json::json!(["<root@example.org>", "<report@example.org>"])
        );
        assert_eq!(manifest["reply_to"].as_str(), Some("reply@example.org"));
        assert_eq!(
            manifest["in_reply_to"].as_str(),
            Some("<report@example.org>")
        );
        assert_eq!(manifest["references"].as_array().unwrap().len(), 2);
        assert_eq!(
            manifest["message_id"].as_str(),
            Some("<receipt@example.org>")
        );
        assert!(manifest.get("read").is_none());
        assert_eq!(metadata["rfc_message_id"], "<receipt@example.org>");
        assert_eq!(
            manifest["rfc_message_id"].as_str(),
            Some("<receipt@example.org>")
        );
    }

    /// Proven RFC identity is additive: legacy raw identity remains available,
    /// while absent, malformed and duplicate headers cannot fabricate identity.
    #[test]
    fn preserves_only_proven_rfc_message_identity() {
        for (header, legacy) in [
            ("", ""),
            ("Message-ID: opaque-provider-id\r\n", "opaque-provider-id"),
            (
                "Message-ID: <a@example.org> <b@example.org>\r\n",
                "<a@example.org> <b@example.org>",
            ),
            (
                "Message-ID: <a@example.org>\r\nMessage-ID: <b@example.org>\r\n",
                "<a@example.org>",
            ),
        ] {
            let raw = format!(
                "From: a@example.org\r\nTo: b@example.org\r\nSubject: test\r\n{header}\r\nbody"
            );
            let result =
                inbound_archive(raw.as_bytes(), "opaque-id", "2026-10-03T00:00:00Z").unwrap();
            assert!(result.7.get("rfc_message_id").is_none(), "{header}");
            assert_eq!(result.7["message_id"], legacy);
            let mut zip = ZipArchive::new(Cursor::new(result.0)).unwrap();
            let mut manifest = String::new();
            zip.by_name("manifest.toml")
                .unwrap()
                .read_to_string(&mut manifest)
                .unwrap();
            let manifest: toml::Value = toml::from_str(&manifest).unwrap();
            assert!(manifest.get("rfc_message_id").is_none());
            assert_eq!(manifest["message_id"].as_str(), Some(legacy));
        }
        assert_eq!(
            normalized_rfc_message_id(" (source) <a@example.org> (tail) "),
            Some("<a@example.org>".into())
        );
        assert!(normalized_rfc_message_id("opaque-provider-id").is_none());
    }

    /// Malformed, missing and ambiguous relationships remain absent; delivery
    /// is accepted and no same-subject or provider identity fallback is invented.
    #[test]
    fn omits_unknown_inbound_reply_context() {
        for headers in [
            "",
            "Reply-To: a@example.org, b@example.org\r\nIn-Reply-To: provider-id\r\nReferences: <ok@example.org> invalid\r\n",
            "Reply-To: Team: a@example.org;\r\nIn-Reply-To: <a@example.org> <b@example.org>\r\nReferences: <bad..id@example.org>\r\n",
            "Reply-To: a@example.org\r\nReply-To: b@example.org\r\nIn-Reply-To: <a@example.org>\r\nIn-Reply-To: <b@example.org>\r\nReferences: <a@example.org>\r\nReferences: <b@example.org>\r\n",
        ] {
            let (metadata, manifest) = receipt(headers);
            for key in ["reply_to", "in_reply_to", "references"] {
                assert!(metadata.get(key).is_none(), "{key}: {headers}");
                assert!(manifest.get(key).is_none(), "{key}: {headers}");
            }
        }
    }

    /// Strict modern IDs and bounded comments/chains prevent malformed relation
    /// data from becoming partial, apparently trustworthy threading evidence.
    #[test]
    fn bounds_relation_headers() {
        for id in ["<a.b@example.org>", "<a@[127.0.0.1]>", "<a@[IPv6:::1]>"] {
            assert!(valid_relation_id(id), "{id}");
        }
        for id in [
            "<@example.org>",
            "<a@>",
            "<a@@example.org>",
            "<a..b@example.org>",
            "<a@bad..org>",
            "<a b@example.org>",
            "<a@example.org>extra",
            "<a@[bad\\literal]>",
        ] {
            assert!(!valid_relation_id(id), "{id}");
        }
        assert!(relation_ids(&"<a@example.org> ".repeat(MAX_RELATION_IDS)).is_some());
        assert!(relation_ids(&"<a@example.org> ".repeat(MAX_RELATION_IDS + 1)).is_none());
        assert!(relation_ids(&format!("<{}@example.org>", "a".repeat(MAX_MESSAGE_ID))).is_none());
        assert!(relation_ids(&" ".repeat(MAX_RELATION_HEADER + 1)).is_none());
        assert!(relation_ids("(unclosed <a@example.org>").is_none());
        assert_eq!(
            relation_ids("<a@[literal>text]>"),
            Some(vec!["<a@[literal>text]>".into()])
        );
        assert!(relation_ids("(((((((((too deep))))))))) <a@example.org>").is_none());
        assert_eq!(
            relation_ids("(parent (nested)) <a@example.org>(tail)"),
            Some(vec!["<a@example.org>".into()])
        );
        let (metadata, _) = receipt(&format!(
            "References: {}\r\n",
            "<a@example.org> ".repeat(MAX_RELATION_IDS + 1)
        ));
        assert!(metadata.get("references").is_none());
    }

    /// ZIP traversal must never reach an agent-selected extraction directory. / ZIP 路径穿越不得越出代理所选目录。
    #[test]
    fn rejects_bad_paths() {
        for path in ["../a", "/a", "a\\b", "a//b", "a/./b", "a/../b", "C:a"] {
            assert!(!valid_path(path), "{path}");
        }
    }

    /// HTML email compilation keeps safe CSS and CID content, but strips executable handlers. / HTML 邮件编译保留安全 CSS 与 CID 资源并移除可执行事件。
    #[test]
    fn html_preserves_cid_and_safe_css() {
        let safe = sanitize_html("<style>.x{color:red}</style><p class=x>Hi<img src=\"cid:chart\" onerror=\"alert(1)\"></p>").unwrap();
        assert!(safe.contains("cid:chart"), "{safe}");
        assert!(safe.contains("color:"), "{safe}");
        assert!(!safe.contains("onerror"), "{safe}");
    }

    /// A highly compressed oversized body is rejected after decompression accounting. / 高压缩率超大正文在解压计量后被拒绝。
    #[test]
    fn rejects_zip_bomb() {
        let mut output = Cursor::new(Vec::new());
        {
            let mut writer = ZipWriter::new(&mut output);
            let opts =
                SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
            writer.start_file("manifest.toml", opts).unwrap();
            writer.write_all(b"version=1\nfrom='a@mail.moesegfault.dev'\nto=['b@example.org']\nsubject='test'\n").unwrap();
            writer.start_file("body.txt", opts).unwrap();
            writer.write_all(&vec![b'a'; 13 * 1024 * 1024]).unwrap();
            writer.finish().unwrap();
        }
        assert!(parse_draft(&output.into_inner()).is_err());
    }
}
