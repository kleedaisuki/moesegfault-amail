"""One protected staging native self-send; never infer delivery or retry uncertainty.

Called only after the two-SMTP journey has cleaned up. The caller removes its
credential home; server acceptance journals and non-content UUID recovery evidence
remain. No private mail or credentials may become public artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
import uuid

import staging_mail_e2e as mail


def one(binary: Path, env: dict[str, str], *args: str) -> dict:
    """Read exactly one native result without exposing any private output."""
    rows = mail.amail(binary, env, *args, failure="owned_send_cli_failed")
    mail.check(len(rows) == 1, "owned_send_result_shape")
    return rows[0]


def owner_subject(account: str, token: str, address: str) -> str:
    """Read the exact active address owner from the existing parameterized D1 row."""
    import urllib.request
    req = urllib.request.Request(
        f"{mail.API}/accounts/{account}/d1/database/{mail.ACCOUNT_DB}/query",
        data=json.dumps({"sql": mail.ADDRESS_ROW_SQL, "params": [address]}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
    try:
        with mail.control_open(req, timeout=25) as response:
            mail.check(response.status == 200, "owned_send_owner_read_failed")
            raw = response.read(262145)
        mail.check(len(raw) <= 262144, "owned_send_owner_read_oversized")
        value = json.loads(raw)
        batches = value.get("result")
        mail.check(value.get("success") is True and isinstance(batches, list) and len(batches) == 1,
                   "owned_send_owner_read_shape")
        rows = batches[0].get("results")
        mail.check(batches[0].get("success") is True and isinstance(rows, list) and len(rows) == 1,
                   "owned_send_owner_read_shape")
        row = rows[0]
        subject = row.get("owner_sub")
        mail.check(row.get("state") == "active" and row.get("owner_iss") == mail.ISSUER
                   and row.get("needs_reconcile") == 0 and isinstance(row.get("cf_rule_id"), str)
                   and isinstance(subject, str) and bool(re.fullmatch(r"[!-~]{1,256}", subject)),
                   "owned_send_owner_unverified")
        return subject
    except mail.ProbeFailure:
        raise
    except Exception:
        raise mail.ProbeFailure("owned_send_owner_read_failed") from None


def prepare(binary: Path, env: dict[str, str], task: Path, address: str, title: str) -> tuple[str, Path]:
    """Persist a fresh logical UUID and the exact native-packed ZIP before submission."""
    task.mkdir(exist_ok=False)
    draft = task / "draft"
    draft.mkdir()
    (draft / "manifest.toml").write_text(
        f'version = 1\nfrom = "{address}"\nto = ["{address}"]\nsubject = "{title}"\n', encoding="utf-8")
    (draft / "body.txt").write_text("Protected staging self-notification acceptance.\n", encoding="utf-8")
    archive = task / "intent.zip"
    one(binary, env, "pack", str(draft), "-o", str(archive))
    key = str(uuid.uuid4())
    intent = {"schema": "amail.staging-owned-intent.v1", "idempotency_key": key,
              "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "title": title,
              "mailbox": address}
    with (task / "intent.json").open("x", encoding="utf-8") as out:
        json.dump(intent, out)
        out.flush()
        os.fsync(out.fileno())
    return key, archive


def preserve_intent(archive: Path, key: str, nonce: str) -> tuple[Path, Path]:
    """Retain exact private ZIP bytes outside disposable homes before any send grant.

    Existing recovery files are never overwritten. Unknown submissions retain both
    this archive and its original UUID; neither file is eligible for public upload.
    """
    mail.check(bool(re.fullmatch(r"[a-f0-9]{16}", nonce)), "owned_send_nonce_invalid")
    saved = mail.TEMP / f"staging-owned-send-recovery-{nonce}.zip"
    recovery = mail.TEMP / f"staging-owned-send-receipt-{nonce}.json"
    payload = archive.read_bytes()
    with saved.open("xb") as out:
        os.chmod(saved, 0o600)
        out.write(payload)
        out.flush()
        os.fsync(out.fileno())
    digest = hashlib.sha256(payload).hexdigest()
    mail.check(hashlib.sha256(saved.read_bytes()).hexdigest() == digest,
               "owned_send_recovery_zip_mismatch")
    with recovery.open("x", encoding="utf-8") as out:
        os.chmod(recovery, 0o600)
        json.dump({"schema": "amail.staging-owned-receipt.v1", "idempotency_key": key,
                   "archive_sha256": digest, "archive": saved.name, "state": "unresolved"}, out)
        out.flush()
        os.fsync(out.fileno())
    return saved, recovery


def accepted(row: dict, key: str) -> str:
    """Only positive server acceptance authorizes the same-key replay."""
    mail.check(row.get("idempotency_key") == key and row.get("state") == "accepted",
               "owned_send_unresolved_no_resend")
    target = row.get("id")
    mail.check(isinstance(target, str) and mail.MAIL_ID.fullmatch(target) is not None,
               "owned_send_accepted_id_missing")
    return target


def update_recovery(path: Path, changes: dict) -> None:
    """Atomically extend private evidence without risking the original UUID record."""
    value = json.loads(path.read_text(encoding="utf-8"))
    value.update(changes)
    temporary = path.with_name(path.name + ".update")
    with temporary.open("x", encoding="utf-8") as out:
        os.chmod(temporary, 0o600)
        json.dump(value, out)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def mapping_observation(provider: str, wire: str) -> dict[str, bool]:
    """Observe this one fixture only, never assert a provider-wide RFC contract."""
    def without_brackets(value: str) -> str:
        """Remove only a matching outer angle-bracket pair, preserving ID case."""
        return value[1:-1] if value.startswith("<") and value.endswith(">") else value
    return {"exactly_equal": provider == wire,
            "anglebracket_normalization_equal": without_brackets(provider) == without_brackets(wire)}


def send_lost_output(binary: Path, env: dict[str, str], key: str, archive: Path) -> None:
    """Discard first stdout by design; a timeout still leads only to receipt reads."""
    try:
        subprocess.run([str(binary), "send", str(archive), "--idempotency-key", key],
                       env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        pass


def inventory(binary: Path, env: dict[str, str], address: str, title: str) -> dict[str, dict]:
    """Select only the task's exact mailbox/title, never arbitrary owner mail."""
    rows = mail.amail(binary, env, "search", "--mailbox", address, "--title", title,
                      "--limit", "10", "--wait-seconds", "60", failure="owned_send_inventory_failed")
    found = {}
    for row in rows:
        mail.check(row.get("mailbox") == address and row.get("subject") == title
                   and row.get("direction") in ("inbound", "outbound")
                   and isinstance(row.get("id"), str) and mail.MAIL_ID.fullmatch(row["id"])
                   and row["id"] not in found, "owned_send_inventory_unverified")
        found[row["id"]] = row
    mail.check(len(found) <= 2, "owned_send_duplicate_message")
    return found


def detail(binary: Path, env: dict[str, str], target: str, address: str, title: str, direction: str) -> dict:
    """Corroborate a task-owned ID before using it as a deletion or relation oracle."""
    row = one(binary, env, "get", target)
    mail.check(row.get("id") == target and row.get("mailbox") == address
               and row.get("subject") == title and row.get("from") == address and row.get("to") == [address]
               and row.get("direction") == direction and isinstance(row.get("metadata"), dict),
               "owned_send_message_unverified")
    return row


def await_projection(binary: Path, env: dict[str, str], key: str) -> dict:
    """Poll the existing intent read, never replay while archive projection is pending."""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        row = one(binary, env, "send-status", key)
        accepted(row, key)
        if row.get("projection_state") == "archived":
            return row
        mail.check(row.get("projection_state") == "pending", "owned_send_projection_shape")
        time.sleep(5)
    raise mail.ProbeFailure("owned_send_projection_timeout_no_resend")


def replay_accepted(binary: Path, env: dict[str, str], key: str, archive: Path,
                    receipt: dict, provider: str, address: str, title: str) -> None:
    """Replay precisely once after positive acceptance, preserving local and provider IDs."""
    target = accepted(receipt, key)
    mail.check(hashlib.sha256(archive.read_bytes()).hexdigest() ==
               json.loads((archive.parent / "intent.json").read_text())["archive_sha256"], "owned_send_zip_changed")
    replay = one(binary, env, "send", str(archive), "--idempotency-key", key)
    mail.check(replay.get("id") == target and replay.get("state") == "accepted", "owned_send_replay_mismatch")
    after = detail(binary, env, target, address, title, "outbound")
    mail.check(after["metadata"].get("provider_id") == provider, "owned_send_provider_changed")
    mail.check(accepted(one(binary, env, "send-status", key, "--local"), key) == target,
               "owned_send_replay_local_receipt_mismatch")


def verify_feedback(binary: Path, env: dict[str, str], target: str, address: str) -> None:
    """Require real delivered feedback and its indexed event within a bounded wait."""
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        outcome = one(binary, env, "outcomes", target)
        mail.check(outcome.get("id") == target and isinstance(outcome.get("outcomes"), list),
                   "owned_send_outcome_shape")
        rows = outcome["outcomes"]
        mail.check(all(r.get("recipient") == address for r in rows), "owned_send_feedback_recipient")
        mail.check(not any(r.get("kind") in ("failed", "rejected", "bounced", "complained") for r in rows),
                   "owned_send_negative_feedback")
        delivered = [r for r in rows if r.get("kind") == "delivered"]
        events = mail.amail(binary, env, "events", "--message", target, "--limit", "20",
                            failure="owned_send_events_failed")
        if delivered and any(e.get("message_id") == target and e.get("recipient") == address
                             and e.get("kind") == "delivered" and e.get("event_id") == delivered[0].get("event_id")
                             for e in events):
            return
        time.sleep(5)
    raise mail.ProbeFailure("owned_send_feedback_timeout_no_resend")


def retire(binary: Path, env: dict[str, str], zone: str, route_token: str,
           account: str, token: str, address: str) -> None:
    """Attempt exact alias removal once and verify both route and D1 reconciliation."""
    try:
        one(binary, env, "address", "delete", address)
    except Exception:
        pass
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        state = mail.row_snapshot(account, token, address)
        route = mail.route_snapshot(zone, route_token, address)
        if route == "route_absent" and state in (("retired", "null", "reconcile_0"),
                                                ("row_absent", "absent", "absent")):
            rows = mail.amail(binary, env, "address", "list", failure="owned_send_retire_readback")
            if not any(r.get("address") == address for r in rows):
                return
        time.sleep(3)
    raise mail.ProbeFailure("owned_send_cleanup_alias_unverified")


def verify_task_counts(account: str, token: str, address: str, title: str) -> None:
    """Corroborate soft deletion and at-most-one submission using exact alias counts."""
    import urllib.request
    sql = ("SELECT COUNT(*) AS total, "
           "COALESCE(SUM(CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END),0) AS active, "
           "COALESCE(SUM(CASE WHEN subject!=?2 OR direction NOT IN ('inbound','outbound') THEN 1 ELSE 0 END),0) AS unexpected, "
           "COALESCE(SUM(CASE WHEN direction='inbound' THEN 1 ELSE 0 END),0) AS inbound, "
           "COALESCE(SUM(CASE WHEN direction='outbound' THEN 1 ELSE 0 END),0) AS outbound "
           "FROM messages WHERE address=?1")
    req = urllib.request.Request(
        f"{mail.API}/accounts/{account}/d1/database/{mail.ACCOUNT_DB}/query",
        data=json.dumps({"sql": sql, "params": [address, title]}).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"}, method="POST")
    try:
        with mail.control_open(req, timeout=25) as response:
            mail.check(response.status == 200, "owned_send_cleanup_counts_unverified")
            raw = response.read(65537)
        mail.check(len(raw) <= 65536, "owned_send_cleanup_counts_unverified")
        value = json.loads(raw)
        batches = value.get("result")
        mail.check(value.get("success") is True and isinstance(batches, list) and len(batches) == 1,
                   "owned_send_cleanup_counts_unverified")
        rows = batches[0].get("results")
        mail.check(batches[0].get("success") is True and isinstance(rows, list) and len(rows) == 1,
                   "owned_send_cleanup_counts_unverified")
        row = rows[0]
        mail.check(set(row) == {"total", "active", "unexpected", "inbound", "outbound"}
                   and all(type(v) is int for v in row.values())
                   and row["active"] == row["unexpected"] == 0
                   and 0 <= row["inbound"] <= 1 and 0 <= row["outbound"] <= 1
                   and row["total"] == row["inbound"] + row["outbound"],
                   "owned_send_cleanup_counts_unverified")
    except mail.ProbeFailure:
        raise
    except Exception:
        raise mail.ProbeFailure("owned_send_cleanup_counts_unverified") from None


def cleanup(binary: Path, env: dict[str, str], zone: str, route_token: str, account: str,
            token: str, address: str, title: str, key: str | None) -> None:
    """Close ingress first; delete exact task messages, never revoke accepted journals."""
    primary = None
    try:
        retire(binary, env, zone, route_token, account, token, address)
    except Exception:
        primary = mail.ProbeFailure("owned_send_cleanup_alias_unverified")
    try:
        # Allow already queued ingress to settle after route removal.
        if key:
            time.sleep(30)
        found = inventory(binary, env, address, title)
        if key:
            try:
                receipt = one(binary, env, "send-status", key)
                if receipt.get("state") == "accepted":
                    receipt = await_projection(binary, env, key)
                    target = accepted(receipt, key)
                    if target not in found:
                        found[target] = detail(binary, env, target, address, title, "outbound")
                else:
                    raise mail.ProbeFailure("owned_send_cleanup_unresolved_journal_preserved")
            except Exception:
                # Still remove independently verified task content. A missing/unknown
                # receipt remains unresolved, preserved server-side, and never replayed.
                primary = mail.acceptance_failure(primary,
                    mail.ProbeFailure("owned_send_cleanup_unresolved_journal_preserved"))
        for target, row in found.items():
            detail(binary, env, target, address, title, row["direction"])
        for target in found:
            succeeded = mail.cleanup_delete_once(binary, env, target)
            mail.amail_not_found(binary, env, "get", target)
            mail.check(succeeded, "owned_send_cleanup_delete_unverified")
        mail.check(not inventory(binary, env, address, title), "owned_send_cleanup_mail_remaining")
        verify_task_counts(account, token, address, title)
    except Exception:
        primary = mail.acceptance_failure(primary, mail.ProbeFailure("owned_send_cleanup_messages_unverified"))
    if primary:
        raise primary


def grant_failure_reason(error: Exception) -> str:
    """Retain closed canary guards or transport/shape categories, never remote text."""
    guards = {"staging_canary_context_unverified", "staging_canary_owner_unverified",
              "staging_canary_route_unverified", "staging_canary_live_slot_or_hold_changed",
              "staging_canary_readback_unverified"}
    value = error.args[0] if isinstance(error, ValueError) and len(error.args) == 1 else None
    if isinstance(value, str) and value in guards:
        return "owned_send_grant_" + value
    if isinstance(error, (TypeError, KeyError)):
        return "owned_send_grant_shape_unverified"
    if isinstance(error, (TimeoutError, OSError)):
        return "owned_send_grant_transport_unverified"
    # The grant imports its reader before use. Do not import another dependency
    # while classifying a failure; diagnostics must not replace the original error.
    forwarding = sys.modules.get("ensure_role_forwarding")
    if forwarding is not None and isinstance(error, forwarding.ProvisionError):
        return "owned_send_grant_route_read_unverified"
    return "owned_send_grant_unverified"


def execute(binary: Path, home: Path, run_dir: Path, nonce: str) -> None:
    """Run at most one new provider submission under the guarded self-only grant."""
    mail.check(os.environ.get("AMAIL_STAGING_CANARY_CONFIRM") == "RUN_STAGING_OWNED_SEND_V012",
               "owned_send_confirmation_required")
    mail.check(bool(re.fullmatch(r"[a-f0-9]{16}", nonce)), "owned_send_nonce_invalid")
    binary, home, run_dir = map(lambda p: mail.inside_temp(str(p)), (binary, home, run_dir))
    account, token = os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""), os.environ.get("CLOUDFLARE_API_TOKEN", "")
    zone, route_token = os.environ.get("CLOUDFLARE_ZONE_ID", ""), os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
    mail.check(bool(re.fullmatch(r"[a-f0-9]{32}", account)) and bool(token)
               and bool(re.fullmatch(r"[a-f0-9]{32}", zone)) and bool(route_token), "owned_send_credentials_missing")
    env = mail.cli_env(home)
    part, title = f"send-{nonce}", f"amail-owned-send-{nonce}"
    address = f"{part}@{mail.DOMAIN}"
    mail.assert_address_creation_preflight(mail.amail(binary, env, "address", "list", failure="owned_send_preflight"),
                                           mail.cf_rules(zone, route_token), address)
    attempted, submitted, key, primary = False, False, None, None
    saved_archive = None
    acceptance_proven = False
    try:
        attempted = True
        result = one(binary, env, "address", "add", part)
        mail.check(result.get("address") == address, "owned_send_alias_mismatch")
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            rows = mail.amail(binary, env, "address", "list", failure="owned_send_alias_readback")
            if len([r for r in rows if r.get("address") == address and r.get("state") == "active"]) == 1:
                break
            time.sleep(3)
        else:
            raise mail.ProbeFailure("owned_send_alias_activation_timeout")
        mail.assert_route(zone, route_token, address, True)
        subject = owner_subject(account, token, address)
        # Give verified literal-route propagation a bounded grace, not a retry send.
        time.sleep(60)
        mail.assert_route(zone, route_token, address, True)
        key, archive = prepare(binary, env, run_dir / "owned-send", address, title)
        saved_archive, recovery = preserve_intent(archive, key, nonce)
        operator = str(mail.ROOT / "infra" / "operator")
        if operator not in sys.path:
            sys.path.insert(0, operator)
        from grant_canary import grant_staging_owned
        try:
            grant_staging_owned(account, token, address, subject, f"staging-owned-{nonce}")
        except Exception as error:
            raise mail.ProbeFailure(grant_failure_reason(error)) from None
        submitted = True
        send_lost_output(binary, env, key, archive)
        receipt = await_projection(binary, env, key)
        target = accepted(receipt, key)
        local = one(binary, env, "send-status", key, "--local")
        mail.check(accepted(local, key) == target, "owned_send_local_receipt_mismatch")
        before = detail(binary, env, target, address, title, "outbound")
        provider = before["metadata"].get("provider_id")
        mail.check(isinstance(provider, str) and bool(provider), "owned_send_provider_id_missing")
        acceptance_proven = True
        # The exact original ZIP remains private until the complete probe succeeds.
        update_recovery(recovery, {"id": target, "provider_id": provider, "state": "accepted"})
        replay_accepted(binary, env, key, archive, receipt, provider, address, title)
        verify_feedback(binary, env, target, address)
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            found = inventory(binary, env, address, title)
            inbound = [r for r in found.values() if r["direction"] == "inbound"]
            if len(inbound) == 1:
                row = detail(binary, env, inbound[0]["id"], address, title, "inbound")
                dest = archive.parent / "received"
                mail.safe_zip(binary, env, row["id"], archive.parent / "received.zip", dest)
                manifest = tomllib.loads((dest / "manifest.toml").read_text(encoding="utf-8"))
                rfc = row["metadata"].get("rfc_message_id")
                mail.check(isinstance(rfc, str) and manifest.get("rfc_message_id") == rfc,
                           "owned_send_received_rfc_missing")
                mail.check(manifest.get("from") == address and manifest.get("to") == [address]
                           and manifest.get("subject") == title
                           and (dest / "body.txt").read_text(encoding="utf-8").strip() ==
                           "Protected staging self-notification acceptance.", "owned_send_received_archive_mismatch")
                # Outbound metadata deliberately leaves the wire identity unknown.
                # Record this one real fixture comparison without upgrading it to a
                # provider contract; received manifest/get agreement is header evidence.
                update_recovery(recovery, {"provider_to_wire_observation": mapping_observation(provider, rfc)})
                print("staging_owned_send_mapping_observed_for_fixture")
                print("staging_owned_send_provider_to_rfc_mapping_not_asserted")
                break
            time.sleep(5)
        else:
            raise mail.ProbeFailure("owned_send_inbound_timeout_no_resend")
        print("staging_owned_send_receipt_replay_feedback_and_inbound_verified")
    except mail.ProbeFailure as error:
        primary = error
    except Exception:
        primary = mail.ProbeFailure("owned_send_unexpected_failure")
    finally:
        if attempted:
            try:
                cleanup(binary, env, zone, route_token, account, token, address, title, key if submitted else None)
            except mail.ProbeFailure as error:
                primary = mail.acceptance_failure(primary, error)
    if primary:
        raise primary
    if acceptance_proven and saved_archive is not None:
        saved_archive.unlink()
