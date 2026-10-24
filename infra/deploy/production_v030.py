"""Roll the accepted USD production graph forward without resetting user state.

The source-owned predecessor is completed run37660780530/receipt11501340995,
not either earlier interrupted v0.2 writer. Migrations precede dual-domain events,
maintenance, and finally the API. Retained sink/ingress and the original lifecycle
subscription stay exact; no pause, drain claim, resource creation or policy write.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from typing import Any

import check_staging_adapters as adapters
import production_upgrade as prior
import production_v020 as usd
from fresh_bootstrap_scope import FreshProvider
from pin_staging_mail import UUID
from tested_worker_artifact import require_artifact
from worker_deploy_result import DeploymentFailure

ROOT = prior.ROOT
ORIGIN_RUN = "37660780530"
ORIGIN_SOURCE = "1c1c891ef2c20d31dfd1aa3fe7b373617aba86bd"
ORIGIN_EXTERNAL = "798579ff67840af9a6508e474c9efd643acd66764825cad2cd441ae20d3f29e7"
PINS: dict[str, tuple[str | None, str]] = {
    "amail-mail": ("45e72a6e-aca8-4c79-aaa9-5d3cee3cc884", "8dc1268f-6947-404b-bb89-95c4f1e5cde9"),
    "amail-mail-maintenance": ("48992383-31d6-4e35-8cdd-0d6eb0268c81", "271e6d3f-9355-4804-b0c4-0d2426ad6c5a"),
    "amail-trace-sink": ("a3e92449-7853-4d82-81af-f7014f24f44a", "f401659a-d076-4c6a-bfe5-28d0e71698b1"),
}
EVENTS = prior.ADAPTER_PINS["amail-events"]["version"]
RECEIPT = ROOT / ".temp/production-v030.json"
FAILURES = frozenset({
    "production_v030_context_unverified", "production_v030_retained_source_changed",
    "production_v030_predecessor_changed", "production_v030_original_external_changed",
    "production_v030_policy_changed", "production_v030_retained_graph_changed",
    "production_v030_adapter_unverified", "production_v030_migration_unverified",
    "production_v030_ownership_changed", "production_v030_domain_unverified",
    "production_v030_dns_unverified", "production_v030_receipt_exists",
})


def context(mode: str) -> None:
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": prior.REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "AMAIL_PRODUCTION_ENVIRONMENT": "production", "GITHUB_RUN_ATTEMPT": "1",
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS"}
    confirmation = "INSPECT_PRODUCTION_V030" if mode == "inspect" else "RUN_PRODUCTION_V030"
    if (mode not in ("inspect", "upgrade")
            or any(os.getenv(key) != value for key, value in expected.items())
            or os.getenv("AMAIL_PRODUCTION_CONFIRM") != confirmation
            or re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", "")) is None
            or re.fullmatch(r"[1-9][0-9]{0,19}", os.getenv("GITHUB_RUN_ID", "")) is None):
        raise ValueError("production_v030_context_unverified")


def unchanged_retained() -> None:
    """Sink protocol and ingress code remain accepted; package labels do not redeploy them."""
    for folder in ("workers/mail-ingress", "workers/trace-sink", "crates/trace-schema"):
        changed = subprocess.run(["git", "diff", "--name-only", ORIGIN_SOURCE, "HEAD", "--", folder],
                                 cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        if changed.stdout.splitlines() not in ([], [folder + "/Cargo.toml"]):
            raise ValueError("production_v030_retained_source_changed")
        original = subprocess.check_output(["git", "show", f"{ORIGIN_SOURCE}:{folder}/Cargo.toml"],
                                           cwd=ROOT, text=True, timeout=30)
        old = tomllib.loads(original)
        current = tomllib.loads((ROOT / folder / "Cargo.toml").read_text(encoding="utf-8"))
        old["package"].pop("version", None)
        current["package"].pop("version", None)
        if old != current:
            raise ValueError("production_v030_retained_source_changed")


def select(pins: dict[str, tuple[str | None, str]]) -> None:
    for script, key in (("amail-mail", "AMAIL_EXPECTED_WORKER_VERSION"),
                        ("amail-mail-maintenance", "AMAIL_EXPECTED_MAINTENANCE_VERSION"),
                        ("amail-trace-sink", "AMAIL_EXPECTED_TRACE_SINK_VERSION")):
        if UUID.fullmatch(pins[script][1]) is None:
            raise ValueError("production_v030_predecessor_changed")
        os.environ[key] = pins[script][1]
    os.environ.update(AMAIL_TRACE_QUEUE_ID=prior.QUEUE, AMAIL_TRACE_DLQ_ID=prior.DLQ,
                      AMAIL_TRACE_TOPOLOGY="api-scheduled")


def adapter_snapshot(provider: FreshProvider, events: str) -> dict[str, dict[str, str]]:
    versions = {"mail_ingress": prior.ADAPTER_PINS["amail-inbound"]["version"], "mail_events": events}
    before = prior.retained.adapter_pins(provider, versions)
    for component, version in versions.items():
        script = prior.retained.ADAPTERS[component]
        _, expected = prior.retained.adapter_contract(component, prior.SCOPE)
        if component == "mail_events" and version == EVENTS:
            expected.pop("MAIL_TMP_DOMAIN", None)
        prior.retained.verify_adapter_version(provider, component, version, expected)
        def read(suffix: str) -> dict[str, Any]:
            return prior.graph.capture.readback(provider.account, provider.token, script, suffix)
        if (not prior.graph.capture.effective_api_settings(
                prior.graph.capture.worker_readback(provider.account, provider.token, script), script,
                read("settings"), read("script-settings"))
                or read("subdomain").get("enabled") is not False
                or read("subdomain").get("previews_enabled") is not False
                or not prior.retained.maintenance.schedules_match(read("schedules"))):
            raise ValueError("production_v030_adapter_unverified")
    adapters.private_surfaces(provider.account, provider.token, {"amail-inbound", "amail-events"})
    if prior.retained.adapter_pins(provider, versions) != before:
        raise ValueError("production_v030_adapter_unverified")
    if before["amail-inbound"] != prior.ADAPTER_PINS["amail-inbound"]:
        raise ValueError("production_v030_predecessor_changed")
    return before


def observe(provider: FreshProvider, pins: dict[str, tuple[str | None, str]], events: str,
            temporary: bool, *, policy: dict[str, Any] | None = None,
            retained: dict[str, Any] | None = None, original: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Separate invariant original paths from the explicitly replaced events component."""
    select(pins)
    actual_policy = prior.graph.global_policy()
    if policy is not None and actual_policy != policy:
        raise ValueError("production_v030_policy_changed")
    graph = prior.graph.verify("production", "active", expected_policy=actual_policy)
    for script, (deployment, version) in pins.items():
        actual = graph["pins"][script]
        if actual[1] != version or deployment is not None and actual[0] != deployment:
            raise ValueError("production_v030_predecessor_changed")
    cohort = adapter_snapshot(provider, events)
    lifecycle = adapters.lifecycle_snapshot(provider.account, provider.token, realm="production", temporary=temporary)
    forwards = prior.graph.direct_forward_snapshot("production", provider.account, provider.token)
    anchors = {"forwards": forwards, "subscription": lifecycle["subscription"],
               "ingress": cohort["amail-inbound"],
               "queues": {name: row["queue_id"] for name, row in lifecycle["queues"].items()}}
    if original and prior.digest({"adapters": cohort, "forwards": forwards,
                                  "subscription": [lifecycle["subscription"]]}) != ORIGIN_EXTERNAL:
        raise ValueError("production_v030_original_external_changed")
    if retained is not None and anchors != retained:
        raise ValueError("production_v030_retained_graph_changed")
    prior.retained.verify_sending_privacy(provider)
    if (prior.graph.global_policy() != actual_policy
            or adapters.lifecycle_snapshot(provider.account, provider.token, realm="production", temporary=temporary) != lifecycle
            or prior.graph.direct_forward_snapshot("production", provider.account, provider.token) != forwards
            or prior.graph.serving(provider.account, provider.token, {name: pin[1] for name, pin in pins.items()}) != graph["pins"]):
        raise ValueError("production_v030_retained_graph_changed")
    return {"graph": graph, "adapters": cohort}, actual_policy, anchors


def domain_ready() -> None:
    """Onboard only the separately approved temporary domain, then read authoritative DNS."""
    sys.path.insert(0, str(ROOT / "infra/provider"))
    import ensure_tmpaddr_staging as domains
    domains.authorize_apply(dict(os.environ), domains.Target.PRODUCTION)
    client = domains.Client(os.environ["CLOUDFLARE_API_TOKEN"])
    prior.journal("temporary_domain", "intent")
    try:
        domains.ensure_routing(client, client, True, domains.Target.PRODUCTION)
        domains.ensure_sending(client, True, domains.Target.PRODUCTION)
    except domains.ProvisionError as error:
        print("production_v030_domain=" + json.dumps(domains.inspection_failure(error), sort_keys=True))
        raise ValueError("production_v030_domain_unverified") from None
    prior.journal("temporary_domain", "observed")
    for domain in ("mail.moesegfault.dev", "tmpaddr.moesegfault.dev"):
        result = subprocess.run([sys.executable, str(ROOT / "infra/dns/verify_sending.py")], cwd=ROOT,
                                env={**os.environ, "MAIL_SENDING_DOMAIN": domain}, capture_output=True,
                                text=True, timeout=240, check=False)
        if result.returncode:
            raise ValueError("production_v030_dns_unverified")


def migrate(provider: FreshProvider) -> int:
    """Preserve original ownership; never assert/reset paid plans, budgets or usage."""
    expected = sorted(path.name for path in (ROOT / "crates/mail-worker/migrations").glob("*.sql"))
    applied = usd.DatabaseClient(provider.account, provider.token, "production").query(
        "SELECT name FROM d1_migrations ORDER BY id LIMIT 100").get("results")
    if (len(expected) != 17 or expected[-2:] != ["0016_profiles.sql", "0017_tmpaddr.sql"]
            or not isinstance(applied, list) or not 15 <= len(applied) <= 17
            or [row.get("name") for row in applied] != expected[:len(applied)]):
        raise ValueError("production_v030_migration_unverified")
    before = usd.ownership(provider)
    require_artifact("mail_api")
    prior.journal("migration", "intent")
    result = subprocess.run(["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"],
                            cwd=ROOT / "crates/mail-worker", capture_output=True, text=True, timeout=600, check=False)
    if result.returncode or len(result.stdout) + len(result.stderr) > 1_048_576:
        raise ValueError("production_v030_migration_unverified")
    prior.journal("migration", "observed")
    after = usd.ownership(provider)
    if any(after.get(address) != row for address, row in before.items()):
        raise ValueError("production_v030_ownership_changed")
    return len(before)


def replace_events(provider: FreshProvider) -> str:
    require_artifact("mail_events")
    prior.journal("mail_events", "intent")
    try:
        version = prior.retained.deploy_adapter("mail_events")
    except DeploymentFailure as error:
        if error.version:
            prior.journal("mail_events", "ambiguous_version_captured", version=error.version)
        raise
    prior.journal("mail_events", "version_captured", version=version)
    def record(state: str, **facts: object) -> None:
        prior.journal("mail_events_capture", state, **facts)

    prior.retained.correct_adapter_capture(provider, prior.SCOPE, "mail_events", version, record)
    return version


def run(mode: str) -> None:
    context(mode)
    if any(path.exists() for path in (RECEIPT, RECEIPT.parent / "production-upgrade-partial.jsonl",
                                      RECEIPT.parent / "production-upgrade-capture.jsonl")):
        raise ValueError("production_v030_receipt_exists")
    unchanged_retained()
    prior.retained.check_configs(prior.SCOPE)
    provider = FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    # Preserve this provider's verified catalog through all immutable-version reads.
    prior.readback.complete(provider, f"accounts/{provider.account}/queues", "queue_id", 100)
    pins = dict(PINS)
    result, policy, anchors = observe(provider, pins, EVENTS, False, original=True)
    preserved = 0
    if mode == "upgrade":
        require_artifact("mail_api")
        usd.billing_ready()
        domain_ready()
        observe(provider, pins, EVENTS, False, policy=policy, retained=anchors)
        preserved = migrate(provider)
        observe(provider, pins, EVENTS, False, policy=policy, retained=anchors)
        events = replace_events(provider)
        prior.journal("temporary_subscription", "intent")
        from ensure_email_events import ensure_subscription
        ensure_subscription("amail-sending-events", "amail-tmpaddr-lifecycle", "tmpaddr.moesegfault.dev")
        prior.journal("temporary_subscription", "observed")
        observe(provider, pins, events, True, policy=policy, retained=anchors)
        pins["amail-mail-maintenance"] = (None, usd.replace(provider, "maintenance"))
        observe(provider, pins, events, True, policy=policy, retained=anchors)
        pins["amail-mail"] = (None, usd.replace(provider, "api"))
        result, _, _ = observe(provider, pins, events, True, policy=policy, retained=anchors)
    snapshot = {"schema": "production-v030/v1", "origin_run": ORIGIN_RUN,
                "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                **result, "policy_state": policy["state"], "policy_fingerprint": prior.digest(policy),
                "retained_fingerprint": prior.digest(anchors), "preserved_addresses": preserved,
                "temporary_lifecycle": mode == "upgrade", "old_http_drain": "NOT_CLAIMED"}
    RECEIPT.parent.mkdir(exist_ok=True)
    with RECEIPT.open("x", encoding="utf-8") as file:
        json.dump(snapshot, file, sort_keys=True)
        file.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "upgrade"))
    args = parser.parse_args()
    try:
        run(args.mode)
    except Exception as error:
        known = FAILURES | prior.FAILURES | prior.retained.ERROR_REASONS | adapters.FAILURE_REASONS
        reason = str(error) if isinstance(error, ValueError) and str(error) in known else "unknown"
        print(f"production_v030=UNVERIFIED reason={reason} class={type(error).__name__}")
        return 1
    print("production_v030=exact_graph_policy_and_ownership_preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
