"""Fail closed when mail API observability differs from the reviewed privacy boundary."""

from __future__ import annotations

import argparse
import json
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


def local_settings(realm: str, *, sink: bool = False) -> dict:
    """Read the matching Wrangler realm without relying on TOML inheritance."""

    with (SINK_CONFIG if sink else CONFIG).open("rb") as source:
        config = tomllib.load(source)
    if realm == "production":
        return {"observability": config.get("observability")}
    return {"observability": config.get("env", {}).get("staging", {}).get("observability")}


def readback(account: str, token: str, script: str, suffix: str) -> dict:
    """Fetch settings without printing response bodies or request credentials."""

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/scripts/{script}/{suffix}"
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
    """Check local intent, current script/version settings, and script-level settings."""

    if not safe_observability(local_settings(realm, sink=sink)["observability"], sink=sink):
        return False
    script = (SINK_SCRIPT if sink else SCRIPT)[realm]
    return all(
        safe_settings(readback(account, token, script, suffix), sink=sink)
        for suffix in ("settings", "script-settings")
    )


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
