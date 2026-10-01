"""Guarded hosted quota prepare/campaign/recovery; workflow wiring remains NO-GO.

Only a registered manual staging workflow for the exact reviewed checkout can
enter. Credentials come from protected environment Secrets, never arguments or
output. This module does not register accounts, send mail, deploy Workers, alter
policy, upload artifacts or delete provider/R2 records directly.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

import staging_ten_address_artifact as artifact
import staging_ten_address_escrow as escrow
import staging_ten_address_hosted as hosted
import staging_ten_address_manifest as manifest
import staging_ten_address_native as native
import staging_ten_address_provenance as provenance
from staging_ten_address_readback import Readback
from staging_worker_created_r2 import github_json

ROOT = Path(__file__).resolve().parents[2]
TEMP = ROOT / ".temp"
require = manifest.require
CONFIRMS = {"prepare": "RUN_STAGING_TEN_ADDRESSES", "campaign": "RUN_STAGING_TEN_ADDRESSES",
            "recover": "RECOVER_STAGING_TEN_ADDRESSES"}
ESCROW_GENERATION = "ten-address-v1"


def checkout() -> str:
    """Compare actual checked-out git source with GitHub's immutable run SHA."""
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            stdin=subprocess.DEVNULL, check=False, timeout=20,
                            env={key: value for key, value in os.environ.items()
                                 if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"}})
    require(result.returncode == 0 and result.stderr == b"" and len(result.stdout) <= 42,
            "checkout_unverified")
    value = result.stdout.decode("ascii").strip()
    require(re.fullmatch(r"[a-f0-9]{40}", value) is not None and value == os.environ.get("GITHUB_SHA"),
            "checkout_unverified")
    return value


def dispatch_record(run: str, token: str, *, checkout_sha: str | None = None) -> dict:
    """Read actual original/manual workflow identity, never trust a supplied run ID alone."""
    manifest.coordinates(run, "1")
    try:
        value = github_json(f"/repos/{manifest.REPOSITORY}/actions/runs/{run}/attempts/1", token)
    except Exception:
        raise manifest.ContractFailure("dispatch_provenance_unverified") from None
    require(isinstance(value, dict) and value.get("id") == int(run) and value.get("run_attempt") == 1
            and value.get("event") == "workflow_dispatch"
            and value.get("head_branch") == manifest.BRANCH.removeprefix("refs/heads/")
            and value.get("path") in (artifact.RECOVERY_WORKFLOW, artifact.RECOVERY_WORKFLOW + "@" + manifest.BRANCH)
            and isinstance(value.get("repository"), dict)
            and value["repository"].get("full_name") == manifest.REPOSITORY
            and isinstance(value.get("head_sha"), str) and re.fullmatch(r"[a-f0-9]{40}", value["head_sha"]) is not None,
            "dispatch_provenance_unverified")
    require(checkout_sha is None or value["head_sha"] == checkout_sha and value.get("status") == "in_progress",
            "dispatch_provenance_unverified")
    return value


def environment(mode: str) -> dict[str, str]:
    """Reject local/unconfirmed/retried execution before reading any private capability."""
    require(mode in CONFIRMS and os.name == "nt" and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("RUNNER_OS") == "Windows"
            and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.environ.get("GITHUB_REPOSITORY") == manifest.REPOSITORY
            and os.environ.get("GITHUB_REF") == manifest.BRANCH
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
            and os.environ.get("AMAIL_QUOTA_ENVIRONMENT") == "staging"
            and os.environ.get("AMAIL_QUOTA_CONFIRM") == CONFIRMS[mode], "dispatch_unconfirmed")
    manifest.coordinates(os.environ.get("GITHUB_RUN_ID", ""), "1")
    keys = ("GITHUB_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ZONE_ID", "CLOUDFLARE_API_TOKEN",
            "CF_EMAIL_ROUTING_TOKEN", "STAGING_E2E_USERNAME", "STAGING_E2E_PASSWORD",
            "AMAIL_TEN_ADDRESS_RECOVERY_KEY", "AMAIL_TEN_ADDRESS_KEY_GENERATION")
    values = {key: os.environ.pop(key, "") for key in keys}
    require(all(values.values()), "quota_capability_missing")
    manifest.key_bytes(values["AMAIL_TEN_ADDRESS_RECOVERY_KEY"])
    require(re.fullmatch(r"[a-z0-9-]{1,40}", values["AMAIL_TEN_ADDRESS_KEY_GENERATION"]) is not None,
            "key_generation_invalid")
    return values


def prepared_file(run: str) -> Path:
    """Choose the one exact ciphertext upload path under an unredirected repository .temp."""
    manifest.coordinates(run, "1")
    require(TEMP.resolve() == TEMP, "quota_temp_redirected")
    return TEMP / ("ten-address-recovery-" + run) / "manifest.bin"


def activation(reader: Readback, allowed: tuple[str, ...]) -> manifest.Snapshot:
    """Poll existing candidate allocations only, without another add or provider mutation."""
    deadline = time.monotonic() + 360
    while True:
        snapshot = reader.read()
        rows = [row for address, row in snapshot.rows.items() if address in allowed and row["state"] != "retired"]
        require(bool(rows), "quota_activation_allocation_missing")
        if all(row["state"] == "active" and row["needs_reconcile"] == 0 for row in rows):
            return snapshot
        require(time.monotonic() < deadline, "quota_activation_timeout")
        time.sleep(3)


def execute(args: argparse.Namespace) -> tuple[str, ...]:
    """Run existing workflow phases without granting any terminal escrow capability."""
    return _execute(args)


def prepare_escrow(args: argparse.Namespace) -> tuple[str, ...]:
    """Dormant prepare-only D1 durability seam, before any artifact upload.

    A reviewed wrapper may call this with prepare, empty original/artifact IDs,
    and the fixed retained-key generation. No CLI or workflow activates it.
    The exact authenticated ciphertext must be sealed in D1 before the upload
    file becomes available. This never attaches an artifact, arms a campaign,
    allocates/retires aliases, writes a receipt or purges ciphertext. Failure
    preserves any provider-side writing/sealed record for explicit recovery.
    """
    require(args.mode == "prepare" and args.artifact_id == "" and args.prior_run == "",
            "quota_escrow_prepare_only")
    return _execute(args, durable_prepare=True)


def _publish_prepared(blob: bytes, run: str, secret: str, generation: str,
                      client: escrow.Escrow | None) -> None:
    """Expose upload bytes only after optional independently authenticated D1 seal.

    Existing file-only preparation retains its contract. Durable preparation
    cannot silently fall back to that mode after a write/readback failure.
    Neither provider records nor partial local files are deleted on failure.
    """
    destination = prepared_file(run)
    require(not destination.parent.exists() and not destination.parent.is_symlink(),
            "quota_prepared_path_exists")
    if client is not None:
        sealed = client.put(blob, secret, run, generation)
        retained, actual = client.read(run, secret, generation)
        require(retained == sealed and retained["state"] == "sealed"
                and retained["artifact_id"] is None and retained["armed_at"] is None
                and retained["cleanup_receipt_sha"] is None and actual == blob,
                "quota_escrow_preparation_unverified")
    destination.parent.mkdir(exist_ok=False)
    with destination.open("xb") as output:
        require(output.write(blob) == len(blob), "quota_prepared_file_incomplete")


def finalize_recovery(args: argparse.Namespace) -> tuple[str, ...]:
    """Dormant concrete read-only recovery/teardown coordinator; no CLI/workflow entry.

    Reuse actual admission and native recovery, never a caller success token.
    Only after every check and local teardown succeeds may private operations
    receipt/purge run. Existing execute/main never activate this source seam.
    Original immutable artifact remains mandatory; expiry fallback is not wired.
    """
    require(args.mode == "recover", "quota_terminal_recovery_only")
    return _execute(args,terminal=True)


def finalize_escrow_recovery(args: argparse.Namespace) -> tuple[str, ...]:
    """Dormant explicit D1-only recovery; verify receipt while retaining ALL ciphertext.

    This deliberate transport is never an artifact-error fallback. It cannot
    prepare/campaign, download the original artifact, purge chunks or replace
    missing original GitHub run provenance. There is no CLI/workflow entrypoint.
    """
    require(args.mode == "recover" and args.artifact_id == "", "quota_escrow_recovery_only")
    return _execute(args,terminal=True,transport="escrow")


def _execute(args: argparse.Namespace, *, terminal: bool = False, transport: str = "artifact",
             durable_prepare: bool = False) -> tuple[str, ...]:
    """Compose concrete observed checks; terminal enables work, never asserts success."""
    require(not terminal or args.mode == "recover", "quota_terminal_recovery_only")
    require(transport == "artifact" or transport == "escrow" and terminal and args.mode == "recover",
            "quota_transport_unreviewed")
    require(not durable_prepare or args.mode == "prepare" and not terminal
            and transport == "artifact" and args.artifact_id == "" and args.prior_run == "",
            "quota_escrow_prepare_only")
    values = environment(args.mode)
    require(not durable_prepare or values["AMAIL_TEN_ADDRESS_KEY_GENERATION"] == ESCROW_GENERATION,
            "escrow_generation_unsupported")
    sha = checkout()
    current_run = os.environ["GITHUB_RUN_ID"]
    token = values["GITHUB_TOKEN"]
    dispatch_record(current_run, token, checkout_sha=sha)
    provenance.successful_source(args.source_run, sha, token)
    original_run = args.prior_run if args.mode == "recover" else current_run
    manifest.coordinates(original_run, "1")
    secret = values["AMAIL_TEN_ADDRESS_RECOVERY_KEY"]
    generation = values["AMAIL_TEN_ADDRESS_KEY_GENERATION"]
    now = datetime.now(timezone.utc)
    artifacts = artifact.Artifacts(token)
    plan, downloaded = None, None
    terminal_client = None
    if args.mode != "prepare":
        original = dispatch_record(original_run, token)
        if transport == "escrow":
            require(original_run != current_run and original.get("status") == "completed",
                    "escrow_original_invocation_unsettled")
            require(generation == ESCROW_GENERATION, "escrow_generation_unsupported")
            terminal_client = escrow.Escrow(values["CLOUDFLARE_ACCOUNT_ID"],values["CLOUDFLARE_API_TOKEN"])
            _,downloaded = terminal_client.read(original_run,secret,generation)
        else:
            downloaded = artifacts.content(args.artifact_id, original_run, original["head_sha"], now, recovery=True)
        plan = manifest.open_manifest(downloaded, secret, original_run, generation)
        require(plan["checkout"] == original["head_sha"], "recovery_original_source_mismatch")
    if terminal:
        if terminal_client is None:
            terminal_client = escrow.Escrow(values["CLOUDFLARE_ACCOUNT_ID"],values["CLOUDFLARE_API_TOKEN"])
        terminal_client.schema()
        _,binding = escrow.binding(downloaded,secret,original_run,generation)
        retained = terminal_client._same(terminal_client.parent(original_run),binding)
        require(transport == "escrow" or retained["artifact_id"] == args.artifact_id,
                "escrow_artifact_unverified")
        if retained["state"] == "cleanup_verified":
            # A prior lost receipt/purge ACK is metadata, not external evidence.
            # We still run the complete fresh native read-only recovery below.
            terminal_client._terminal(retained,binding)
        else:
            require(terminal_client.read(original_run,secret,generation)[1] == downloaded,
                    "escrow_envelope_mismatch")
    allowed = tuple(manifest.candidates(secret, original_run))
    resources = tuple(sorted(set(allowed) | {part.lower() + "@" + manifest.DOMAIN for part in manifest.submissions()}))
    reader = Readback(values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_ZONE_ID"],
                      values["CLOUDFLARE_API_TOKEN"], values["CF_EMAIL_ROUTING_TOKEN"], resources)
    services = provenance.Services(values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"],
                                   reader.sending_state, phase=args.mail_phase, queue_id=args.queue_id)
    pins = services.read()
    if plan is not None:
        require((plan["mail_version"], plan["provenance"]["identity_revision"], plan["provenance"]["login_revision"])
                == (pins.mail, pins.identity, pins.login), "recovery_service_pins_changed")
    # Full effective privacy is independent of immutable resource bindings.
    require(provenance.mail_pin.run(values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"],
                                    pins.mail, phase=args.mail_phase, queue_id=args.queue_id) == "match",
            "quota_effective_privacy_unverified")
    require(TEMP.resolve() == TEMP, "quota_temp_redirected")
    TEMP.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ten-address-hosted-", dir=TEMP)).resolve()
    try:
        binary = artifacts.binary(args.source_run, sha, work / "amail.exe", now)
        with native.native_account(binary, values["STAGING_E2E_USERNAME"], values["STAGING_E2E_PASSWORD"],
                                   values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"], allowed) as (owner, cli):
            def pin() -> str:
                """Reject version, binding or global-hold drift before each observation."""
                services.check(pins)
                return pins.mail
            def forbidden(*args):
                """Prepare/recovery never receive an add capability, even accidentally."""
                raise manifest.ContractFailure("quota_mutation_capability_unavailable")
            adapter = hosted.Adapter(reader.read, cli.owned, forbidden if args.mode != "campaign" else cli.add,
                                     forbidden if args.mode != "campaign" else cli.delete,
                                     lambda: activation(reader, allowed), pin, reader.storage_empty)
            evidence = hosted.Evidence("workflow_dispatch", manifest.BRANCH, manifest.REPOSITORY, "staging",
                                       "RUN_STAGING_TEN_ADDRESSES", original_run, "1", sha, sha, "success",
                                       owner, values["STAGING_E2E_USERNAME"], values["STAGING_E2E_USERNAME"], owner,
                                       pins.mail, pins.identity, pins.login,
                                       ("amail-mail-staging", "amail-inbound-staging", manifest.DOMAIN, manifest.ISSUER), "held")
            if args.mode == "prepare":
                _, blob = hosted.prepare(evidence, secret, generation, int(now.timestamp() * 1000), adapter)
                client = (escrow.Escrow(values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"])
                          if durable_prepare else None)
                _publish_prepared(blob, original_run, secret, generation, client)
                return (("ten_address_escrow_prepared",) if durable_prepare
                        else ("ten_address_recovery_prepared",))
            require(plan["owner_sub"] == owner and plan["provenance"]["verified_username"] == values["STAGING_E2E_USERNAME"],
                    "recovery_owner_mismatch")
            if args.mode == "recover":
                hosted.recover(plan, secret, generation, owner, adapter)
                require(provenance.mail_pin.run(values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"],
                                                pins.mail, phase=args.mail_phase, queue_id=args.queue_id) == "match",
                        "quota_effective_privacy_unverified")
                if not terminal:
                    return ("ten_address_recovery_verified",)
            else:
                require(plan["checkout"] == sha, "campaign_manifest_mismatch")
                local_path = prepared_file(original_run)
                require(local_path.resolve() == local_path and local_path.is_file() and not local_path.is_symlink(),
                        "campaign_local_manifest_unverified")
                local = local_path.read_bytes()
                labels = hosted.campaign(evidence, local, downloaded, args.artifact_id, secret, generation,
                                         int(datetime.now(timezone.utc).timestamp() * 1000), adapter)
                require(provenance.mail_pin.run(values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"],
                                                pins.mail, phase=args.mail_phase, queue_id=args.queue_id) == "match",
                        "quota_effective_privacy_unverified")
                return labels
    finally:
        require(TEMP in work.parents and work.name.startswith("ten-address-hosted-"), "quota_cleanup_path_unverified")
        try:
            shutil.rmtree(work)
        except Exception:
            raise manifest.ContractFailure("quota_local_cleanup_required") from None
    # Reaching this point proves both native context teardown and owned binary
    # scratch removal returned normally. Any exception/cancellation bypasses it.
    require(terminal and terminal_client is not None, "quota_terminal_recovery_unverified")
    services.check(pins)
    # Final cleanup legitimately retains owned settled retired tombstones.
    # Reuse the complete read-only cleanup oracle, not active-prefix semantics.
    manifest.reconcile(plan,reader.read,None,owner,secret,original_run,generation)
    require(reader.storage_empty(tuple(plan["resources"])) is True, "unexpected_message_storage")
    require(provenance.mail_pin.run(values["CLOUDFLARE_ACCOUNT_ID"],values["CLOUDFLARE_API_TOKEN"],
                                    pins.mail,phase=args.mail_phase,queue_id=args.queue_id) == "match",
            "quota_effective_privacy_unverified")
    row = terminal_client.parent(original_run)
    require(row is not None, "escrow_parent_missing")
    if row["state"] != "cleanup_verified":
        row = terminal_client._finalize(original_run,secret,generation,current_run,sha,downloaded)
    if transport == "escrow":
        # A prior terminal status cannot prove ciphertext still exists after
        # native checks. Reauthenticate every chunk and immutable receipt now,
        # for both new and resumed terminal states, before claiming retention.
        final,actual = terminal_client.read(original_run,secret,generation)
        _,binding = escrow.binding(downloaded,secret,original_run,generation)
        terminal_client._terminal(final,binding)
        require(actual == downloaded and final == row, "escrow_terminal_retention_unverified")
        # Expiry recovery must not create a destructive partial-envelope window.
        # Atomic all-chunk purge is a separate reviewed/provider-tested contract.
        return ("ten_address_escrow_receipt_retained",)
    terminal_client._purge(original_run,secret,generation,downloaded)
    return ("ten_address_terminal_receipt_verified",)


def main() -> int:
    """Emit only fixed source-owned outcome labels; no private provider/CLI exception text."""
    parser = argparse.ArgumentParser(description="Guarded hosted staging quota acceptance")
    parser.add_argument("mode", choices=tuple(CONFIRMS))
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--artifact-id", default="")
    parser.add_argument("--prior-run", default="")
    parser.add_argument("--mail-phase", choices=("pre-queue", "queue-api"), default="pre-queue")
    parser.add_argument("--queue-id", default="")
    args = parser.parse_args()
    try:
        for label in execute(args):
            print(label)
        return 0
    except manifest.ContractFailure as error:
        # This exact public result is source-owned and contains no observed value.
        label = ("ten_address_recovery_manual_intervention_required"
                 if str(error) == "recovery_manual_intervention_required"
                 else "ten_address_acceptance_unverified")
        print(label, file=sys.stderr)
        return 1
    except Exception:
        print("ten_address_acceptance_unverified", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
