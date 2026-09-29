"""One-shot, fail-closed CLI cleanup of the fifth hosted E2E's two fixtures.

Only the authenticated synthetic account may enumerate and delete messages.
The control-plane aggregate is corroborating evidence, not a principal proof;
it excludes foreign-owner rows by construction. Never print provider output.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from staging_fifth_mail_audit import ATTEMPT, RUN, aggregate, fixture_subjects
from staging_prior_alias_reconcile import alias, required, route_absent, rules
from staging_hosted_e2e import BUILT_BINARY, ROOT, TEMP, safe_stage_code, unique_auth_home
from staging_mail_e2e import SENDER, cli_env


CONFIRM = "DELETE_FIFTH_MAIL_EXACT_FIXTURES"
ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
CURSOR = re.compile(r"[A-Za-z0-9_.~:-]{1,4096}\Z")
CODE = re.compile(rb"(?:^|\n)amail: mail API [a-z.]+ failed: HTTP ([45][0-9]{2})(?: [A-Za-z ]{1,40})?, code=([a-z][a-z0-9_]{0,48})(?:, correlation_id=[^,\r\n]{1,128})?(?:, diag=[^,\r\n]{1,100})?(?:, cf_error=[^,\r\n]{1,40})?\r?(?:\n|$)")
RUNNING_JOB = re.compile(rb"search job ([A-Za-z0-9_-]{1,128}) still running; resume with `amail search --resume [A-Za-z0-9_-]{1,128}`")


class CleanupFailure(Exception):
    """Fixed, nonsensitive failure code for the hosted log."""


def require(ok: bool, label: str) -> None:
    """Stop on any ambiguous observation before further mutation."""

    if not ok:
        raise CleanupFailure(label)


def cli(binary: Path, env: dict[str, str], *args: str) -> tuple[int, list[dict], bytes]:
    """Capture bounded CLI output privately, returning only parsed JSONL to callers."""

    try:
        result = subprocess.run([str(binary), *args], env=env, capture_output=True,
                                timeout=360 if args[0] == "search" else 90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise CleanupFailure("cli_transport_unverified") from None
    require(len(result.stdout) <= 2_000_000 and len(result.stderr) <= 65_536,
            "cli_output_unverified")
    try:
        import json
        rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except (ValueError, UnicodeDecodeError):
        raise CleanupFailure("cli_output_unverified") from None
    require(all(isinstance(row, dict) for row in rows), "cli_output_unverified")
    return result.returncode, rows, result.stderr


def failure_code(stderr: bytes) -> tuple[int, str] | None:
    """Extract only a known HTTP status and public problem code."""

    found = CODE.search(stderr)
    return (int(found[1]), found[2].decode("ascii")) if found else None


def success(binary: Path, env: dict[str, str], *args: str) -> list[dict]:
    """Require an unambiguous successful CLI operation."""

    status, rows, _ = cli(binary, env, *args)
    require(status == 0, "cli_operation_unverified")
    return rows


def search_page(binary: Path, env: dict[str, str], args: list[str]) -> tuple[int, list[dict], bytes]:
    """Resume a previously accepted job privately instead of resubmitting filters."""

    for _ in range(3):
        status, lines, stderr = cli(binary, env, *args)
        match = RUNNING_JOB.search(stderr) if status != 0 else None
        if match is None:
            return status, lines, stderr
        job = match[1].decode("ascii")
        require(stderr.count(match[1]) >= 2, "search_job_unverified")
        args = ["search", "--resume", job, "--wait-seconds", "300"]
    raise CleanupFailure("search_job_unverified")


def inventory(binary: Path, env: dict[str, str], mailbox: str,
              title: str | None = None) -> dict[str, dict]:
    """Exhaust one owner-scoped search snapshot; retry only documented stale reads."""

    for attempt in range(3):
        cursor = None
        seen_cursors: set[str] = set()
        found: dict[str, dict] = {}
        for _page in range(100):
            args = ["search", "--mailbox", mailbox, "--limit", "100", "--wait-seconds", "300"]
            if title is not None:
                args.extend(("--title", title))
            if cursor is not None:
                args.extend(("--cursor", cursor))
            status, lines, stderr = search_page(binary, env, args)
            if status != 0:
                code = failure_code(stderr)
                if code in ((409, "search_job_stale"), (409, "search_cursor_stale")) and attempt < 2:
                    time.sleep((2, 5)[attempt])
                    break
                raise CleanupFailure("search_unverified")
            markers = [row for row in lines if "next_cursor" in row]
            require(len(markers) <= 1 and (not markers or lines[-1] is markers[0]),
                    "search_shape_unverified")
            if markers:
                require(set(markers[0]) == {"next_cursor"} and
                        isinstance(markers[0]["next_cursor"], str) and
                        CURSOR.fullmatch(markers[0]["next_cursor"]) is not None and
                        markers[0]["next_cursor"] not in seen_cursors,
                        "search_cursor_unverified")
            for row in lines[:len(lines) - len(markers)]:
                msg_id = row.get("id")
                require(isinstance(msg_id, str) and ID.fullmatch(msg_id) is not None and
                        msg_id not in found and row.get("mailbox") == mailbox and
                        row.get("direction") == "inbound", "search_row_unverified")
                found[msg_id] = row
            if not markers:
                return found
            cursor = markers[0]["next_cursor"]
            seen_cursors.add(cursor)
        else:
            raise CleanupFailure("search_pages_unverified")
    raise CleanupFailure("search_unverified")


def control(account: str, token: str, route_token: str, mailbox: str,
            active: int | None, allow_purge: bool = False) -> dict:
    """Require the complete exact routing and D1 gate immediately before mutation."""

    try:
        absent = route_absent(rules(route_token), mailbox)
        row = aggregate(account, token, mailbox)
    except Exception:
        raise CleanupFailure("control_read_unverified") from None
    require(absent and row["address_state"] == "retired" and
            row["needs_reconcile"] == 0 and row["owner_expected"] == 1 and
            (active is None or row["signal_active"] + row["distractor_active"] == active) and
            (active is None or row["inbound_active"] == active) and
            row["signal_active"] <= 1 and row["distractor_active"] <= 1 and
            (row["signal_active"] + row["signal_deleted"] <= 1 if allow_purge else
             row["signal_active"] + row["signal_deleted"] == 1) and
            (row["distractor_active"] + row["distractor_deleted"] <= 1 if allow_purge else
             row["distractor_active"] + row["distractor_deleted"] == 1) and
            all(row[key] == 0 for key in ("other_inbound_active", "other_inbound_deleted",
                                         "outbound_active", "outbound_deleted", "embedding_pending",
                                         "embedding_quarantined")), "control_gate_failed")
    return row


def control_any(account: str, token: str, route_token: str, mailbox: str) -> dict:
    """Accept only the known two-fixture state, including safe prior soft deletes."""

    return control(account, token, route_token, mailbox, None)


def verify_row(binary: Path, env: dict[str, str], msg_id: str, mailbox: str,
               subject: str, signal: bool) -> None:
    """Corroborate each exact get field; reveal only fixed mismatch categories."""

    rows = success(binary, env, "get", msg_id)
    require(len(rows) == 1, "get_shape_unverified")
    row = rows[0]
    nonce = subject.split("-")[2]
    suffix = "signal" if signal else "distractor"
    metadata = row.get("metadata")
    # Keep each predicate independent so the hosted log identifies the failed
    # contract without emitting any received header, subject, or message ID.
    require(row.get("id") == msg_id, "fixture_get_id_mismatch")
    require(row.get("mailbox") == mailbox, "fixture_get_mailbox_mismatch")
    require(row.get("direction") == "inbound", "fixture_get_direction_mismatch")
    require(row.get("subject") == subject, "fixture_get_subject_mismatch")
    require(row.get("from") == SENDER, "fixture_get_from_mismatch")
    require(row.get("to") == [mailbox], "fixture_get_to_mismatch")
    require(row.get("has_text") is True, "fixture_get_text_mismatch")
    require(row.get("has_html") is signal, "fixture_get_html_mismatch")
    require(row.get("has_attachments") is signal, "fixture_get_attachments_mismatch")
    require(row.get("attachment_count") == (2 if signal else 0),
            "fixture_get_attachment_count_mismatch")
    require(isinstance(metadata, dict), "fixture_get_metadata_shape_mismatch")
    require(metadata.get("message_id") ==
            f"<amail-e2e-{nonce}-{suffix}@mail-staging.moesegfault.dev>",
            "fixture_get_message_id_mismatch")


def not_found(binary: Path, env: dict[str, str], msg_id: str) -> None:
    """Require exact 404/not_found for an already deleted owner-scoped ID."""

    status, _, stderr = cli(binary, env, "get", msg_id)
    require(status != 0 and failure_code(stderr) == (404, "not_found"),
            "delete_readback_unverified")


def delete_once(binary: Path, env: dict[str, str], msg_id: str) -> bool:
    """Issue exactly one CLI delete; accept only its proven empty-204 render shape.

    The CLI converts a 204 empty body to ``{"ok":true}``. A different or
    missing stdout cannot be interpreted as success, but callers must still
    read back the ID because the mutation may already have committed.
    """

    try:
        result = subprocess.run([str(binary), "delete", msg_id], env=env,
                                capture_output=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == b'{"ok":true}' and not result.stderr


def pin(account: str, token: str, version: str) -> None:
    """Require the reviewed 100%-serving Worker version and bindings."""

    sys.path.insert(0, str(ROOT / "infra" / "deploy"))
    from pin_staging_mail import UUID, run
    require(UUID.fullmatch(version) is not None, "version_invalid")
    try:
        require(run(account, token, version) == "match", "version_unverified")
    except Exception:
        raise CleanupFailure("version_unverified") from None


def execute() -> str:
    """Use a fresh native PKCE session, validate both rows, then delete per ID."""

    require(os.name == "nt", "windows_required")
    require(sys.argv == [sys.argv[0], CONFIRM, RUN, ATTEMPT], "confirmation_required")
    username = required("STAGING_E2E_USERNAME")
    password = required("STAGING_E2E_PASSWORD")
    account = required("CLOUDFLARE_ACCOUNT_ID")
    token = required("CLOUDFLARE_API_TOKEN")
    route_token = required("CF_EMAIL_ROUTING_TOKEN")
    version = required("AMAIL_EXPECTED_WORKER_VERSION")
    require(re.fullmatch(r"[a-z0-9_]{3,32}", username) is not None and
            15 <= len(password) <= 128 and
            re.fullmatch(r"[a-f0-9]{32}", account) is not None and
            TEMP == ROOT / ".temp" and BUILT_BINARY.is_file(), "configuration_invalid")
    mailbox = alias(password, RUN, ATTEMPT)
    subjects = fixture_subjects(mailbox)
    pin(account, token, version)
    initial = control_any(account, token, route_token, mailbox)
    require(initial["embedding_succeeded"] == 2 and
            initial["embedding_no_work"] == 0, "embedding_gate_failed")
    print("fifth_cleanup_preflight:verified")
    TEMP.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="fifth-mail-cleanup-", dir=TEMP)).resolve()
    require(TEMP in run_dir.parents, "temp_path_invalid")
    try:
        from staging_identity_cdp import native_login, store_credential
        binary = run_dir / "amail.exe"
        shutil.copy2(BUILT_BINARY, binary)
        store_credential(run_dir, username, password)
        del username, password
        native_login(run_dir, binary)
        home = unique_auth_home(run_dir)
        env = cli_env(home)
        auth = success(binary, env, "auth", "status")
        require(len(auth) == 1 and auth[0].get("authenticated") is True,
                "auth_unverified")
        print("fifth_cleanup_auth:verified")
        expected = dict(zip(subjects, (True, False)))
        full = inventory(binary, env, mailbox)
        active_subjects = {subject for subject, key in zip(subjects, ("signal_active", "distractor_active"))
                           if initial[key] == 1}
        require(len(full) == len(active_subjects) and
                {row.get("subject") for row in full.values()} == active_subjects,
                "inventory_mismatch")
        for subject, signal in expected.items():
            if subject not in active_subjects:
                continue
            titled = inventory(binary, env, mailbox, subject)
            matches = {key: value for key, value in titled.items()
                       if value.get("subject") == subject and value.get("mailbox") == mailbox}
            require(len(titled) == len(matches) == 1 and set(matches).issubset(full),
                    "title_inventory_mismatch")
            msg_id = next(iter(matches))
            require(full[msg_id].get("subject") == subject, "title_inventory_mismatch")
            verify_row(binary, env, msg_id, mailbox, subject, signal)
        control(account, token, route_token, mailbox, len(full))
        require(inventory(binary, env, mailbox) == full, "inventory_changed")
        pin(account, token, version)
        print("fifth_cleanup_fixture_gate:verified")
        for subject in subjects:
            if subject not in active_subjects:
                continue
            msg_id = next(key for key, row in full.items() if row["subject"] == subject)
            deleted = delete_once(binary, env, msg_id)
            # An ambiguous mutation is never retried; first read back that same ID.
            not_found(binary, env, msg_id)
            require(deleted, "delete_status_unverified")
            observed = inventory(binary, env, mailbox)
            require(set(observed) == set(full) - {msg_id}, "delete_inventory_unverified")
            full = observed
            control(account, token, route_token, mailbox, len(full), allow_purge=True)
            print("fifth_cleanup_delete_readback:verified")
        require(not inventory(binary, env, mailbox), "final_inventory_unverified")
        row = control(account, token, route_token, mailbox, 0, allow_purge=True)
        require(row["signal_deleted"] <= 1 and row["distractor_deleted"] <= 1,
                "final_deleted_counts_unverified")
        pin(account, token, version)
        return "verified"
    finally:
        require(TEMP in run_dir.parents and run_dir.name.startswith("fifth-mail-cleanup-"),
                "temp_path_invalid")
        try:
            shutil.rmtree(run_dir)
        except OSError:
            raise CleanupFailure("temp_cleanup_failed") from None


def main() -> int:
    """Emit fixed labels only; never surface raw CLI, Identity, or provider errors."""

    try:
        outcome = execute()
    except CleanupFailure as error:
        print(f"fifth_cleanup_failed:{safe_stage_code(error)}")
        return 1
    except Exception:
        print("fifth_cleanup_failed:unexpected_failure")
        return 1
    print(f"fifth_cleanup_final:{outcome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
