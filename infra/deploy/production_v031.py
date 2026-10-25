"""Promote consent-gated semantic indexing from the completed v0.3.0 epoch.

Replace the backward-compatible sink, fail-closed API and paused maintenance
before applying 0018. Only the old scheduled cohort has a documented wall bound;
already-admitted old HTTP requests are not recalled. Never change sending policy,
create infrastructure, clear stored vectors, or replay an ambiguous submission.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Any
import urllib.error
import urllib.request

import production_v030 as legacy
from fresh_bootstrap_scope import FreshProvider
from mail_schema_contract import expected_schema, verify_schema
from tested_worker_artifact import require_artifact
from worker_deploy_result import DeploymentFailure, submit

prior, usd, ROOT = legacy.prior, legacy.usd, legacy.ROOT
ORIGIN_RUN = "40116604490"
ORIGIN_SOURCE = "d3d913d4bf59f48790a2753bc066033b4d8cf7a6"
ORIGIN_RETAINED = "cf8eb6019942a390c041a32d77fd7b420c8185322567cce5709290e545be4517"
PINS: dict[str, tuple[str | None, str]] = {
    "amail-mail": ("1b021326-4917-40f5-a1e2-09d7351a185e", "0592192f-5937-445c-8c26-73ab18799bba"),
    "amail-mail-maintenance": ("fb7ca5c0-af40-4479-b6e6-17880914e9e4", "ec73a333-0fba-497f-8f38-1fceffebc122"),
    "amail-trace-sink": ("a3e92449-7853-4d82-81af-f7014f24f44a", "f401659a-d076-4c6a-bfe5-28d0e71698b1"),
}
EVENTS = "c17d92ad-cbc4-4ff3-a250-724f17d5bc60"
RECEIPT = ROOT / ".temp/production-v031.json"
PROPAGATION_SECONDS, INVOCATION_SECONDS, MARGIN_SECONDS = 900, 900, 60
WINDOW_SECONDS = PROPAGATION_SECONDS + INVOCATION_SECONDS + MARGIN_SECONDS
FAILURES = frozenset({
    "production_v031_context_unverified", "production_v031_receipt_exists",
    "production_v031_retained_source_changed", "production_v031_predecessor_changed",
    "production_v031_retained_graph_changed", "production_v031_policy_changed",
    "production_v031_schema_unverified", "production_v031_ownership_changed",
    "production_v031_old_invocation_bound_unverified", "production_v031_secrets_missing",
    "production_v031_embeddings_unverified",
    "production_v031_health_unverified",
})


def context(mode: str) -> None:
    """Admit only a protected, first-attempt, explicit trusted-main invocation."""
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": prior.REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "AMAIL_PRODUCTION_ENVIRONMENT": "production", "GITHUB_RUN_ATTEMPT": "1",
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS"}
    confirmation = "INSPECT_PRODUCTION_V031" if mode == "inspect" else "RUN_PRODUCTION_V031"
    if (mode not in ("inspect", "upgrade")
            or any(os.getenv(key) != value for key, value in expected.items())
            or os.getenv("AMAIL_PRODUCTION_CONFIRM") != confirmation
            or re.fullmatch(r"[0-9a-f]{40}", os.getenv("GITHUB_SHA", "")) is None
            or re.fullmatch(r"[1-9][0-9]{0,19}", os.getenv("GITHUB_RUN_ID", "")) is None):
        raise ValueError("production_v031_context_unverified")


def unchanged_adapters() -> None:
    """Retain the accepted ingress/events; package version labels are immaterial."""
    for folder in ("workers/mail-ingress", "workers/mail-events"):
        changed = subprocess.run(["git", "diff", "--name-only", ORIGIN_SOURCE, "HEAD", "--", folder],
                                 cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        if changed.stdout.splitlines() not in ([], [folder + "/Cargo.toml"]):
            raise ValueError("production_v031_retained_source_changed")
        original = subprocess.check_output(["git", "show", f"{ORIGIN_SOURCE}:{folder}/Cargo.toml"],
                                           cwd=ROOT, text=True, timeout=30)
        old = tomllib.loads(original)
        current = tomllib.loads((ROOT / folder / "Cargo.toml").read_text(encoding="utf-8"))
        old["package"].pop("version", None)
        current["package"].pop("version", None)
        if old != current:
            raise ValueError("production_v031_retained_source_changed")


def observe(provider: FreshProvider, pins: dict[str, tuple[str | None, str]], state: str = "active",
            *, policy: dict[str, Any] | None = None, retained: dict[str, Any] | None = None,
            original: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Bracket every existing graph edge and preserve the live allowed/held policy."""
    legacy.select(pins)
    actual_policy = prior.graph.global_policy()
    if policy is not None and actual_policy != policy:
        raise ValueError("production_v031_policy_changed")
    graph = prior.graph.verify("production", state, expected_policy=actual_policy)
    for script, (deployment, version) in pins.items():
        actual = graph["pins"][script]
        if actual[1] != version or deployment is not None and actual[0] != deployment:
            raise ValueError("production_v031_predecessor_changed")
    cohort = legacy.adapter_snapshot(provider, EVENTS)
    lifecycle = legacy.adapters.lifecycle_snapshot(provider.account, provider.token,
                                                   realm="production", temporary=True)
    forwards = prior.graph.direct_forward_snapshot("production", provider.account, provider.token)
    anchors = {"forwards": forwards, "subscription": lifecycle["subscription"],
               "ingress": cohort["amail-inbound"],
               "queues": {name: row["queue_id"] for name, row in lifecycle["queues"].items()}}
    if original and prior.digest(anchors) != ORIGIN_RETAINED:
        raise ValueError("production_v031_retained_graph_changed")
    retained_now = {**anchors, "adapters": cohort, "lifecycle": lifecycle}
    if retained is not None and retained_now != retained:
        raise ValueError("production_v031_retained_graph_changed")
    prior.retained.verify_sending_privacy(provider)
    if (prior.graph.global_policy() != actual_policy
            or legacy.adapters.lifecycle_snapshot(provider.account, provider.token,
                                                  realm="production", temporary=True) != lifecycle
            or prior.graph.direct_forward_snapshot("production", provider.account, provider.token) != forwards
            or prior.graph.serving(provider.account, provider.token,
                                   {name: pin[1] for name, pin in pins.items()}) != graph["pins"]):
        raise ValueError("production_v031_retained_graph_changed")
    return {"graph": graph, "adapters": cohort}, actual_policy, retained_now


def database(provider: FreshProvider) -> usd.DatabaseClient:
    """Use the established D1 read-only adapter, not fresh-bootstrap capabilities."""
    return usd.DatabaseClient(provider.account, provider.token, "production")


def recorded_schema(provider: FreshProvider, count: int) -> None:
    """Require exact recorded migration names and the source-derived actual schema."""
    client = database(provider)
    contract = expected_schema(count)
    applied = client.query("SELECT name FROM d1_migrations ORDER BY id LIMIT 100").get("results")
    if (not isinstance(applied, list)
            or [row.get("name") for row in applied] != list(contract.migrations)
            or len(expected_schema().migrations) != 18
            or expected_schema().migrations[-1] != "0018_semantic_consent.sql"):
        raise ValueError("production_v031_schema_unverified")
    verify_schema(lambda sql: client.query(sql)["results"], contract)


def migrate(provider: FreshProvider) -> int:
    """Apply only 0018; vectors and existing account/billing state remain untouched."""
    recorded_schema(provider, 17)
    before = usd.ownership(provider)
    vectors = embedding_count(provider)
    require_artifact("mail_api")
    prior.journal("migration", "intent")
    result = subprocess.run(["wrangler", "d1", "migrations", "apply", "MAIL_DB", "--remote"],
                            cwd=ROOT / "crates/mail-worker", capture_output=True, text=True,
                            timeout=600, check=False)
    if result.returncode or len(result.stdout) + len(result.stderr) > 1_048_576:
        raise ValueError("production_v031_schema_unverified")
    prior.journal("migration", "observed")
    recorded_schema(provider, 18)
    enabled = database(provider).query("SELECT COUNT(*) AS enabled FROM semantic_preferences WHERE enabled=1").get("results")
    if enabled != [{"enabled": 0}] or embedding_count(provider) != vectors:
        raise ValueError("production_v031_embeddings_unverified")
    after = usd.ownership(provider)
    if any(after.get(address) != row for address, row in before.items()):
        raise ValueError("production_v031_ownership_changed")
    return len(before)


def embedding_count(provider: FreshProvider) -> int:
    """Read one non-content preservation count; never download mail or vectors."""
    rows = database(provider).query("SELECT COUNT(*) AS vectors FROM messages WHERE embedding_json IS NOT NULL").get("results")
    if (not isinstance(rows, list) or len(rows) != 1 or set(rows[0]) != {"vectors"}
            or type(rows[0]["vectors"]) is not int or rows[0]["vectors"] < 0):
        raise ValueError("production_v031_embeddings_unverified")
    return rows[0]["vectors"]


def pause_maintenance(provider: FreshProvider) -> str:
    """Submit the exact tested maintenance entry with an explicitly empty Cron."""
    require_artifact("mail_api")
    prior.retained.maintenance.maintenance_config("production", active=True)
    source = (ROOT / usd.CONFIGS["maintenance"]).read_text(encoding="utf-8")
    source = source.replace('crons = ["*/5 * * * *"]', 'crons = []', 1)
    source = source.replace('main = "entry/maintenance.mjs"',
                            'main = "' + (ROOT / "crates/mail-worker/entry/maintenance.mjs").as_posix() + '"', 1)
    values = {name: os.getenv(name, "") for name in
              ("OPENROUTER_API_KEY", "CF_EMAIL_ROUTING_TOKEN", "BILLING_SERVICE_KEY")}
    if not all(values.values()):
        raise ValueError("production_v031_secrets_missing")
    prior.journal("maintenance_pause", "intent")
    try:
        with tempfile.TemporaryDirectory(prefix="production-v031-", dir=ROOT / ".temp") as folder:
            config, secret = Path(folder) / "wrangler.toml", Path(folder) / "secrets.json"
            config.write_text(source, encoding="utf-8")
            secret.write_text(json.dumps(values), encoding="utf-8")
            secret.chmod(0o600)
            version = submit(["wrangler", "deploy", "--config", str(config), "--secrets-file", str(secret)],
                             "production", "mail_api", cwd=ROOT / "crates/mail-worker")
    except DeploymentFailure as error:
        if error.version:
            prior.journal("maintenance_pause", "ambiguous_version_captured", version=error.version)
        raise
    prior.journal("maintenance_pause", "version_captured", version=version)
    config_data = tomllib.loads(source)
    expected = prior.retained.maintenance.expected_bindings("production", prior.QUEUE, active=False)
    prior.readback.capture_off(provider, "amail-mail-maintenance", version,
                              expected_bindings=expected, reviewed=config_data["observability"],
                              record=lambda state, **facts: prior.journal("maintenance_pause_capture", state, **facts))
    return version


def old_usage_model(provider: FreshProvider) -> str:
    """Only modern scheduled invocations have the documented 15-minute wall bound."""
    version = prior.graph.capture.readback(provider.account, provider.token, "amail-mail-maintenance",
                                           f"versions/{PINS['amail-mail-maintenance'][1]}")
    usage = version.get("resources", {}).get("script_runtime", {}).get("usage_model")
    if usage not in ("standard", "unbound"):
        raise ValueError("production_v031_old_invocation_bound_unverified")
    return usage


def quiesce(provider: FreshProvider, pins: dict[str, tuple[str | None, str]],
            policy: dict[str, Any], retained: dict[str, Any]) -> dict[str, Any]:
    """Keep exact replacement pins and empty Cron throughout the old-Cron bound."""
    observe(provider, pins, "paused", policy=policy, retained=retained)
    started, samples = time.monotonic(), 0
    while True:
        legacy.select(pins)
        current = prior.graph.serving(provider.account, provider.token, {name: pin[1] for name, pin in pins.items()})
        if any(pin[1] != pins[name][1] for name, pin in current.items()):
            raise ValueError("production_v031_predecessor_changed")
        prior.retained.maintenance.verify("production", "paused", provider.account, provider.token,
                                         pins["amail-mail-maintenance"][1], prior.QUEUE)
        if prior.graph.global_policy() != policy:
            raise ValueError("production_v031_policy_changed")
        samples += 1
        elapsed = time.monotonic() - started
        if elapsed >= WINDOW_SECONDS:
            break
        time.sleep(min(60, WINDOW_SECONDS - elapsed))
    observe(provider, pins, "paused", policy=policy, retained=retained)
    return {"observed_monotonic_seconds": elapsed, "pin_samples": samples,
            "propagation_limit_seconds": PROPAGATION_SECONDS,
            "invocation_limit_seconds": INVOCATION_SECONDS, "old_http_drain": "NOT_CLAIMED"}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """The public health witness must come from the fixed production API itself."""

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        return None


def health_ready() -> None:
    """Wait for exact public version readiness without replaying a provider write."""
    opener = urllib.request.build_opener(NoRedirect)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        request = urllib.request.Request("https://mail.moesegfault.dev/health",
                                         headers={"User-Agent": "amail-production-witness/0.3.1"})
        try:
            with opener.open(request, timeout=min(20, max(1, deadline - time.monotonic()))) as response:
                body = response.read(16_385)
                if len(body) > 16_384:
                    raise ValueError("production_v031_health_unverified")
                value = json.loads(body)
                if (response.status == 200 and value.get("status") == "ok"
                        and value.get("version") == "0.3.1" and value.get("api_version") == 2):
                    return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(5, remaining))
    raise ValueError("production_v031_health_unverified")


def run(mode: str) -> None:
    """Submit each mutation once, stopping on any ambiguous outcome or changed edge."""
    context(mode)
    if any(path.exists() for path in (RECEIPT, RECEIPT.parent / "production-upgrade-partial.jsonl",
                                      RECEIPT.parent / "production-upgrade-capture.jsonl")):
        raise ValueError("production_v031_receipt_exists")
    unchanged_adapters()
    prior.retained.check_configs(prior.SCOPE)
    provider = FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    prior.readback.complete(provider, f"accounts/{provider.account}/queues", "queue_id", 100)
    pins = dict(PINS)
    result, policy, anchors = observe(provider, pins, original=True)
    recorded_schema(provider, 17)
    usage = old_usage_model(provider)
    preserved, witness = 0, {}
    if mode == "upgrade":
        require_artifact("mail_api")
        require_artifact("trace_sink")
        usd.billing_ready()
        pins["amail-trace-sink"] = (None, usd.replace(provider, "sink"))
        observe(provider, pins, policy=policy, retained=anchors)
        pins["amail-mail"] = (None, usd.replace(provider, "api"))
        observe(provider, pins, policy=policy, retained=anchors)
        pins["amail-mail-maintenance"] = (None, pause_maintenance(provider))
        witness = quiesce(provider, pins, policy, anchors)
        preserved = migrate(provider)
        observe(provider, pins, "paused", policy=policy, retained=anchors)
        pins["amail-mail-maintenance"] = (None, usd.replace(provider, "maintenance"))
        result, _, _ = observe(provider, pins, policy=policy, retained=anchors)
        health_ready()
    snapshot = {"schema": "production-v031/v1", "origin_run": ORIGIN_RUN,
                "source_sha": os.environ["GITHUB_SHA"], "run_id": os.environ["GITHUB_RUN_ID"],
                **result, "policy_state": policy["state"], "policy_fingerprint": prior.digest(policy),
                "retained_fingerprint": prior.digest(anchors), "preserved_addresses": preserved,
                "semantic_default_after_upgrade": "disabled", "schema_migration_applied": mode == "upgrade",
                "embedding_model_after_upgrade": "voyageai/voyage-4",
                "old_scheduled_usage_model": usage, "quiescence": witness,
                "old_http_drain": "NOT_CLAIMED"}
    RECEIPT.parent.mkdir(exist_ok=True)
    with RECEIPT.open("x", encoding="utf-8") as file:
        json.dump(snapshot, file, sort_keys=True)
        file.write("\n")


def main() -> int:
    """Keep provider prose, mail, policy values and contact snapshots out of logs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "upgrade"))
    args = parser.parse_args()
    try:
        run(args.mode)
    except Exception as error:
        known = FAILURES | legacy.FAILURES | prior.FAILURES | prior.retained.ERROR_REASONS | legacy.adapters.FAILURE_REASONS
        reason = str(error) if isinstance(error, ValueError) and str(error) in known else "unknown"
        print(f"production_v031=UNVERIFIED reason={reason} class={type(error).__name__}")
        return 1
    print("production_v031=exact_graph_policy_ownership_and_semantic_consent_preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
