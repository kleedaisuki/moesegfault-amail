"""Compare anonymous urllib and amail-equivalent reqwest on one staging route.

The two synthetic GETs have the same path/query marker and runner, but no auth.
Only fixed response facts leave this process. This is a transport discriminator,
not a retained-log privacy proof or a replacement for the original canary.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid


ROOT = Path(__file__).resolve().parents[2]
API = "https://mail-staging.moesegfault.dev"
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
RUST_LINE = re.compile(
    rb"staging_http_compare: status=(401|403|3xx|2xx|other_4xx|5xx|other) "
    rb"id=(true|false) ray=(true|false) redirect=(true|false)\r?\n\Z"
)
BIN = ROOT / "target" / "debug" / "staging-http-compare.exe"


class CompareError(Exception):
    """Fixed diagnostic failure; never carries URL, header, or provider text."""


class NoFollow(HTTPRedirectHandler):
    """Observe a redirect but do not disclose the marker to another origin."""

    def __init__(self) -> None:
        super().__init__()
        self.seen = False

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        """Stop before a second request; the first response remains inspectable."""

        self.seen = True
        return None


def status_label(status: int) -> str:
    """Keep the exact 401/403 discriminator without exposing arbitrary status."""

    if status in (401, 403):
        return str(status)
    if 200 <= status <= 299:
        return "2xx"
    if 300 <= status <= 399:
        return "3xx"
    if 400 <= status <= 499:
        return "other_4xx"
    if 500 <= status <= 599:
        return "5xx"
    return "other"


def header_facts(headers) -> tuple[bool, bool]:
    """Inspect only a canonical app UUID and presence of a single CF Ray."""

    ids = headers.get_all("x-amail-request-id", [])
    rays = headers.get_all("cf-ray", [])
    return (len(ids) == 1 and UUID.fullmatch(ids[0]) is not None,
            len(rays) == 1 and bool(rays[0]))


def urllib_facts(url: str) -> tuple[str, bool, bool, bool]:
    """GET without reading a body, following a redirect, or logging a URL."""

    redirect = NoFollow()
    opener = build_opener(redirect)
    try:
        with opener.open(Request(url, method="GET"), timeout=30) as response:
            status, headers = response.status, response.headers
    except HTTPError as error:
        status, headers = error.code, error.headers
    except (URLError, TimeoutError):
        raise CompareError("urllib_network_unverified") from None
    return (status_label(status), *header_facts(headers), redirect.seen)


def reqwest_environment() -> dict[str, str]:
    """Retain OS/proxy discovery, never pass the preflight credentials to Rust."""

    allowed = (
        "PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT",
        "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL", "HTTP_PROXY", "HTTPS_PROXY",
        "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    )
    return {key: os.environ[key] for key in allowed if key in os.environ}


def reqwest_facts(url: str, binary: Path = BIN) -> tuple[str, bool, bool, bool]:
    """Parse only the helper's exact closed vocabulary, discarding stderr."""

    if not binary.is_file() or not binary.resolve().is_relative_to((ROOT / "target").resolve()):
        raise CompareError("reqwest_binary_unverified")
    try:
        result = subprocess.run(
            [str(binary)], input=(url + "\n").encode("ascii"), env=reqwest_environment(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=35, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise CompareError("reqwest_process_unverified") from None
    match = RUST_LINE.fullmatch(result.stdout[:257]) if len(result.stdout) <= 256 else None
    if result.returncode != 0 or match is None:
        raise CompareError("reqwest_response_unverified")
    status, app_id, ray, redirected = match.groups()
    return (status.decode("ascii"), app_id == b"true", ray == b"true",
            redirected == b"true")


def compare(first: tuple[str, bool, bool, bool],
            second: tuple[str, bool, bool, bool]) -> str:
    """Classify both paths without turning a 403 into privacy acceptance."""

    if first[:2] == second[:2] == ("401", True) and not first[3] and not second[3]:
        return "both_worker_contract_observed"
    if first != second:
        return "transport_difference_unverified"
    return "same_noncontract_response_unverified"


def main() -> int:
    """Run once after effective staging privacy settings are verified."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", choices=["RUN_STAGING_TRACE_HTTP_COMPARE"], required=True)
    parser.parse_args()
    try:
        account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        if re.fullmatch(r"[0-9a-f]{32}", account) is None or not token:
            raise CompareError("preflight_credentials_unverified")
        from staging_trace_canary import preflight

        obs_token = os.environ.get("CF_OBSERVABILITY_TOKEN", "")
        if not obs_token:
            raise CompareError("preflight_credentials_unverified")
        try:
            preflight(account, obs_token, token)
        except Exception:
            raise CompareError("privacy_preflight_unverified") from None
        marker = uuid.uuid4().hex
        url = (f"{API}/v1/messages/amail_path_canary_{marker}"
               f"?probe=amail_query_canary_{marker}")
        first = urllib_facts(url)
        second = reqwest_facts(url)
        label = compare(first, second)
    except CompareError as error:
        print(f"staging_trace_http_compare: UNVERIFIED ({error.args[0]})")
        return 1
    except Exception:
        print("staging_trace_http_compare: UNVERIFIED (local_probe_unverified)")
        return 1
    for name, facts in (("urllib", first), ("reqwest", second)):
        status, app_id, ray, redirected = facts
        print(f"{name}: status={status} app_id={str(app_id).lower()} "
              f"cf_ray={str(ray).lower()} redirect={str(redirected).lower()}")
    print(f"staging_trace_http_compare: {label}")
    return 0 if label == "both_worker_contract_observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
