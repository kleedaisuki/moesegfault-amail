//! Export an active mailbox lifetime without retaining another local mail store.

use crate::api::{Api, SearchReply};
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use std::{
    collections::HashSet,
    fs::OpenOptions,
    io::Write,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};
use zip::{write::SimpleFileOptions, ZipWriter};

fn active_snapshot(addresses: &Value, address: &str) -> Result<Value> {
    let row = addresses
        .get("addresses")
        .and_then(Value::as_array)
        .and_then(|rows| {
            rows.iter()
                .find(|row| row.get("address").and_then(Value::as_str) == Some(address))
        })
        .context("mailbox is not active or has already expired")?;
    ensure!(
        row.get("state").and_then(Value::as_str) == Some("active"),
        "mailbox is not active or has already expired"
    );
    if row.get("kind").and_then(Value::as_str) == Some("tmpaddr") {
        ensure!(
            row.get("generation")
                .and_then(Value::as_str)
                .is_some_and(|generation| !generation.is_empty()),
            "temporary mailbox generation is unavailable"
        );
    }
    Ok(json!({
        "address":address,
        "kind":row.get("kind").cloned().unwrap_or(json!("mail")),
        "generation":row.get("generation").cloned().unwrap_or(Value::Null),
        "expires_at":row.get("expires_at").cloned().unwrap_or(Value::Null)
    }))
}

fn safe_id(summary: &Value) -> Result<&str> {
    let id = summary
        .get("id")
        .and_then(Value::as_str)
        .context("message id missing")?;
    ensure!(
        !id.is_empty()
            && id.len() <= 128
            && id
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_')),
        "unsafe message id in export"
    );
    Ok(id)
}

fn complete_page(api: &Api<'_>, request: &Value) -> Result<Value> {
    let deadline = Instant::now() + Duration::from_secs(900);
    let mut reply = api.search(request)?;
    loop {
        match reply {
            SearchReply::Complete(page) => return Ok(page),
            SearchReply::Running {
                job_id,
                retry_after,
            } => {
                ensure!(Instant::now() < deadline, "mailbox export search timed out");
                std::thread::sleep(retry_after.min(Duration::from_secs(5)));
                reply = api.poll_search_job(&job_id)?;
            }
        }
    }
}

fn write_bundle(api: &Api<'_>, address: &str, temporary: &Path) -> Result<u64> {
    let snapshot = active_snapshot(&api.addresses()?, address)?;
    let mut open = OpenOptions::new();
    open.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        open.mode(0o600);
    }
    let file = open.open(temporary)?;
    let mut bundle = ZipWriter::new(file);
    let options = SimpleFileOptions::default().compression_method(zip::CompressionMethod::Stored);
    let mut request = json!({"mailbox":address,"limit":100});
    let mut cursors = HashSet::new();
    let mut message_ids = HashSet::new();
    let mut count = 0_u64;
    loop {
        let page = complete_page(api, &request)?;
        let messages = page
            .get("messages")
            .and_then(Value::as_array)
            .context("invalid export page")?;
        for summary in messages {
            let id = safe_id(summary)?;
            ensure!(
                message_ids.insert(id.to_owned()),
                "mailbox export repeated a message"
            );
            let archive = api.archive(id)?;
            bundle.start_file(format!("messages/{id}.zip"), options)?;
            bundle.write_all(&archive)?;
            bundle.start_file(format!("messages/{id}.json"), options)?;
            serde_json::to_writer(&mut bundle, summary)?;
            count += 1;
        }
        let Some(cursor) = page.get("next_cursor").and_then(Value::as_str) else {
            break;
        };
        ensure!(
            !cursor.is_empty() && cursors.insert(cursor.to_owned()),
            "mailbox export repeated a cursor"
        );
        request["cursor"] = json!(cursor);
    }
    ensure!(
        snapshot == active_snapshot(&api.addresses()?, address)?,
        "mailbox lifetime changed during export"
    );
    bundle.start_file("manifest.json", options)?;
    serde_json::to_writer(
        &mut bundle,
        &json!({
            "schema":"amail.mailbox-export.v1",
            "mailbox":snapshot,
            "message_count":count,
            "exported_at":chrono::Utc::now().timestamp_millis()
        }),
    )?;
    bundle.finish()?.sync_all()?;
    Ok(count)
}

/// The caller holds a cloud read lease. Release/expiry remains irreversible;
/// this command must finish while the selected address generation is active.
pub fn run(api: &Api<'_>, address: &str, out: &PathBuf, human: bool) -> Result<()> {
    ensure!(!out.exists(), "export destination already exists");
    let temporary = out.with_extension(format!("amail-{}.tmp", uuid::Uuid::new_v4()));
    let result = (|| -> Result<u64> {
        let count = write_bundle(api, address, &temporary)?;
        // Same-directory hard-link publication is atomic and refuses an existing
        // destination, unlike rename's overwrite semantics on Unix.
        std::fs::hard_link(&temporary, out)
            .context("publishing mailbox export without overwrite")?;
        #[cfg(unix)]
        {
            let parent = out
                .parent()
                .filter(|p| !p.as_os_str().is_empty())
                .unwrap_or(Path::new("."));
            std::fs::File::open(parent)?.sync_all()?;
        }
        Ok(count)
    })();
    let _ = std::fs::remove_file(&temporary);
    let count = result?;
    crate::emit(
        &json!({"exported":true,"address":address,"path":out,"messages":count}),
        human,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn export_entry_names_cannot_escape_the_bundle() {
        for id in [
            "",
            ".",
            "..",
            "../outside",
            "a/b",
            "a\\b",
            "x:y",
            "a\0b",
            "é",
        ] {
            assert!(safe_id(&json!({"id":id})).is_err(), "accepted {id:?}");
        }
        for byte in 0_u8..=127 {
            let id = format!("message{}id", char::from(byte));
            let expected = byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_');
            assert_eq!(safe_id(&json!({"id":id})).is_ok(), expected);
        }
    }

    #[test]
    fn temporary_generation_is_mandatory_and_part_of_snapshot() {
        let row = json!({"address":"a@tmpaddr.moesegfault.dev","state":"active","kind":"tmpaddr","generation":"first","expires_at":123});
        let first = active_snapshot(
            &json!({"addresses":[row.clone()]}),
            "a@tmpaddr.moesegfault.dev",
        )
        .unwrap();
        let mut replacement = row.clone();
        replacement["generation"] = json!("second");
        let second = active_snapshot(
            &json!({"addresses":[replacement]}),
            "a@tmpaddr.moesegfault.dev",
        )
        .unwrap();
        assert_ne!(first, second);
        let mut missing = row;
        missing.as_object_mut().unwrap().remove("generation");
        assert!(
            active_snapshot(&json!({"addresses":[missing]}), "a@tmpaddr.moesegfault.dev").is_err()
        );
        assert!(active_snapshot(&json!({"addresses":[]}), "a@tmpaddr.moesegfault.dev").is_err());
    }
}
