//! Bounded ZIP exchange format / 有边界的 ZIP 交换格式。

use anyhow::{bail, ensure, Context, Result};
use serde::Deserialize;
use std::{
    collections::HashSet,
    fs::File,
    io::{Cursor, Read, Write},
    path::{Path, PathBuf},
};
use zip::{write::SimpleFileOptions, ZipArchive, ZipWriter};

const MAX_OUTBOUND_ARCHIVE: usize = 5 * 1024 * 1024;
const MAX_INBOUND_ARCHIVE: usize = 25 * 1024 * 1024;
const MAX_OUTBOUND_UNCOMPRESSED: u64 = 12 * 1024 * 1024;
const MAX_INBOUND_UNCOMPRESSED: u64 = 50 * 1024 * 1024;

fn contains_any(value: &str, chars: &[char]) -> bool {
    value.chars().any(|c| chars.contains(&c))
}

/// Declared inline or attached asset / 声明的内联资源或附件。
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Asset {
    path: String,
    content_type: String,
    disposition: String,
    cid: Option<String>,
    filename: Option<String>,
}

/// Outbound manifest; read-only inbound fields are rejected by serde.
/// 发件清单；入站只读字段由 serde 拒绝。
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    version: u32,
    from: String,
    to: Vec<String>,
    #[serde(default)]
    cc: Vec<String>,
    #[serde(default)]
    bcc: Vec<String>,
    subject: String,
    reply_to: Option<String>,
    in_reply_to: Option<String>,
    references: Option<Vec<String>>,
    #[serde(default)]
    assets: Vec<Asset>,
}

/// Verify a safe relative ZIP name; never trust path normalization to strip traversal.
/// 校验安全的 ZIP 相对路径；绝不依赖路径归一化消除穿越。
fn safe_name(name: &str) -> Result<()> {
    ensure!(
        !name.is_empty()
            && !name.starts_with('/')
            && !name.contains('\\')
            && !name.contains(':')
            && !name.contains('\0'),
        "unsafe ZIP entry name"
    );
    ensure!(
        name.split('/')
            .all(|p| !p.is_empty() && p != "." && p != ".."),
        "unsafe ZIP path component"
    );
    Ok(())
}

fn validate_manifest(manifest: &Manifest, names: &HashSet<String>) -> Result<()> {
    ensure!(manifest.version == 1, "unsupported archive version");
    ensure!(
        manifest.from.contains('@') && !contains_any(&manifest.from, &['\r', '\n']),
        "invalid sender"
    );
    ensure!(
        !manifest.to.is_empty() && manifest.to.len() + manifest.cc.len() + manifest.bcc.len() <= 50,
        "recipient count out of range"
    );
    for recipient in manifest.to.iter().chain(&manifest.cc).chain(&manifest.bcc) {
        ensure!(
            recipient.contains('@') && !contains_any(recipient, &['\r', '\n']),
            "invalid recipient"
        );
    }
    ensure!(
        !contains_any(&manifest.subject, &['\r', '\n']) && manifest.subject.len() <= 998,
        "invalid subject"
    );
    if let Some(reply_to) = &manifest.reply_to {
        ensure!(!contains_any(reply_to, &['\r', '\n']), "invalid reply_to");
    }
    if let Some(message_id) = &manifest.in_reply_to {
        ensure!(
            !contains_any(message_id, &['\r', '\n']),
            "invalid in_reply_to"
        );
    }
    if let Some(references) = &manifest.references {
        ensure!(
            references.len() <= 20 && references.iter().all(|v| !contains_any(v, &['\r', '\n'])),
            "invalid references"
        );
    }
    ensure!(
        names.contains("body.txt") || names.contains("body.html"),
        "archive needs body.txt or body.html"
    );
    ensure!(manifest.assets.len() <= 32, "too many assets");
    let mut declared = HashSet::new();
    let mut cids = HashSet::new();
    for asset in &manifest.assets {
        safe_name(&asset.path)?;
        ensure!(
            asset.path.starts_with("assets/") && names.contains(&asset.path),
            "missing or misplaced asset"
        );
        ensure!(
            declared.insert(asset.path.as_str()),
            "duplicate asset declaration"
        );
        ensure!(
            !contains_any(&asset.content_type, &['\r', '\n']) && asset.content_type.contains('/'),
            "invalid asset content type"
        );
        ensure!(
            matches!(asset.disposition.as_str(), "inline" | "attachment"),
            "invalid asset disposition"
        );
        if asset.disposition == "inline" {
            let cid = asset.cid.as_deref().context("inline asset requires cid")?;
            ensure!(
                !cid.is_empty() && !contains_any(cid, &['\r', '\n', '<', '>']) && cids.insert(cid),
                "invalid or duplicate cid"
            );
        }
        if let Some(filename) = &asset.filename {
            ensure!(
                !contains_any(filename, &['\r', '\n', '/', '\\']),
                "invalid asset filename"
            );
        }
    }
    for name in names {
        ensure!(
            matches!(name.as_str(), "manifest.toml" | "body.txt" | "body.html")
                || declared.contains(name.as_str()),
            "undeclared archive entry: {name}"
        );
    }
    Ok(())
}

/// Validate outbound ZIP and return bytes suitable for an idempotent send.
/// 校验出站 ZIP，返回可用于幂等发送的字节。
pub fn outbound_bytes(path: &Path) -> Result<Vec<u8>> {
    let bytes = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
    ensure!(
        bytes.len() <= MAX_OUTBOUND_ARCHIVE,
        "archive exceeds 5 MiB transport limit"
    );
    let mut zip = ZipArchive::new(Cursor::new(&bytes))?;
    ensure!(zip.len() <= 36, "too many archive entries");
    let mut names = HashSet::new();
    let mut total = 0u64;
    for i in 0..zip.len() {
        let mut entry = zip.by_index(i)?;
        let name = entry.name().to_owned();
        safe_name(&name)?;
        ensure!(!entry.is_dir(), "directory entries are not needed");
        ensure!(names.insert(name), "duplicate ZIP entry");
        ensure!(
            matches!(
                entry.compression(),
                zip::CompressionMethod::Stored | zip::CompressionMethod::Deflated
            ),
            "unsupported ZIP compression"
        );
        if let Some(mode) = entry.unix_mode() {
            ensure!(mode & 0o170000 != 0o120000, "ZIP symlink rejected");
        }
        total = total.saturating_add(entry.size());
        ensure!(
            total <= MAX_OUTBOUND_UNCOMPRESSED,
            "archive expands beyond limit"
        );
        let mut sink = std::io::sink();
        let copied = std::io::copy(&mut entry, &mut sink)?;
        ensure!(copied == entry.size(), "ZIP entry size mismatch");
    }
    let mut manifest_text = String::new();
    zip.by_name("manifest.toml")?
        .read_to_string(&mut manifest_text)?;
    ensure!(manifest_text.len() <= 64 * 1024, "manifest too large");
    let manifest: Manifest = toml::from_str(&manifest_text)?;
    validate_manifest(&manifest, &names)?;
    for name in ["body.txt", "body.html"] {
        if names.contains(name) {
            let mut text = String::new();
            zip.by_name(name)?
                .read_to_string(&mut text)
                .with_context(|| format!("{name} must be UTF-8"))?;
            ensure!(text.len() <= 2 * 1024 * 1024, "{name} too large");
        }
    }
    Ok(bytes)
}

fn gather(dir: &Path, rel: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
    for item in std::fs::read_dir(dir.join(rel))? {
        let item = item?;
        let name = item.file_name();
        let relative = rel.join(name);
        let meta = item.symlink_metadata()?;
        ensure!(!meta.file_type().is_symlink(), "symlink in draft directory");
        if meta.is_dir() {
            gather(dir, &relative, files)?;
        } else if meta.is_file() {
            files.push(relative);
        } else {
            bail!("unsupported draft file type");
        }
    }
    Ok(())
}

/// Package a draft directory using Rust ZIP, adding text fallback for HTML-only drafts.
/// 使用 Rust 原生 ZIP 打包草稿；仅有 HTML 时补充文本正文。
///
/// Example / 示例: a directory containing `manifest.toml` and `body.html` can be
/// packaged by `amail pack draft/ -o draft.zip`, then sent by `amail send draft.zip`.
/// 示例：目录中包含 `manifest.toml` 与 `body.html` 后执行上述命令即可打包发送。
pub fn pack(dir: &Path, output: &Path) -> Result<()> {
    ensure!(dir.is_dir(), "draft must be a directory");
    ensure!(!output.exists(), "output archive already exists");
    let mut files = Vec::new();
    gather(dir, Path::new(""), &mut files)?;
    files.sort();
    ensure!(files.len() <= 36, "too many draft files");
    let generated_text = !dir.join("body.txt").exists() && dir.join("body.html").exists();
    let temp = output.with_extension(format!("amail-{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| -> Result<()> {
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            file.set_permissions(std::fs::Permissions::from_mode(0o600))?;
        }
        let mut zip = ZipWriter::new(file);
        let options =
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated);
        for rel in files {
            let name = rel
                .to_str()
                .context("draft path must be UTF-8")?
                .replace('\\', "/");
            safe_name(&name)?;
            let mut input = File::open(dir.join(&rel))?;
            zip.start_file(name, options)?;
            std::io::copy(&mut input, &mut zip)?;
        }
        if generated_text {
            let html = std::fs::read(dir.join("body.html"))?;
            let text = html2text::from_read(html.as_slice(), 80)?;
            zip.start_file("body.txt", options)?;
            zip.write_all(text.as_bytes())?;
        }
        zip.finish()?.sync_all()?;
        outbound_bytes(&temp)?;
        ensure!(!output.exists(), "output archive already exists");
        std::fs::rename(&temp, output)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(&temp);
    }
    result
}

/// Safely extract an inbound archive into a new directory, never following links.
/// 安全地将入站归档解包到新目录，绝不跟随链接。
pub fn unpack(bytes: &[u8], destination: &Path) -> Result<()> {
    ensure!(
        bytes.len() <= MAX_INBOUND_ARCHIVE,
        "inbound archive exceeds 25 MiB limit"
    );
    ensure!(!destination.exists(), "destination already exists");
    let mut zip = ZipArchive::new(Cursor::new(bytes))?;
    ensure!(zip.len() <= 36, "too many entries");
    let mut names = HashSet::new();
    let mut total = 0u64;
    for i in 0..zip.len() {
        let entry = zip.by_index(i)?;
        safe_name(entry.name())?;
        ensure!(
            !entry.is_dir() && names.insert(entry.name().to_owned()),
            "directory or duplicate entry"
        );
        if let Some(mode) = entry.unix_mode() {
            ensure!(mode & 0o170000 != 0o120000, "symlink rejected");
        }
        total = total.saturating_add(entry.size());
        ensure!(
            total <= MAX_INBOUND_UNCOMPRESSED,
            "archive expansion exceeds limit"
        );
    }
    ensure!(
        names.contains("manifest.toml")
            && (names.contains("body.html") || names.contains("body.txt")),
        "incomplete message archive"
    );
    let temp = destination.with_extension(format!("amail-{}.tmp", uuid::Uuid::new_v4()));
    std::fs::create_dir(&temp)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&temp, std::fs::Permissions::from_mode(0o700))?;
    }
    let result = (|| -> Result<()> {
        for i in 0..zip.len() {
            let mut entry = zip.by_index(i)?;
            let path = temp.join(entry.name());
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)?;
            }
            let mut out = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(path)?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                out.set_permissions(std::fs::Permissions::from_mode(0o600))?;
            }
            std::io::copy(&mut entry, &mut out)?;
            out.sync_all()?;
        }
        ensure!(!destination.exists(), "destination already exists");
        std::fs::rename(&temp, destination)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = std::fs::remove_dir_all(&temp);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_traversal() {
        for bad in ["../secret", "/root", "a//b", "a\\b", "C:/temp", "a/./b"] {
            assert!(safe_name(bad).is_err());
        }
    }

    #[test]
    fn package_html_draft_with_text_fallback() {
        let root = tempfile::tempdir().unwrap();
        let draft = root.path().join("draft");
        std::fs::create_dir(&draft).unwrap();
        std::fs::write(draft.join("manifest.toml"), "version = 1\nfrom = 'a@mail.moesegfault.dev'\nto = ['b@example.org']\nsubject = 'Hello'\n").unwrap();
        std::fs::write(draft.join("body.html"), "<p>Hello <b>world</b></p>").unwrap();
        let output = root.path().join("message.zip");
        pack(&draft, &output).unwrap();
        let bytes = outbound_bytes(&output).unwrap();
        let mut zip = ZipArchive::new(Cursor::new(bytes)).unwrap();
        assert!(zip.by_name("body.txt").is_ok());
    }

    #[test]
    fn inbound_metadata_cannot_be_resent_unchanged() {
        let root = tempfile::tempdir().unwrap();
        let draft = root.path().join("draft");
        std::fs::create_dir(&draft).unwrap();
        std::fs::write(draft.join("manifest.toml"),
            "version = 1\nfrom = 'a@mail.moesegfault.dev'\nto = ['b@example.org']\nsubject = 'Echo'\nid = 'inbound-id'\n").unwrap();
        std::fs::write(draft.join("body.txt"), "hello").unwrap();
        let output = root.path().join("message.zip");
        assert!(pack(&draft, &output).is_err());
        assert!(!output.exists());
    }
}
