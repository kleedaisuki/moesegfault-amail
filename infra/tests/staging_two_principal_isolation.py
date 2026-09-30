"""Check B's denials against A's already verified live SMTP fixtures.

This helper creates no address, route, or SMTP submission. Only the ordinary
A-owned harness may clean up the two fixtures and their exact provider route.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

import staging_mail_e2e as mail


def ensure(condition: bool, label: str) -> None:
    """Use fixed-label failures so no private CLI/provider data reaches logs."""

    if not condition:
        raise mail.ProbeFailure(label)


def foreign_denied(binary: Path, env: dict[str, str], *args: str,
                   output: Path | None = None) -> None:
    """Require exact typed 404 and no stdout or written archive."""

    if output is not None:
        ensure(not output.exists(), "foreign_output_preexisting")
    wrote = False
    try:
        result = subprocess.run([str(binary), *args], env=env, capture_output=True,
                                timeout=90, check=False)
    except (subprocess.TimeoutExpired, OSError):
        raise mail.ProbeFailure("foreign_process_failed") from None
    finally:
        # A denied archive must not remain in B's home even if the CLI errs.
        if output is not None and output.exists():
            wrote = True
            if output.is_file():
                output.unlink()
    ensure(not wrote, "foreign_archive_created")
    ensure(result.returncode != 0 and not result.stdout and
           mail.cli_failure(result.stderr, "foreign_denied") ==
           "foreign_denied_http_404_not_found", "foreign_id_disclosed_or_mutated")
    ensure(output is None or not output.exists(), "foreign_archive_created")


def assert_b_ready(binary: Path, home_a: Path, home_b: Path) -> None:
    """Reject nonempty B before A creates a route or submits any SMTP."""

    ensure(home_a != home_b and home_a.is_dir() and home_b.is_dir(),
           "principal_homes_not_distinct")
    env = mail.cli_env(home_b)
    status = mail.amail(binary, env, "auth", "status", failure="principal_auth_failed")
    ensure(len(status) == 1 and status[0].get("authenticated") is True,
           "principal_auth_missing")
    ensure(not mail.amail(binary, env, "address", "list", failure="foreign_address_list_failed"),
           "foreign_mailbox_not_empty")
    ensure(not mail.rows(mail.amail(binary, env, "sync", "--all", failure="foreign_sync_failed")),
           "foreign_sync_not_empty")


def owner_row(binary: Path, env: dict[str, str], target: str) -> dict:
    """Require one unread row for the independently verified A fixture."""

    values = mail.amail(binary, env, "get", target, failure="owner_get_failed")
    ensure(len(values) == 1 and values[0].get("id") == target
           and values[0].get("read") is False, "owner_fixture_missing_or_changed")
    return values[0]


def stable_owner_row(value: dict) -> dict:
    """Exclude only the documented per-request correlation ID from equality."""

    ensure(isinstance(value.get("request_id"), str), "owner_request_id_missing")
    return {key: item for key, item in value.items() if key != "request_id"}


def owner_unchanged(binary: Path, env: dict[str, str],
                    signal_id: str, distractor_id: str,
                    prior: dict, other: dict) -> None:
    """Read both A fixtures immediately after each foreign ID operation."""

    ensure(stable_owner_row(owner_row(binary, env, signal_id)) == stable_owner_row(prior)
           and stable_owner_row(owner_row(binary, env, distractor_id)) == stable_owner_row(other),
           "owner_state_changed_by_foreign")


def assert_foreign_isolation(
    binary: Path, home_a: Path, home_b: Path, address: str,
    signal_id: str, distractor_id: str, subjects: tuple[str, str],
    provider_message_id: str, zone: str, routing_token: str,
) -> None:
    """Prove A-positive/B-negative/owner-unchanged without new provider state."""

    ensure(home_a != home_b and home_a.is_dir() and home_b.is_dir(),
           "principal_homes_not_distinct")
    ensure(all(re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in
               (signal_id, distractor_id)), "fixture_id_invalid")
    ensure(len(subjects) == 2 and len(set(subjects)) == 2 and
           all(re.fullmatch(r"AMAIL-E2E-[a-f0-9]{16}-(Signal|Distractor)", value)
               for value in subjects), "fixture_subject_invalid")
    env_a, env_b = mail.cli_env(home_a), mail.cli_env(home_b)
    for env in (env_a, env_b):
        status = mail.amail(binary, env, "auth", "status", failure="principal_auth_failed")
        ensure(len(status) == 1 and status[0].get("authenticated") is True,
               "principal_auth_missing")
    prior = owner_row(binary, env_a, signal_id)
    other = owner_row(binary, env_a, distractor_id)
    metadata = prior.get("metadata")
    ensure(prior.get("mailbox") == address and other.get("mailbox") == address
           and {prior.get("subject"), other.get("subject")} == set(subjects)
           and isinstance(metadata, dict) and metadata.get("message_id") == provider_message_id,
           "owner_positive_controls_missing")
    owned = mail.amail(binary, env_b, "address", "list", failure="foreign_address_list_failed")
    ensure(not owned, "foreign_mailbox_not_empty")
    synced = mail.rows(mail.amail(binary, env_b, "sync", "--all", failure="foreign_sync_failed"))
    ensure(not synced, "foreign_sync_disclosed")
    for subject in subjects:
        values = mail.rows(mail.amail(binary, env_b, "search", "--title", subject,
                                      failure="foreign_search_failed"))
        ensure(not values, "foreign_search_disclosed")
    values = mail.rows(mail.amail(binary, env_b, "search", "--meta",
                                  f"message_id={provider_message_id}",
                                  failure="foreign_metadata_search_failed"))
    ensure(not values, "foreign_metadata_disclosed")
    # One well-formed nonexistent ID should have the same public status/code.
    nonexistent = "i" + "0" * 31
    ensure(nonexistent not in (signal_id, distractor_id), "negative_id_collision")
    output = home_b / "foreign-denied.zip"
    operations = (
        ("get",), ("read", "-o", str(output)),
        ("mark", "--read"), ("mark", "--unread"), ("delete",),
    )
    for args in operations:
        for target in (nonexistent, signal_id):
            if args[0] == "read":
                foreign_denied(binary, env_b, args[0], target, *args[1:], output=output)
            else:
                foreign_denied(binary, env_b, args[0], target, *args[1:])
            owner_unchanged(binary, env_a, signal_id, distractor_id, prior, other)
    foreign_denied(binary, env_b, "address", "delete", address)
    owner_unchanged(binary, env_a, signal_id, distractor_id, prior, other)
    for subject in subjects:
        hits = mail.rows(mail.amail(binary, env_a, "search", "--title", subject,
                                   failure="owner_search_after_foreign_failed"))
        ensure(len(hits) == 1 and hits[0].get("id") in (signal_id, distractor_id),
               "owner_search_changed_by_foreign")
    addresses = mail.amail(binary, env_a, "address", "list",
                           failure="owner_address_after_foreign_failed")
    ensure(len([item for item in addresses if item.get("address") == address
                and item.get("state") == "active"]) == 1,
           "owner_address_changed_by_foreign")
    mail.assert_route(zone, routing_token, address, True)
