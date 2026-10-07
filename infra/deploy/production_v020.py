"""Promote the USD release from the exact accepted v0.1.2 production epoch.

Keep the historical upgrade controller frozen. This lane replaces the compatible
typed trace sink first, then applies additive schema and replaces API/maintenance.
It never provisions resources, changes sending policy, or retries ambiguous writes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import urllib.request

import production_upgrade as prior
from pin_staging_mail import UUID, expected_bindings
from tested_worker_artifact import require_artifact
from worker_deploy_result import submit, DeploymentFailure

ROOT = prior.ROOT
ORIGIN_RUN = "37104468990"
ORIGIN_SOURCE = "805ac273fc00e85f773b9249587581a0dc274ce2"
# Source-owned receipt artifact11267970678; never learn predecessor pins from latest.
PINS = {
    "amail-mail": ("4eee1ec6-8f70-47ee-98d8-e7ba4feb3f19", "50bd330d-2f9b-4102-8c8e-9bbaada927fe"),
    "amail-mail-maintenance": ("411db6fb-3028-44bd-98db-cb354bfbe922", "293d4049-c56a-40ee-8bc3-ef345a7a4eb7"),
    "amail-trace-sink": prior.PINS["amail-trace-sink"],
}
ROLES = {"api": "amail-mail", "maintenance": "amail-mail-maintenance", "sink": "amail-trace-sink"}
CONFIGS = {**prior.retained.CONFIGS, "sink": "workers/trace-sink/wrangler.toml"}
OWNERSHIP = "SELECT address,owner_iss,owner_sub,created_at FROM addresses ORDER BY address LIMIT 1000"


def unchanged_adapters() -> None:
    """Retain accepted SMTP/lifecycle code; package version changes are immaterial."""
    for folder in ("workers/mail-ingress", "workers/mail-events"):
        result = subprocess.run(["git", "diff", "--name-only", ORIGIN_SOURCE, "HEAD", "--", folder],
                                cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        if result.stdout.splitlines() not in ([], [folder + "/Cargo.toml"]):
            raise ValueError("production_retained_source_changed")
        old = subprocess.check_output(["git", "show", ORIGIN_SOURCE + ":" + folder + "/Cargo.toml"], cwd=ROOT, text=True)
        old, current = tomllib.loads(old), tomllib.loads((ROOT / folder / "Cargo.toml").read_text())
        old["package"].pop("version", None)
        current["package"].pop("version", None)
        if old != current:
            raise ValueError("production_retained_source_changed")


def select(pins: dict) -> None:
    """Use fixed predecessor or successful same-run capture UUIDs, not inventory adoption."""
    keys = {"amail-mail": "AMAIL_EXPECTED_WORKER_VERSION", "amail-mail-maintenance": "AMAIL_EXPECTED_MAINTENANCE_VERSION",
            "amail-trace-sink": "AMAIL_EXPECTED_TRACE_SINK_VERSION"}
    for script, key in keys.items():
        if UUID.fullmatch(pins[script][1]) is None:
            raise ValueError("production_upgrade_pins_unverified")
        os.environ[key] = pins[script][1]
    os.environ.update(AMAIL_TRACE_QUEUE_ID=prior.QUEUE, AMAIL_TRACE_DLQ_ID=prior.DLQ, AMAIL_TRACE_TOPOLOGY="api-scheduled")


def observe(pins: dict, policy: dict | None = None) -> tuple[dict, dict, object]:
    """Bracket exact capabilities, sending policy, retained routes and immutable roles."""
    unchanged_adapters()
    prior.retained.check_configs(prior.SCOPE)
    select(pins)
    actual_policy = prior.graph.global_policy()
    if policy is not None and actual_policy != policy:
        raise ValueError("production_upgrade_policy_changed")
    expected = os.getenv("AMAIL_UPGRADE_POLICY_FINGERPRINT", "")
    if expected and expected != prior.digest(actual_policy):
        raise ValueError("production_upgrade_policy_changed")
    result = prior.graph.verify("production", "active", expected_policy=actual_policy,
                                allow_production_v012_predecessor=True)
    for script, (deployment, version) in pins.items():
        observed = result["pins"][script]
        if observed[1] != version or deployment is not None and observed[0] != deployment:
            raise ValueError("production_upgrade_predecessor_changed")
    provider = prior.FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    prior.retained.verify_sending_privacy(provider)
    external = prior.retained_snapshot(provider)
    expected = os.getenv("AMAIL_UPGRADE_EXTERNAL_FINGERPRINT", "")
    if expected and expected != prior.digest(external):
        raise ValueError("production_upgrade_graph_changed")
    if prior.retained_snapshot(provider) != external or prior.graph.global_policy() != actual_policy:
        raise ValueError("production_upgrade_graph_changed")
    if prior.graph.serving(provider.account, provider.token, {name: pin[1] for name, pin in pins.items()}) != result["pins"]:
        raise ValueError("production_upgrade_graph_changed")
    return result, actual_policy, provider


def billing_ready() -> None:
    """Read both production service boundaries without creating consent or usage."""
    key = os.environ.get("BILLING_SERVICE_KEY", "")
    if not 32 <= len(key) <= 256:
        raise ValueError("production_billing_unverified")
    for service in ("billing", "subscribe"):
        request = urllib.request.Request(f"https://{service}.moesegfault.dev/v1/service/amail/trace-query",
            data=b'{"trace_id":"11111111111111111111111111111111"}', method="POST",
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "User-Agent": "amail-production-witness/0.2.0"})
        # No credential redirects, provider error prose, or unbounded response body.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            """Refuse moving a production service capability to another URL."""
            def redirect_request(self, *args):
                """A redirect is never a valid service receipt."""
                return None
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("production_billing_unverified")
        data = json.loads(body)
        if data.get("schema_version") != 1 or not isinstance(data.get("spans"), list):
            raise ValueError("production_billing_unverified")


def query(provider, sql: str) -> list:
    """Reuse the bounded private production SELECT reader; never emit user rows."""
    return prior.readback.query(provider, "accounts/" + provider.account, prior.SCOPE, sql)


def ownership(provider) -> dict:
    """Snapshot ownership only, excluding mail content and concurrently mutable state."""
    rows = query(provider, OWNERSHIP)
    if len(rows) >= 1000:
        raise ValueError("production_ownership_scope_exceeded")
    return {row["address"]: row for row in rows}


def migrate(provider) -> dict:
    """Apply forward-only SQL and verify every original address's ownership survives."""
    before = ownership(provider)
    prior.journal("migration", "intent")
    result = subprocess.run(["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"],
        cwd=ROOT / "crates/mail-worker", capture_output=True, text=True, timeout=600, check=False)
    if result.returncode or len(result.stdout) + len(result.stderr) > 1048576:
        raise ValueError("production_upgrade_migration_unverified")
    prior.journal("migration", "observed")
    after = ownership(provider)
    if any(after.get(address) != row for address, row in before.items()):
        raise ValueError("production_ownership_changed")
    rows = query(provider, "SELECT count(*) AS owners,coalesce(sum(plan!='free' OR currency!='USD' OR overage_budget_micros!=0),0) AS invalid FROM resource_accounts")
    if len(rows) != 1 or rows[0]["invalid"] != 0:
        raise ValueError("production_free_migration_unverified")
    return {"preserved_addresses": len(before), "owners": rows[0]["owners"], "currency": "USD", "initial_budget_micros": 0}


def replace(role: str) -> str:
    """Submit one exact tested role, retaining recovery UUID and removing secret files."""
    component = "trace_sink" if role == "sink" else "mail_api"
    require_artifact(component)
    command = ["wrangler", "deploy", "--config", str(ROOT / CONFIGS[role])]
    secret = None
    prior.journal(role, "intent")
    try:
        if role != "sink":
            names = ["OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "BILLING_SERVICE_KEY"]
            if role == "api":
                names.append("INGRESS_SECRET")
            values = {name: os.environ.get(name, "") for name in names}
            if not all(values.values()):
                raise ValueError("production_secrets_missing")
            fd, path = tempfile.mkstemp(prefix="production-v020-", suffix=".json", dir=ROOT / ".temp")
            secret = Path(path)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                secret.chmod(0o600)
                json.dump(values, file)
            command.extend(["--secrets-file", str(secret)])
        version = submit(command, "production", component, cwd=ROOT)
    except DeploymentFailure as error:
        if error.version:
            prior.journal(role, "ambiguous_version_captured", version=error.version)
            prior.output(role + "_version", error.version)
        raise
    finally:
        if secret is not None:
            secret.unlink(missing_ok=True)
    prior.journal(role, "version_captured", version=version)
    prior.output(role + "_version", version)
    if role != "sink":
        provider = prior.FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
        expected = (expected_bindings("queue-api", prior.QUEUE, realm="production") if role == "api"
                    else prior.retained.maintenance.expected_bindings("production", prior.QUEUE, active=True))
        config = tomllib.loads((ROOT / CONFIGS[role]).read_text())
        prior.readback.capture_off(provider, ROLES[role], version, expected_bindings=expected,
            reviewed=config["observability"], record=lambda state, **facts: prior.journal(role + "_capture", state, **facts))
    return version


def run(mode: str) -> None:
    """Preserve source-owned graph/policy and advance only known successful submits."""
    prior.context(mode)
    pins = dict(PINS)
    if mode == "verify":
        for role, script in ROLES.items():
            pins[script] = (None, os.environ.get("AMAIL_UPGRADE_" + role.upper() + "_VERSION", ""))
    result, policy, provider = observe(pins)
    facts = {}
    if mode in ("preflight", "upgrade"):
        billing_ready()
    if mode == "upgrade":
        pins = result["pins"]
        pins[ROLES["sink"]] = (None, replace("sink"))
        result, _, provider = observe(pins, policy)
        pins = result["pins"]
        facts = migrate(provider)
        observe(pins, policy)
        for role in ("api", "maintenance"):
            pins[ROLES[role]] = (None, replace(role))
            result, _, provider = observe(pins, policy)
            pins = result["pins"]
    snapshot = {"schema": "production-v020/v1", "origin_run": ORIGIN_RUN,
        "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
        "graph": result, "policy_state": policy["state"], "policy_fingerprint": prior.digest(policy),
        "external_fingerprint": prior.digest(prior.retained_snapshot(provider)), "migration": facts}
    path = ROOT / ".temp/production-upgrade.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    for key, value in (("queue_id", prior.QUEUE), ("dlq_id", prior.DLQ),
                       ("sink_version", result["pins"][ROLES["sink"]][1]),
                       ("policy_fingerprint", snapshot["policy_fingerprint"]), ("external_fingerprint", snapshot["external_fingerprint"])):
        prior.output(key, value)


def main() -> int:
    """Emit a closed error code, never provider prose, private rows or credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "preflight", "upgrade", "verify"))
    args = parser.parse_args()
    try:
        run(args.mode)
    except Exception as error:
        known = prior.FAILURES | {"production_billing_unverified", "production_ownership_changed",
            "production_ownership_scope_exceeded", "production_free_migration_unverified", "production_secrets_missing"}
        reason = str(error) if isinstance(error, ValueError) and str(error) in known else prior.graph.failure_reason(error)
        print("production_v020=UNVERIFIED reason=" + reason)
        return 1
    print("production_v020=exact_graph_policy_and_ownership_preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
