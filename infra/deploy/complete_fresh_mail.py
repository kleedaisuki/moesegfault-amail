"""Complete an admitted fresh paused Mail graph without releasing global sending.

The protected first-attempt job installs inbound/lifecycle adapters and enables
maintenance on the already-created stores. It never migrates, recreates stores,
replaces the API/sink, sends mail, grants a canary, or retries an ambiguous write.
Usage: set AMAIL_FRESH_BOOTSTRAP_RUN_ID to the protected paused receipt producer
and invoke this module from the production-fresh-online CI job.
"""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
sys.path.insert(0, str(ROOT / "infra/provider"))
from fresh_bootstrap_contract import Epoch, Scope, REPO, STAGING_DATABASE
from fresh_bootstrap_receipt import load
from fresh_bootstrap_scope import FreshProvider
import fresh_bootstrap_readback as readback
import fresh_mail_bootstrap as bootstrap
import inspect_held_production as old
from tested_worker_artifact import require_artifact
from worker_deploy_result import submit, DeploymentFailure
from pin_staging_mail import mail_resources, serving_deployment, _bindings_match
from check_mail_maintenance import CADENCE, entry_surface_match, schedules_match
from check_production_role_graph import forward_snapshot
import check_observability as capture
import worker_artifact

CONFIRM = "RUN_FRESH_PRODUCTION_ONLINE"
FOLDER = ROOT / ".temp/fresh-online"
CONFIGS = {"api": "crates/mail-worker/wrangler.toml",
           "maintenance": "crates/mail-worker/wrangler-maintenance.toml",
           "mail_ingress": "workers/mail-ingress/wrangler.toml",
           "mail_events": "workers/mail-events/wrangler.toml"}
ADAPTERS = {"mail_ingress": "amail-inbound", "mail_events": "amail-events"}
# Closed source-owned labels only: never project arbitrary exception arguments.
ERROR_REASONS = {
    "fresh_online_protected_context_required", "fresh_online_scope_mismatch",
    "fresh_online_source_database_unadopted", "fresh_online_staging_database_changed",
    "fresh_online_source_bucket_unadopted", "fresh_online_operation_unverified",
    "fresh_online_email_phase_unreviewed", "fresh_online_adapter_unreviewed",
    "fresh_online_ingress_secret_missing", "fresh_online_adapter_serving_unverified",
    "fresh_online_adapter_capabilities_unverified", "fresh_online_ingress_service_unverified",
    "fresh_online_adapter_capture_unverified", "fresh_online_adapters_changed",
    "fresh_online_event_queue_unverified", "fresh_online_event_dlq_consumer_unreviewed",
    "fresh_online_event_consumer_unverified", "fresh_online_recovery_path_unreviewed",
    "fresh_online_record_unreviewed", "fresh_online_paused_graph_changed",
    "fresh_online_external_graph_changed", "fresh_online_capabilities_missing",
    "fresh_provider_read_unverified", "fresh_inventory_incomplete", "fresh_inventory_unverified",
    "fresh_serving_unverified", "fresh_d1_read_unverified", "fresh_send_hold_unverified",
    "fresh_grant_unverified", "fresh_population_unverified", "fresh_queue_identity_unverified",
    "fresh_queue_detail_unverified", "fresh_queue_consumers_unverified", "fresh_public_domain_unverified",
    "fresh_zones_unverified", "fresh_public_route_unverified", "fresh_api_ingress_shadowed",
    "fresh_version_unverified", "fresh_capabilities_unverified", "fresh_capture_or_surface_unverified",
    "fresh_coordinates_unreviewed", "fresh_schedule_unreviewed", "fresh_r2_empty_unverified",
    "fresh_graph_changed", "process_exit", "version_count", "output_limit",
}


def failure_reason(error: Exception) -> str:
    """Keep useful fixed predicate labels while excluding credentials and provider prose."""
    if (isinstance(error, ValueError) and len(error.args) == 1
            and isinstance(error.args[0], str) and error.args[0] in ERROR_REASONS):
        return error.args[0]
    return old.failure_reason(error)


def admit() -> Epoch:
    """Require protected current-main context and all original installed modules.

    Full source jobs are workflow dependencies; this check cannot replace them.
    The admitted bootstrap receipt comes from a different immutable producer.
    """
    expected = {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": REPO,
                "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_RUN_ATTEMPT": "1", "GITHUB_JOB": "production-fresh-online",
                "GITHUB_WORKFLOW_REF": f"{REPO}/.github/workflows/ci.yml@refs/heads/main",
                "AMAIL_PRODUCTION_ONLINE_CONFIRM": CONFIRM,
                "AMAIL_PRODUCTION_GRAPH_FREEZE": "FREEZE_PRODUCTION_GRAPH_WRITERS",
                "AMAIL_PRODUCTION_ENVIRONMENT": "production"}
    if any(os.getenv(key) != value for key, value in expected.items()):
        raise ValueError("fresh_online_protected_context_required")
    for component in ("mail_api", "mail_ingress", "mail_events"):
        require_artifact(component)
    identity = worker_artifact.context()
    manifest = worker_artifact.FOLDER / "manifest.json"
    return Epoch(identity["source_sha"], identity["run_id"],
                 int(os.environ["AMAIL_WORKER_ARTIFACT_ID"]),
                 hashlib.sha256(manifest.read_bytes()).hexdigest(),
                 identity["rust"], identity["worker_build"])


def receipt_scope(value: dict) -> Scope:
    """Keep original creation names independent of the latest deployment source."""
    epoch = Epoch(**value.get("creation_epoch", value["source_epoch"]))
    stores = value["scope"]
    scope = Scope(epoch, stores["database"], stores["database_created_at"], stores["bucket_created_at"])
    if stores["database_name"] != scope.database_name or stores["bucket"] != scope.bucket:
        raise ValueError("fresh_online_scope_mismatch")
    return scope


def check_configs(scope: Scope) -> None:
    """Require source adoption into all production stores, keeping staging fixed."""
    for role in ("api", "maintenance", "mail_events"):
        with (ROOT / CONFIGS[role]).open("rb") as file:
            config = tomllib.load(file)
        databases = config.get("d1_databases")
        if (not isinstance(databases, list) or len(databases) != 1
                or databases[0].get("binding") != "MAIL_DB"
                or databases[0].get("database_id") != scope.database
                or databases[0].get("database_name") != scope.database_name):
            raise ValueError("fresh_online_source_database_unadopted")
        stage = config["env"]["staging"]
        stage_databases = stage.get("d1_databases")
        if (not isinstance(stage_databases, list) or len(stage_databases) != 1
                or stage_databases[0].get("binding") != "MAIL_DB"
                or stage_databases[0].get("database_id") != STAGING_DATABASE
                or stage_databases[0].get("database_name") != "moesegfault-mail-staging"):
            raise ValueError("fresh_online_staging_database_changed")
        if role != "mail_events":
            if (mail_resources(config) != (scope.database, scope.bucket)
                    or mail_resources(stage) != (STAGING_DATABASE, "moesegfault-mail-raw-staging")):
                raise ValueError("fresh_online_source_bucket_unadopted")
    from check_staging import check
    check()


def captured(command: list[str], classifier: str | None = None, *, env=None) -> None:
    """Run once with private output; only a fixed successful classifier is admitted."""
    result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                            text=True, check=False, timeout=600)
    if (result.returncode or len(result.stdout) + len(result.stderr) > 1_048_576
            or classifier is not None and result.stdout.strip() != classifier):
        raise ValueError("fresh_online_operation_unverified")


def email_events(phase: str) -> None:
    """Provision only reviewed production queues/subscription, without output leaks."""
    if phase not in ("queues", "subscription"):
        raise ValueError("fresh_online_email_phase_unreviewed")
    captured([sys.executable, str(ROOT / "infra/deploy/ensure_email_events.py"),
              "--target", "production", "--phase", phase],
             f"email events {phase} ready: production")


def deploy_adapter(component: str) -> str:
    """Deploy installed tested bytes once; remove private ingress secret on failure."""
    if component not in ADAPTERS:
        raise ValueError("fresh_online_adapter_unreviewed")
    require_artifact(component)
    command = ["wrangler", "deploy", "--config", str(ROOT / CONFIGS[component])]
    secret_path = None
    try:
        if component == "mail_ingress":
            secret = os.getenv("INGRESS_SECRET", "")
            if not secret:
                raise ValueError("fresh_online_ingress_secret_missing")
            descriptor, name = tempfile.mkstemp(prefix="fresh-online-secret-", suffix=".json", dir=ROOT / ".temp")
            secret_path = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                secret_path.chmod(0o600)
                json.dump({"INGRESS_SECRET": secret}, output)
            command.extend(["--secrets-file", str(secret_path)])
        return submit(command, "production", component, cwd=ROOT)
    finally:
        if secret_path is not None:
            secret_path.unlink(missing_ok=True)


def adapter_pins(provider, versions: dict) -> dict:
    """Read exact single100 deployment coordinates, never trust a printed version."""
    result = {}
    for component, version in versions.items():
        pin = serving_deployment(capture.readback(provider.account, provider.token,
                                                ADAPTERS[component], "deployments?per_page=1&page=1"))
        if pin is None or pin[1] != version:
            raise ValueError("fresh_online_adapter_serving_unverified")
        result[ADAPTERS[component]] = {"deployment": pin[0], "version": pin[1]}
    return result


def verify_adapters(provider, scope: Scope, versions: dict) -> dict:
    """Bracket immutable adapter capabilities and effective independent capture-off."""
    before = adapter_pins(provider, versions)
    for component, version in versions.items():
        script = ADAPTERS[component]
        read = lambda suffix: capture.readback(provider.account, provider.token, script, suffix)
        with (ROOT / CONFIGS[component]).open("rb") as file:
            config = tomllib.load(file)
        expected = {name: ("plain_text", value) for name, value in config.get("vars", {}).items()}
        if component == "mail_ingress":
            expected.update({"INGRESS_SECRET": ("secret_text", None), "MAIL_API": ("service", None)})
        else:
            expected["MAIL_DB"] = ("d1", scope.database)
        immutable = read(f"versions/{version}")
        if (not _bindings_match(immutable, version, expected)
                or not entry_surface_match(immutable, version, "email" if component == "mail_ingress" else "queue")):
            raise ValueError("fresh_online_adapter_capabilities_unverified")
        if component == "mail_ingress":
            bindings = immutable["resources"]["bindings"]
            bindings = bindings["result"] if isinstance(bindings, dict) else bindings
            service = next(binding for binding in bindings if binding["name"] == "MAIL_API")
            if service.get("service") != "amail-mail" or service.get("environment") not in (None, "production"):
                raise ValueError("fresh_online_ingress_service_unverified")
        settings, legacy = read("settings"), read("script-settings")
        worker = capture.worker_readback(provider.account, provider.token, script)
        subdomain = read("subdomain")
        if (not capture.effective_api_settings(worker, script, settings, legacy)
                or not isinstance(subdomain, dict) or subdomain.get("enabled") is not False
                or subdomain.get("previews_enabled") is not False or not schedules_match(read("schedules"))):
            raise ValueError("fresh_online_adapter_capture_unverified")
    verify_event_consumer(provider)
    if adapter_pins(provider, versions) != before:
        raise ValueError("fresh_online_adapters_changed")
    return before


def verify_event_consumer(provider) -> None:
    """Observe the lifecycle consumer/DLQ, not merely its immutable queue handler."""
    base = f"accounts/{provider.account}"
    queues = readback.complete(provider, f"{base}/queues", "queue_id", 100)
    for name in ("amail-sending-events", "amail-sending-events-dlq"):
        matches = [row for row in queues if row.get("queue_name") == name]
        if len(matches) != 1:
            raise ValueError("fresh_online_event_queue_unverified")
        detail = provider.get(f"{base}/queues/{matches[0]['queue_id']}")
        if (not isinstance(detail, dict) or detail.get("queue_id") != matches[0]["queue_id"]
                or detail.get("queue_name") != name or not isinstance(detail.get("consumers"), list)
                or type(detail.get("consumers_total_count")) is not int
                or detail["consumers_total_count"] != len(detail["consumers"] )):
            raise ValueError("fresh_online_event_queue_unverified")
        consumers = detail["consumers"]
        if name.endswith("-dlq"):
            if consumers:
                raise ValueError("fresh_online_event_dlq_consumer_unreviewed")
            continue
        if len(consumers) != 1 or not isinstance(consumers[0], dict):
            raise ValueError("fresh_online_event_consumer_unverified")
        consumer = consumers[0]
        settings = consumer.get("settings")
        if (consumer.get("type") != "worker" or consumer.get("script_name") != "amail-events"
                or consumer.get("dead_letter_queue") != "amail-sending-events-dlq"
                or not isinstance(settings, dict) or any(settings.get(key) != wanted for key, wanted in {
                    "batch_size": 10, "max_wait_time_ms": 5000, "max_retries": 5, "retry_delay": 120}.items())):
            raise ValueError("fresh_online_event_consumer_unverified")


class Online:
    """One-shot controller; every write is preceded by a private fsynced intent."""

    def __init__(self, folder: Path = FOLDER):
        """Use only the repository-owned recovery tree; refuse prior attempt reuse."""
        self.folder = Path(folder)
        if (not self.folder.resolve().is_relative_to((ROOT / ".temp").resolve())
                or any(path.is_symlink() for path in (self.folder, *self.folder.parents))):
            raise ValueError("fresh_online_recovery_path_unreviewed")
        self.journal = self.folder / "recovery/controller.jsonl"
        self.phase = "admission"
        self.epoch = None
        self.scope = None

    def record(self, state: str, **facts) -> None:
        """Persist closed aggregate fields, never error text, provider bodies or secrets."""
        if state not in {"intent", "observed", "failed"} or set(facts) - {"version", "error_type"}:
            raise ValueError("fresh_online_record_unreviewed")
        value = {"schema": "mail-fresh-online-controller/v1", "phase": self.phase,
                 "state": state, **facts}
        if self.epoch is not None:
            value["source_epoch"] = asdict(self.epoch)
        if self.scope is not None:
            value["creation_epoch"] = asdict(self.scope.epoch)
            value["resources"] = {"database": self.scope.database, "bucket": self.scope.bucket}
        with self.journal.open("a", encoding="utf-8") as output:
            output.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
            output.flush()
            os.fsync(output.fileno())

    def step(self, phase: str, action):
        """Attempt an operation once; ambiguity stops all subsequent phases."""
        self.phase = phase
        self.record("intent")
        result = action()
        self.record("observed", **({"version": result} if phase in {*ADAPTERS, "maintenance"} else {}))
        return result

    def run(self) -> dict:
        """Reach active maintenance with global sending held, or leave diagnostic intent."""
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        try:
            self.epoch = self.step("admission", admit)
            receipt = self.step("receipt_origin", lambda: load(os.getenv("AMAIL_FRESH_BOOTSTRAP_RUN_ID", "")))
            value = receipt.value
            scope = receipt_scope(value)
            self.scope = scope
            self.step("source_adoption", lambda: check_configs(scope))
            provider, s3 = self.step("capabilities", lambda: capabilities(scope))
            queue, dlq = value["resources"]["queue"], value["resources"]["dlq"]
            pins = {script: pin["version"] for script, pin in value["graph"]["pins"].items()}
            before = self.step("paused_readback", lambda: readback.verify(
                scope, pins, queue, dlq, provider, maintenance_crons=(), source_active=True))
            if dict(before) != value["graph"]:
                raise ValueError("fresh_online_paused_graph_changed")
            forwards = forward_snapshot(provider.account)
            dns_env = {**os.environ, "CF_ZONE_ID": "6edff81c6ed02f412e70868076411a5e",
                       "MAIL_SENDING_DOMAIN": "mail.moesegfault.dev"}
            self.step("sending_dns", lambda: captured([sys.executable, str(ROOT / "infra/dns/verify_sending.py")], env=dns_env))
            self.step("sending_privacy", lambda: captured(
                [sys.executable, str(ROOT / "infra/provider/configure_sending_privacy.py"), "--target", "production"],
                "sending_privacy=verified target=production preview=false drop_suppressed=false"))
            self.step("email_queues", lambda: email_events("queues"))
            versions = {component: self.step(component, lambda component=component: deploy_adapter(component))
                        for component in ADAPTERS}
            self.step("email_subscription", lambda: email_events("subscription"))
            pins["amail-mail-maintenance"] = self.step("maintenance", lambda: bootstrap.submit_once(
                "maintenance", ROOT / CONFIGS["maintenance"], scope))
            adapters_before = self.step("adapter_readback", lambda: verify_adapters(provider, scope, versions))
            graph = self.step("active_readback", lambda: readback.verify(
                scope, pins, queue, dlq, provider, maintenance_crons=CADENCE, source_active=True))
            if adapter_pins(provider, versions) != adapters_before or forward_snapshot(provider.account) != forwards:
                raise ValueError("fresh_online_external_graph_changed")
            result = {"schema": "mail-fresh-online/v1", "realm": "production", "state": "online-held",
                      "creation_epoch": asdict(scope.epoch), "source_epoch": asdict(self.epoch),
                      "bootstrap_source_epoch": value["source_epoch"], "bootstrap_artifact_id": receipt.artifact_id,
                      "scope": value["scope"], "resources": value["resources"], "graph": dict(graph),
                      "adapter_pins": adapters_before, "sendHeld": True, "external_activation": {"maintenance_cron": True},
                      "sending_privacy": "VERIFIED", "sending_dns": "VERIFIED",
                      "send_release": "NOT_GRANTED", "old_work_end": "UNVERIFIED"}
            self.step("receipt", lambda: self.persist(result))
            return result
        except Exception as error:
            facts = {"error_type": type(error).__name__}
            if isinstance(error, DeploymentFailure) and error.version is not None:
                facts["version"] = error.version
            self.record("failed", **facts)
            raise

    def persist(self, value: dict) -> None:
        """Publish success only after runtime brackets; never overwrite an earlier receipt."""
        descriptor = os.open(self.folder / "receipt.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")
            output.flush()
            os.fsync(output.fileno())


def capabilities(scope: Scope):
    """Bind readonly inspection to admitted existing stores, never call create_scope."""
    required = ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCESS_KEY_ID",
                "CLOUDFLARE_SECRET_ACCESS_KEY", "CF_EMAIL_ROUTING_TOKEN", "ROLE_FORWARD_DESTINATION",
                "OPENROUTER_API_KEY", "INGRESS_SECRET")
    if not all(os.getenv(name, "") for name in required):
        raise ValueError("fresh_online_capabilities_missing")
    provider = FreshProvider(os.environ["CLOUDFLARE_ACCOUNT_ID"], os.environ["CLOUDFLARE_API_TOKEN"])
    provider._epoch, provider._scope = scope.epoch, scope
    import boto3
    from botocore.config import Config
    s3 = boto3.client("s3", endpoint_url=f"https://{provider.account}.r2.cloudflarestorage.com",
                      aws_access_key_id=os.environ["CLOUDFLARE_ACCESS_KEY_ID"],
                      aws_secret_access_key=os.environ["CLOUDFLARE_SECRET_ACCESS_KEY"], region_name="auto",
                      config=Config(connect_timeout=15, read_timeout=30, retries={"max_attempts": 0}))
    provider.r2_empty = lambda bucket: old.r2_count(s3, bucket) == 0
    provider.forward_snapshot = forward_snapshot
    return provider, s3


def main() -> int:
    """Emit the source phase and closed failure label, never provider exception text."""
    controller = None
    try:
        controller = Online()
        controller.run()
    except Exception as error:
        phase = controller.phase if controller is not None else "admission"
        print(f"fresh_production_online=UNVERIFIED phase={phase} error_type={type(error).__name__} "
              f"reason={failure_reason(error)} replay=NOT_GRANTED")
        return 1
    print("fresh_production_online=online-held maintenance_cron=active send_release=NOT_GRANTED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
