"""Read-only source and three-service admission for a future quota workflow.

No executable entry point or caller-supplied pass flag exists. All identities,
source runs and serving versions are independently read from provider control
planes; private responses remain in memory. No account, alias, send, deploy or
local token-store capability is granted by this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import sys
from typing import Callable

import staging_ten_address_manifest as manifest
from staging_second_principal import json_result, request
from staging_worker_created_r2 import github_json

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))
import pin_staging_mail as mail_pin

require = manifest.require
SHA = re.compile(r"[a-f0-9]{40}\Z")
UUID = re.compile(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}\Z")
SOURCE_WORKFLOW = ".github/workflows/ci.yml"
JOBS = ("CLI (ubuntu-latest)", "CLI (windows-latest)", "CLI (macos-latest)",
        "Rust Worker (Wasm)", "Astro release site", "Infrastructure probe unit tests")
IDENTITY = "moesegfault-identity-staging"
LOGIN = "moesegfault-login-staging"
IDENTITY_DB = "c4042bd4-bb4a-4cf7-aa7f-04cf1a5d6ad9"
IDENTITY_FIXED = {
    "ENVIRONMENT": "staging", "ISSUER": manifest.ISSUER,
    "LOGIN_ORIGIN": "https://login-staging.moesegfault.dev",
    "ACCOUNT_ORIGIN": "https://account-staging.moesegfault.dev",
    "AVATAR_PUBLIC_ORIGIN": "https://avatars-staging.moesegfault.dev",
    "OAUTH_ENABLED": "true", "WEBAUTHN_RP_ID": "login-staging.moesegfault.dev",
}


def successful_source(run: str, checkout: str, token: str,
                      *, read: Callable = github_json) -> None:
    """Verify all six actual source jobs and the real encryption step at exact SHA."""
    manifest.coordinates(run, "1")
    require(isinstance(checkout, str) and SHA.fullmatch(checkout) is not None
            and isinstance(token, str) and bool(token), "source_capability_invalid")
    base = f"/repos/{manifest.REPOSITORY}/actions/runs/{run}/attempts/1"
    try:
        result, listing = read(base, token), read(base + "/jobs?per_page=100", token)
    except Exception:
        raise manifest.ContractFailure("source_metadata_unverified") from None
    require(isinstance(result, dict) and result.get("id") == int(run) and result.get("run_attempt") == 1
            and result.get("event") == "push" and result.get("status") == "completed"
            and result.get("conclusion") == "success" and result.get("head_sha") == checkout
            and result.get("head_branch") == manifest.BRANCH.removeprefix("refs/heads/")
            and result.get("path") in (SOURCE_WORKFLOW, SOURCE_WORKFLOW + "@" + manifest.BRANCH)
            and isinstance(result.get("repository"), dict)
            and result["repository"].get("full_name") == manifest.REPOSITORY,
            "source_metadata_unverified")
    require(isinstance(listing, dict) and type(listing.get("total_count")) is int
            and 0 <= listing["total_count"] <= 100 and isinstance(listing.get("jobs"), list)
            and len(listing["jobs"]) == listing["total_count"]
            and all(isinstance(job, dict) for job in listing["jobs"]), "source_jobs_incomplete")
    for name in JOBS:
        matches = [job for job in listing["jobs"] if isinstance(job, dict) and job.get("name") == name]
        require(len(matches) == 1, "source_job_unverified")
        job = matches[0]
        require(job.get("run_id") == int(run) and job.get("head_sha") == checkout
                and job.get("status") == "completed" and job.get("conclusion") == "success",
                "source_job_unverified")
    infra = next(job for job in listing["jobs"] if job.get("name") == JOBS[-1])
    steps = infra.get("steps")
    require(isinstance(steps, list), "source_crypto_unverified")
    crypto = [step for step in steps if isinstance(step, dict)
              and step.get("name") == "Test real encrypted quota recovery envelopes"]
    require(len(crypto) == 1 and crypto[0].get("status") == "completed"
            and crypto[0].get("conclusion") == "success", "source_crypto_unverified")


def binding_inventory(version: dict, expected: str) -> dict[str, dict]:
    """Require complete version-scoped binding inventory with no duplicate names."""
    require(isinstance(version, dict) and version.get("id") == expected
            and isinstance(version.get("resources"), dict), "service_bindings_unverified")
    values = version["resources"].get("bindings")
    if isinstance(values, dict) and set(values) == {"result"}:
        values = values["result"]
    require(isinstance(values, list) and all(isinstance(value, dict)
            and isinstance(value.get("name"), str) and bool(value["name"]) for value in values),
            "service_bindings_unverified")
    result = {value["name"]: value for value in values}
    require(len(result) == len(values), "service_bindings_unverified")
    return result


def identity_bindings(version: dict, expected: str) -> None:
    """Reject foreign persistent resources or protocol-critical origin/issuer drift.

    Current public-key/noncritical scalar vars and secret binding names remain
    version-bound without reprinting or pinning a key rotation in amail policy.
    Any additional persistent/service/network binding kind fails closed.
    """
    values = binding_inventory(version, expected)
    persistent = {"DB": ("d1", "database_id", IDENTITY_DB),
                  "AUDIT_ARCHIVE": ("r2_bucket", "bucket_name", "moesegfault-identity-audit-staging"),
                  "AVATARS": ("r2_bucket", "bucket_name", "moesegfault-avatars-staging")}
    for name, (kind, field, target) in persistent.items():
        require(name in values and values[name].get("type") == kind
                and values[name].get(field) == target, "identity_bindings_unverified")
    for name, target in IDENTITY_FIXED.items():
        require(name in values and values[name].get("type") == "plain_text"
                and values[name].get("text") == target, "identity_bindings_unverified")
    require("EMAIL" in values and values["EMAIL"].get("type") == "send_email"
            and values["EMAIL"].get("allowed_sender_addresses") == ["identity@moesegfault.dev"],
            "identity_bindings_unverified")
    remainder = [value for name, value in values.items() if name not in persistent
                 and name not in IDENTITY_FIXED and name != "EMAIL"]
    require(all(value.get("type") in ("plain_text", "secret_text") for value in remainder),
            "identity_bindings_unverified")


@dataclass(frozen=True, repr=False)
class Pins:
    """Immutable provider serving version relation, retained only in sealed provenance."""

    mail: str
    identity: str
    login: str


class Services:
    """Read fixed staging services; no worker/resource selector comes from workflow inputs."""

    def __init__(self, account: str, token: str, hold: Callable[[], str], *, phase: str = "pre-queue",
                 queue_id: str = "", read: Callable | None = None):
        """Admit only reviewed Mail resource phase and bounded provider capability."""
        require(isinstance(account, str) and re.fullmatch(r"[a-f0-9]{32}", account) is not None
                and isinstance(token, str) and bool(token) and callable(hold), "service_capability_invalid")
        try:
            mail_pin.expected_bindings(phase, queue_id)
        except Exception:
            raise manifest.ContractFailure("service_phase_unreviewed") from None
        self.account, self._token, self._hold = account, token, hold
        self.phase, self.queue_id = phase, queue_id
        self._read = read or self._http

    def _http(self, worker: str, suffix: str) -> dict:
        """Read only fixed worker deployments/version JSON without redirected bearer use."""
        require(worker in (mail_pin.SCRIPT, IDENTITY, LOGIN)
                and (suffix == "deployments?per_page=1&page=1" or suffix.startswith("versions/")
                     and UUID.fullmatch(suffix.removeprefix("versions/")) is not None),
                "service_read_unreviewed")
        raw = request("GET", f"/accounts/{self.account}/workers/scripts/{worker}/{suffix}", self._token)
        value = json_result(raw)
        require(isinstance(value.get("result"), dict), "service_readback_unverified")
        return value["result"]

    def _one(self, worker: str) -> str:
        """Bracket actual version-scoped bindings with equal single-100% deployments."""
        first = mail_pin.serving_deployment(self._read(worker, "deployments?per_page=1&page=1"))
        require(first is not None, "service_serving_unverified")
        version = self._read(worker, "versions/" + first[1])
        if worker == mail_pin.SCRIPT:
            require(mail_pin.bindings_match(version, first[1], phase=self.phase, queue_id=self.queue_id),
                    "mail_bindings_unverified")
        elif worker == IDENTITY:
            identity_bindings(version, first[1])
        else:
            require(binding_inventory(version, first[1]) == {}, "login_bindings_unverified")
        require(mail_pin.serving_deployment(self._read(worker, "deployments?per_page=1&page=1")) == first,
                "service_serving_changed")
        return first[1]

    def check(self, expected: Pins) -> None:
        """Recheck held state and the same immutable revisions without refetching bindings.

        Version-scoped bindings were checked during initial read. Their exact
        immutable IDs cannot acquire different resources in place, so repeating
        all version payload GETs around forty CLI operations adds latency, not
        another independent invariant. Mutable capture settings remain a separate
        explicit privacy check in the wrapper before and after the campaign.
        """
        require(isinstance(expected, Pins) and all(isinstance(value, str)
                and UUID.fullmatch(value) is not None for value in vars(expected).values()),
                "service_expected_pins_unverified")
        try:
            require(self._hold() == "held", "global_sending_not_held")
            for worker, version in zip((mail_pin.SCRIPT, IDENTITY, LOGIN),
                                       (expected.mail, expected.identity, expected.login)):
                serving = mail_pin.serving_deployment(self._read(worker, "deployments?per_page=1&page=1"))
                require(serving is not None and serving[1] == version, "service_relation_changed")
            require(self._hold() == "held", "global_sending_not_held")
        except manifest.ContractFailure:
            raise
        except Exception:
            raise manifest.ContractFailure("service_provenance_unverified") from None

    def read(self) -> Pins:
        """Require actual explicit hold and two equal three-service serving relations."""
        try:
            require(self._hold() == "held", "global_sending_not_held")
            first = Pins(*(self._one(worker) for worker in (mail_pin.SCRIPT, IDENTITY, LOGIN)))
            second = Pins(*(self._one(worker) for worker in (mail_pin.SCRIPT, IDENTITY, LOGIN)))
            require(first == second, "service_relation_changed")
            require(self._hold() == "held", "global_sending_not_held")
            return second
        except manifest.ContractFailure:
            raise
        except Exception:
            raise manifest.ContractFailure("service_provenance_unverified") from None
