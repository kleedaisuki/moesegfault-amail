"""Read staging containment settings as fixed categories, never as raw provider data.

This is a discrepancy discriminator, not a privacy attestation. It makes four
control-plane GETs and never invokes the Mail API or changes any settings.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "deploy"))
from pin_staging_mail import ACCOUNT, UUID, fetch, serving_deployment

CONFIRM = "READ_STAGING_CONTAINMENT_SETTINGS"
MISSING = object()
FIELDS = (
    "observability_shape", "logs_shape", "traces_shape",
    "enabled", "sampling", "redact", "logs", "invocation", "persist",
    "logs_sampling", "logs_destinations", "traces", "traces_sampling",
    "traces_destinations", "logpush", "tails",
)


def boolean(value: object) -> str:
    """Categorize strict boolean presence; null and wrong types are other."""
    if value is MISSING:
        return "missing"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "other"


def sampling(value: object) -> str:
    """Classify numeric one as true and zero as false; never coerce booleans."""
    if value is MISSING:
        return "missing"
    if type(value) not in (int, float):
        return "other"
    return "true" if value == 1 else "false" if value == 0 else "other"


def collection(value: object, destinations: bool = False) -> str:
    """Classify lists: false means empty or Cloudflare-only destinations.

    True means a populated tail list or at least one non-Cloudflare destination.
    Other means a malformed list; no list member is printed.
    """
    if value is MISSING:
        return "missing"
    if not isinstance(value, list) or (destinations and not all(isinstance(x, str) for x in value)):
        return "other"
    if destinations:
        return "false" if all(x == "cloudflare" for x in value) else "true"
    return "true" if value else "false"


def field(value: object, key: str) -> object:
    """Preserve missing children without serializing provider containers."""
    return value.get(key, MISSING) if isinstance(value, dict) else MISSING


def shape(value: object) -> str:
    """Distinguish an absent container from a malformed one without its contents."""
    return "missing" if value is MISSING else "true" if isinstance(value, dict) else "other"


def classify(settings: dict) -> dict[str, str]:
    """Return a closed set of field names and categorical values only."""
    obs = field(settings, "observability")
    logs, traces = field(obs, "logs"), field(obs, "traces")
    return {
        "observability_shape": shape(obs),
        "logs_shape": shape(logs),
        "traces_shape": shape(traces),
        "enabled": boolean(field(obs, "enabled")),
        "sampling": sampling(field(obs, "head_sampling_rate")),
        "redact": boolean(field(obs, "redact_query_string")),
        "logs": boolean(field(logs, "enabled")),
        "invocation": boolean(field(logs, "invocation_logs")),
        "persist": boolean(field(logs, "persist")),
        "logs_sampling": sampling(field(logs, "head_sampling_rate")),
        "logs_destinations": collection(field(logs, "destinations"), True),
        "traces": boolean(field(traces, "enabled")),
        "traces_sampling": sampling(field(traces, "head_sampling_rate")),
        "traces_destinations": collection(field(traces, "destinations"), True),
        "logpush": boolean(field(settings, "logpush")),
        "tails": collection(field(settings, "tail_consumers")),
    }


def probe(account: str, token: str, expected: str) -> tuple[str, dict[str, dict[str, str]]]:
    """Bracket both settings reads with the same expected stable-100 deployment.

    A changed deployment discards collected categories; failures never prove
    containment. Endpoint failures remain categorical, not raw exception text.
    """
    first = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if first is None:
        return "deployment_unverified", {}
    if first[1] != expected:
        return "version_mismatch", {}
    result = {}
    for suffix, label in (("settings", "settings"), ("script-settings", "script_settings")):
        try:
            result[label] = {"read": "available", **classify(fetch(account, token, suffix))}
        except Exception:
            result[label] = {"read": "unavailable"}
    second = serving_deployment(fetch(account, token, "deployments?per_page=1&page=1"))
    if first != second:
        return "deployment_changed", {}
    status = "stable100" if all(x["read"] == "available" for x in result.values()) else "settings_unavailable"
    return status, result


def main() -> int:
    """Validate inputs before any GET and emit no uncontrolled strings."""
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    expected = os.environ.get("AMAIL_EXPECTED_WORKER_VERSION", "")
    confirm = os.environ.get("AMAIL_CONTAINMENT_CONFIRM", "")
    if confirm != CONFIRM or not ACCOUNT.fullmatch(account) or not token or not UUID.fullmatch(expected):
        status, result = "invalid_input", {}
    else:
        try:
            status, result = probe(account, token, expected)
        except Exception:
            status, result = "unavailable", {}
    print("staging_containment_readback=" + status)
    for endpoint in ("settings", "script_settings"):
        values = result.get(endpoint, {})
        for name in ("read", *FIELDS):
            if name in values:
                print("staging_containment_" + endpoint + "_" + name + "=" + values[name])
    return 0 if status == "stable100" else 1


if __name__ == "__main__":
    raise SystemExit(main())
