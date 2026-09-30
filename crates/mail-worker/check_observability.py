"""Fail closed when mail API observability differs from the reviewed privacy boundary."""

from __future__ import annotations

import argparse
import json
import math
import sys
import os
import re
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CONFIG = Path(__file__).with_name("wrangler.toml")
SINK_CONFIG = CONFIG.parents[2] / "workers" / "trace-sink" / "wrangler.toml"
SINK_SCRIPT = {"production": "amail-trace-sink", "staging": "amail-trace-sink-staging"}
SCRIPT = {"production": "amail-mail", "staging": "amail-mail-staging"}


def built_in_destinations(value: object) -> bool:
    """Accept only Cloudflare's own retained log sink, never external exports."""

    return value is None or (
        isinstance(value, list)
        and all(destination == "cloudflare" for destination in value)
    )


def safe_observability(value: object, *, sink: bool = False) -> bool:
    """Require public API retention entirely disabled, even for custom safe messages."""

    if not isinstance(value, dict):
        return False
    logs = value.get("logs")
    traces = value.get("traces")
    return (
        value.get("enabled") is sink
        and type(value.get("head_sampling_rate")) in (int, float)
        and value.get("head_sampling_rate") == 1.0
        and value.get("redact_query_string") is True
        and isinstance(logs, dict)
        and logs.get("enabled") is sink
        and logs.get("invocation_logs") is False
        and logs.get("persist") is not False
        and logs.get("head_sampling_rate", 1.0) == 1.0
        and built_in_destinations(logs.get("destinations"))
        and isinstance(traces, dict)
        and traces.get("enabled") is False
        and built_in_destinations(traces.get("destinations"))
    )


def safe_settings(value: object, *, sink: bool = False) -> bool:
    """Reject unreviewed script-level export consumers in API readback."""

    return (
        isinstance(value, dict)
        and safe_observability(value.get("observability"), sink=sink)
        and value.get("logpush") is not True
        and not value.get("tail_consumers")
    )


def capture_disabled(value: object, *, complete: bool = True) -> bool:
    """Validate explicit capture-off, not inactive sampling/persistence preferences.

    Cloudflare documents logs.enabled and traces.enabled as their capture
    switches. Invocation/persistence/redaction preferences do not enable a
    disabled subsystem. Issues is independently controlled and must be off.
    Legacy partial objects may omit fields, but cannot contradict the resource.
    """
    if not isinstance(value, dict):
        return False
    if set(value) - {"enabled", "head_sampling_rate", "redact_query_string",
                     "logs", "traces", "issues"}:
        return False
    if (complete or "enabled" in value) and value.get("enabled") is not False:
        return False
    for name in ("logs", "traces", "issues"):
        if name not in value and not complete:
            continue
        section = value.get(name)
        if not isinstance(section, dict):
            return False
        allowed = {"enabled"} if name == "issues" else {
            "enabled", "destinations", "head_sampling_rate", "persist",
            "invocation_logs"} if name == "logs" else {
            "enabled", "destinations", "head_sampling_rate", "persist",
            "propagation_policy"}
        if set(section) - allowed:
            return False
        if (complete or "enabled" in section) and section.get("enabled") is not False:
            return False
        if "destinations" in section and not (
                isinstance(section["destinations"], list)
                and all(x == "cloudflare" for x in section["destinations"])):
            return False
        for key in ("persist", "invocation_logs"):
            if key in section and type(section[key]) is not bool:
                return False
        if "propagation_policy" in section and section["propagation_policy"] not in (
                None, "authenticated", "accept"):
            return False
        if not valid_sampling(section):
            return False
    return (valid_sampling(value) and ("redact_query_string" not in value
            or type(value["redact_query_string"]) is bool))


def valid_sampling(value: dict) -> bool:
    """Accept optional finite numeric preferences only within the documented range."""
    if "head_sampling_rate" not in value:
        return True
    rate = value["head_sampling_rate"]
    return type(rate) in (int, float) and math.isfinite(rate) and 0 <= rate <= 1


def legacy_noncontradictory(value: object) -> bool:
    """Missing/null legacy observability is unsupported, never positive evidence."""
    if not isinstance(value, dict):
        return False
    if "logpush" in value and value["logpush"] is not False:
        return False
    if "tail_consumers" in value and value["tail_consumers"] != []:
        return False
    if "streaming_tail_consumers" in value and value["streaming_tail_consumers"] != []:
        return False
    obs = value.get("observability")
    return obs is None or capture_disabled(obs, complete=False)


def effective_api_settings(worker: object, script: str, *legacy: object) -> bool:
    """Require the exact current Worker resource and explicit no-capture/no-export.

    Preview templates and absent legacy representations cannot establish safety.
    This policy does not change the enabled private Queue sink's stricter policy.
    """
    if not isinstance(worker, dict):
        return False
    identity = worker.get("id")
    return (worker.get("name") == script and isinstance(identity, str)
            and 0 < len(identity) <= 128 and identity.strip() == identity
            and worker.get("logpush") is False
            and isinstance(worker.get("tail_consumers"), list)
            and worker["tail_consumers"] == []
            and ("streaming_tail_consumers" not in worker
                 or worker["streaming_tail_consumers"] == [])
            and capture_disabled(worker.get("observability"))
            and all(legacy_noncontradictory(value) for value in legacy))


def local_settings(realm: str, *, sink: bool = False) -> dict:
    """Read the matching Wrangler realm without relying on TOML inheritance."""

    with (SINK_CONFIG if sink else CONFIG).open("rb") as source:
        config = tomllib.load(source)
    if realm == "production":
        return {"observability": config.get("observability")}
    return {"observability": config.get("env", {}).get("staging", {}).get("observability")}


def worker_readback(account: str, token: str, script: str) -> dict:
    """Read the exact-name current Worker resource, not its preview template."""
    return fetch_result(account, token, f"workers/{script}")


def readback(account: str, token: str, script: str, suffix: str) -> dict:
    """Read the reviewed script endpoint without disclosing provider data."""
    return fetch_result(account, token, f"scripts/{script}/{suffix}")


def fetch_result(account: str, token: str, path: str) -> dict:
    """Fetch settings without printing response bodies or request credentials."""

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/{path}"
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read(262_145)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError("Cloudflare settings readback unavailable") from error
    if len(payload) > 262_144:
        raise ValueError("Cloudflare settings readback too large")
    try:
        envelope = json.loads(payload)
        if envelope.get("success") is not True or not isinstance(envelope.get("result"), dict):
            raise ValueError
        return envelope["result"]
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError("Cloudflare settings readback malformed") from error


def verify(realm: str, account: str, token: str, *, sink: bool = False) -> bool:
    """Bracket positive current-resource capture-off with unchanged single100 serving."""

    if not safe_observability(local_settings(realm, sink=sink)["observability"], sink=sink):
        return False
    script = (SINK_SCRIPT if sink else SCRIPT)[realm]
    if sink:
        from check_trace_sink_isolation import verify as verify_isolation
        return verify_isolation(account, token, realm, script, readback, safe_settings)
    deploy_dir = str(CONFIG.parents[2] / "infra" / "deploy")
    if deploy_dir not in sys.path:
        sys.path.insert(0, deploy_dir)
    from pin_staging_mail import serving_deployment
    first = serving_deployment(readback(account, token, script, "deployments?per_page=1&page=1"))
    if first is None:
        return False
    expected = os.environ.get("AMAIL_EXPECTED_WORKER_VERSION")
    if expected is not None and first[1] != expected:
        return False
    settings = readback(account, token, script, "settings")
    script_settings = readback(account, token, script, "script-settings")
    worker = worker_readback(account, token, script)
    if not effective_api_settings(worker, script, settings, script_settings):
        return False
    second = serving_deployment(readback(account, token, script, "deployments?per_page=1&page=1"))
    return second == first


def main() -> int:
    """Return nonzero on any missing setting, API failure, or unsafe export path."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--realm", choices=tuple(SCRIPT), required=True)
    parser.add_argument("--mode", choices=("api", "sink"), default="api")
    args = parser.parse_args()
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if re.fullmatch(r"[0-9a-f]{32}", account) is None or not token:
        print("Mail observability verification unavailable: missing credentials")
        return 1
    try:
        safe = verify(args.realm, account, token, sink=args.mode == "sink")
    except ValueError:
        safe = False
    print(f"Mail observability {args.mode} {args.realm}: {'safe' if safe else 'UNVERIFIED'}")
    return 0 if safe else 1


if __name__ == "__main__":
    raise SystemExit(main())
