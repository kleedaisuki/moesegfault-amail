"""Replace only the established production API/maintenance, preserving live policy.

The reviewed predecessor is successful online run 36938451911, not a name/latest
inventory adoption. Retained adapters/sink/queues are never deployed or created.
Usage: protected CI runs ``inspect``, or ``preflight`` then ``upgrade`` and ``verify``.
Every ambiguous write stops without retry; an installed partial upgrade needs
explicit owned reconciliation, never another automatic invocation of this lane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tomllib

import check_mail_split_graph as graph
import complete_fresh_mail as retained
import fresh_bootstrap_readback as readback
from fresh_bootstrap_contract import Epoch, Scope, REPO
from fresh_bootstrap_scope import FreshProvider
from fresh_mail_bootstrap import submit_once
from check_mail_maintenance import maintenance_config
from pin_staging_mail import UUID, expected_bindings
from tested_worker_artifact import require_artifact
from worker_deploy_result import DeploymentFailure

ROOT = Path(__file__).resolve().parents[2]
ORIGIN_RUN = "36938451911"
ORIGIN_SOURCE = "45f8dc41c82866ce47877601340113e28e8fb99d"
# Original successful artifact 11199880674/receipt.json SHA256:
# f1fa430eb66c13094b7d204ba13afcfb321b7147e15db752eac4ceafac39d18b.
PINS = {
    "amail-mail": ("c4cb98a5-0d4e-48a4-a3f3-ef1db963881c", "a2eba957-43e1-4ba1-af67-44d368f03b6f"),
    "amail-mail-maintenance": ("4aae750f-96fe-4be6-97bc-8e82a3c75cf5", "125a0063-d7ff-44ea-859e-cd709a0ac066"),
    "amail-trace-sink": ("e4c4cc87-48e7-44d3-9cb0-390764e2ee34", "d372b6f0-42ed-4536-b7ee-15273b50d6a3"),
}
ADAPTER_PINS = {
    "amail-inbound": {"deployment": "3192c6ef-7b49-40e7-b244-a8d9f9759028", "version": "5c296407-5048-43b3-aad6-ac106676e7f2"},
    "amail-events": {"deployment": "33145303-b22e-43c5-98bf-ca82e013b9e5", "version": "7fa0c130-d4bc-45c4-8c22-c16293821df8"},
}
QUEUE, DLQ = "e7a80fba65b0471aa4a267527d83d2d3", "7eab75daab9345e9ad6d0c1fa6f0e37c"
SCOPE = Scope(Epoch("87acaaa4ddbc2c22233fb5e5fc74f1778f86f3aa", "36912824752", 11188385927,
                    "ea687638b68ec1791c9754c92e0df9aad3105a909cf92163d1dc68140a4619ec", "1.98.1"),
              "d9be9bb4-5a73-4223-85d6-b04763e6f03b", "2026-10-01T19:20:25Z", "2026-10-01T19:20:26Z")
CONFIRM = "RUN_PRODUCTION_SPLIT_UPGRADE"
FAILURES = frozenset({"production_upgrade_context_unverified", "production_retained_source_changed",
                     "production_upgrade_pins_unverified", "production_retained_adapters_changed",
                     "production_retained_subscription_unverified", "production_upgrade_policy_changed",
                     "production_upgrade_predecessor_changed", "production_upgrade_graph_changed",
                     "production_upgrade_migration_unverified"})


def context(mode: str) -> None:
    """Require trusted main, protected environment, freeze and explicit read/write mode."""
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "AMAIL_PRODUCTION_ENVIRONMENT": "production",
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS"}
    confirmation = "INSPECT_PRODUCTION_V012" if mode == "inspect" else CONFIRM
    if (any(os.getenv(key) != value for key, value in expected.items())
            or os.getenv("AMAIL_PRODUCTION_GRAPH_CONFIRM") != confirmation
            or os.getenv("GITHUB_RUN_ATTEMPT") != "1"
            or re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", "")) is None
            or re.fullmatch(r"[1-9][0-9]{0,19}", os.getenv("GITHUB_RUN_ID", "")) is None):
        raise ValueError("production_upgrade_context_unverified")
    if mode in ("upgrade", "verify") and any(len(os.getenv(key, "")) != 64 for key in
            ("AMAIL_UPGRADE_POLICY_FINGERPRINT", "AMAIL_UPGRADE_EXTERNAL_FINGERPRINT")):
        raise ValueError("production_upgrade_context_unverified")


def digest(value: object) -> str:
    """Compare private policy/routing/subscription values without publishing them."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def unchanged_components() -> None:
    """Retained deployed code/config equals its owned source, except package version."""
    for folder in ("workers/mail-ingress", "workers/mail-events", "workers/trace-sink", "crates/trace-schema"):
        result = subprocess.run(["git", "diff", "--name-only", ORIGIN_SOURCE, "HEAD", "--", folder],
                                cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        if result.returncode or result.stdout.splitlines() not in ([], [folder + "/Cargo.toml"]):
            raise ValueError("production_retained_source_changed")
        if not result.stdout:
            continue
        original = subprocess.run(["git", "show", ORIGIN_SOURCE + ":" + folder + "/Cargo.toml"],
                                  cwd=ROOT, capture_output=True, text=True, timeout=30, check=False)
        if original.returncode:
            raise ValueError("production_retained_source_changed")
        old = tomllib.loads(original.stdout)
        current = tomllib.loads((ROOT / folder / "Cargo.toml").read_text())
        old["package"].pop("version", None)
        current["package"].pop("version", None)
        if old != current:
            raise ValueError("production_retained_source_changed")


def select_pins(api: str, maintenance: str) -> None:
    """Select source-owned predecessor or same-run submit UUIDs, never inventory names."""
    if any(UUID.fullmatch(value) is None for value in (api, maintenance)):
        raise ValueError("production_upgrade_pins_unverified")
    os.environ.update({"AMAIL_EXPECTED_WORKER_VERSION": api, "AMAIL_EXPECTED_MAINTENANCE_VERSION": maintenance,
                       "AMAIL_EXPECTED_TRACE_SINK_VERSION": PINS["amail-trace-sink"][1],
                       "AMAIL_TRACE_QUEUE_ID": QUEUE, "AMAIL_TRACE_DLQ_ID": DLQ,
                       "AMAIL_TRACE_TOPOLOGY": "api-scheduled"})


def retained_snapshot(provider: FreshProvider) -> dict:
    """Bracket owned adapters and private direct forwards/lifecycle subscription unchanged."""
    versions = {key: ADAPTER_PINS[name]["version"] for key, name in retained.ADAPTERS.items()}
    pins = retained.verify_adapters(provider, SCOPE, versions)
    if pins != ADAPTER_PINS:
        raise ValueError("production_retained_adapters_changed")
    from check_staging_adapters import forwarding
    from ensure_email_events import EVENTS, ZONE
    queues = retained.readback.complete(provider, f"accounts/{provider.account}/queues", "queue_id", 100)
    found = {name: [row for row in queues if row.get("queue_name") == name]
             for name in ("amail-sending-events", "amail-sending-events-dlq")}
    if any(len(rows) != 1 for rows in found.values()):
        raise ValueError("production_retained_subscription_unverified")
    main = found["amail-sending-events"][0]
    selected = {rows[0]["queue_id"] for rows in found.values()}
    subscriptions = forwarding.pages(forwarding.Client(token=provider.token, account=provider.account),
                                     f"/accounts/{provider.account}/event_subscriptions/subscriptions")
    seen, related = set(), []
    for row in subscriptions:
        identity, source, destination = row.get("id"), row.get("source"), row.get("destination")
        if (not isinstance(identity, str) or not 1 <= len(identity) <= 256 or identity in seen
                or not isinstance(source, dict) or not isinstance(destination, dict)):
            raise ValueError("production_retained_subscription_unverified")
        seen.add(identity)
        if (source.get("type") == "email.sending" and source.get("domain") == "mail.moesegfault.dev"
                or destination.get("queue_id") in selected):
            related.append(row)
    if len(related) != 1:
        raise ValueError("production_retained_subscription_unverified")
    subscription = related[0]
    source = subscription["source"]
    # API subscription rows have no top-level type discriminator. The documented
    # destination.type is queues.queue; neither an invented guard nor a broader
    # destination alias belongs in the production contract.
    if (subscription.get("name") != "amail-sending-lifecycle"
            or subscription.get("enabled") is not True
            or set(source) - {"type", "zone_id", "domain", "name"}
            or any(source.get(key) != value for key, value in
                   {"type": "email.sending", "zone_id": ZONE, "domain": "mail.moesegfault.dev"}.items())
            or "name" in source and (not isinstance(source["name"], str) or len(source["name"]) > 256)
            or subscription.get("destination") != {"type": "queues.queue", "queue_id": main["queue_id"]}
            or not isinstance(subscription.get("events"), list)
            or sorted(subscription["events"]) != sorted(EVENTS.split(","))):
        raise ValueError("production_retained_subscription_unverified")
    return {"adapters": pins, "forwards": graph.direct_forward_snapshot("production", provider.account, provider.token),
            "subscription": related}


def observe(*, original: bool) -> tuple[dict, dict, FreshProvider]:
    """Require live active graph and stable exact policy, retaining private values in memory."""
    unchanged_components()
    retained.check_configs(SCOPE)
    maintenance_config("production", active=True)
    if original:
        select_pins(PINS["amail-mail"][1], PINS["amail-mail-maintenance"][1])
    policy = graph.global_policy()
    policy_hash = os.getenv("AMAIL_UPGRADE_POLICY_FINGERPRINT", "")
    if policy_hash and policy_hash != digest(policy):
        raise ValueError("production_upgrade_policy_changed")
    result = graph.verify("production", "active", expected_policy=policy)
    if original and result["pins"] != PINS:
        raise ValueError("production_upgrade_predecessor_changed")
    if result["pins"]["amail-trace-sink"] != PINS["amail-trace-sink"]:
        raise ValueError("production_upgrade_predecessor_changed")
    provider = FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    retained.verify_sending_privacy(provider)
    before = retained_snapshot(provider)
    if (graph.global_policy() != policy or retained_snapshot(provider) != before
            or graph.serving(provider.account, provider.token, {name: pin[1] for name, pin in result["pins"].items()}) != result["pins"]):
        raise ValueError("production_upgrade_graph_changed")
    external_hash = os.getenv("AMAIL_UPGRADE_EXTERNAL_FINGERPRINT", "")
    if external_hash and external_hash != digest(before):
        raise ValueError("production_upgrade_graph_changed")
    return result, policy, provider


def output(key: str, value: str) -> None:
    """Emit only fixed labels, infrastructure UUIDs and non-content fingerprints."""
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as file:
        file.write(f"{key}={value}\n")


def journal(phase: str, state: str, **facts) -> None:
    """Fsync non-content intent/coordinates before writes; failed runs retain artifacts."""
    name = "capture" if phase.endswith("_capture") else "partial"
    path = ROOT / f".temp/production-upgrade-{name}.jsonl"
    path.parent.mkdir(exist_ok=True)
    row = {"schema": "production-upgrade-partial/v1", "source_sha": os.environ["GITHUB_SHA"],
           "run_id": os.environ["GITHUB_RUN_ID"], "run_attempt": 1, "phase": phase, "state": state, **facts}
    with path.open("a", encoding="utf-8") as file:
        path.chmod(0o600)
        file.write(json.dumps(row) + "\n")
        file.flush()
        os.fsync(file.fileno())


def replace(provider: FreshProvider, role: str) -> str:
    """Submit one exact tested role and preserve its UUID even if later verification fails."""
    require_artifact("mail_api")
    config = ROOT / retained.CONFIGS[role]
    journal(role, "intent")
    try:
        version = submit_once(role, config, SCOPE)
    except DeploymentFailure as error:
        if error.version:
            output(role + "_version", error.version)
            journal(role, "ambiguous_version_captured", version=error.version)
        raise
    output(role + "_version", version)
    journal(role, "version_captured", version=version)
    if role == "api":
        expected = expected_bindings("queue-api", QUEUE, realm="production")
    else:
        expected = retained.maintenance.expected_bindings("production", QUEUE, active=True)
    config_data = tomllib.loads(config.read_text())
    def record(state: str, **facts) -> None:
        """Retain exact settings-PATCH intent/outcome, never policy/contact values."""
        journal(role + "_capture", state, **facts)
    readback.capture_off(provider, "amail-mail" if role == "api" else "amail-mail-maintenance", version,
                         expected_bindings=expected, reviewed=config_data["observability"], record=record)
    return version


def run(mode: str) -> None:
    """Normal upgrade never provisions, enables sending, clears fences or changes cadence."""
    context(mode)
    original = mode != "verify"
    if mode == "verify":
        select_pins(os.getenv("AMAIL_UPGRADE_API_VERSION", ""), os.getenv("AMAIL_UPGRADE_MAINTENANCE_VERSION", ""))
    result, policy, provider = observe(original=original)
    if mode == "upgrade":
        require_artifact("mail_api")
        journal("migration", "intent")
        migration = subprocess.run(["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"],
                                   cwd=ROOT / "crates/mail-worker", capture_output=True, text=True, timeout=600, check=False)
        if migration.returncode or len(migration.stdout) + len(migration.stderr) > 1_048_576:
            raise ValueError("production_upgrade_migration_unverified")
        journal("migration", "observed")
        graph.verify("production", "active", expected_policy=policy)
        api = replace(provider, "api")
        select_pins(api, PINS["amail-mail-maintenance"][1])
        graph.verify("production", "active", expected_policy=policy)
        maintenance = replace(provider, "maintenance")
        select_pins(api, maintenance)
        result, _, _ = observe(original=False)
    snapshot = {"schema": "production-upgrade/v1", "origin_run": ORIGIN_RUN, "source_sha": os.getenv("GITHUB_SHA", ""),
                "run_id": os.getenv("GITHUB_RUN_ID", ""), "run_attempt": 1,
                "graph": result, "policy_state": policy["state"], "policy_fingerprint": digest(policy),
                "external_fingerprint": digest(retained_snapshot(provider))}
    path = ROOT / ".temp/production-upgrade.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2) + "\n")
    for key, value in (("queue_id", QUEUE), ("dlq_id", DLQ), ("sink_version", PINS["amail-trace-sink"][1]),
                       ("policy_fingerprint", snapshot["policy_fingerprint"]), ("external_fingerprint", snapshot["external_fingerprint"])):
        output(key, value)


def main() -> int:
    """Closed diagnostics never copy policy/contact values or provider prose."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "preflight", "upgrade", "verify"))
    args = parser.parse_args()
    try:
        run(args.mode)
    except Exception as error:
        reason = str(error) if isinstance(error, ValueError) and str(error) in FAILURES else graph.failure_reason(error)
        print(f"production_upgrade=UNVERIFIED reason={reason}")
        return 1
    print("production_upgrade=exact_active_graph_policy_preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
