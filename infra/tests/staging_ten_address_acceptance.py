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
    """Compose independently observed admission, immutable recovery and exact CLI cleanup."""
    values = environment(args.mode)
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
    if args.mode != "prepare":
        original = dispatch_record(original_run, token)
        downloaded = artifacts.content(args.artifact_id, original_run, original["head_sha"], now, recovery=True)
        plan = manifest.open_manifest(downloaded, secret, original_run, generation)
        require(plan["checkout"] == original["head_sha"], "recovery_original_source_mismatch")
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
                                     forbidden if args.mode == "prepare" else cli.delete,
                                     lambda: activation(reader, allowed), pin, reader.storage_empty)
            evidence = hosted.Evidence("workflow_dispatch", manifest.BRANCH, manifest.REPOSITORY, "staging",
                                       "RUN_STAGING_TEN_ADDRESSES", original_run, "1", sha, sha, "success",
                                       owner, values["STAGING_E2E_USERNAME"], values["STAGING_E2E_USERNAME"], owner,
                                       pins.mail, pins.identity, pins.login,
                                       ("amail-mail-staging", "amail-inbound-staging", manifest.DOMAIN, manifest.ISSUER), "held")
            if args.mode == "prepare":
                _, blob = hosted.prepare(evidence, secret, generation, int(now.timestamp() * 1000), adapter)
                destination = prepared_file(original_run)
                destination.parent.mkdir(exist_ok=False)
                with destination.open("xb") as output:
                    output.write(blob)
                return ("ten_address_recovery_prepared",)
            require(plan["owner_sub"] == owner and plan["provenance"]["verified_username"] == values["STAGING_E2E_USERNAME"],
                    "recovery_owner_mismatch")
            if args.mode == "recover":
                hosted.recover(plan, secret, generation, owner, adapter)
                require(provenance.mail_pin.run(values["CLOUDFLARE_ACCOUNT_ID"], values["CLOUDFLARE_API_TOKEN"],
                                                pins.mail, phase=args.mail_phase, queue_id=args.queue_id) == "match",
                        "quota_effective_privacy_unverified")
                return ("ten_address_recovery_verified",)
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
    except Exception:
        print("ten_address_acceptance_unverified", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
