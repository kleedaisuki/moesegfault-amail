"""Exercise one disposable private R2 object on hosted staging only.

Usage: dispatch CI target ``staging-r2-object-capability`` with the exact
``RUN_STAGING_R2_OBJECT_CAPABILITY`` confirmation. This is not a local probe.
Only fixed result labels are emitted; a failed/aborted run requires independent
inventory reconciliation before a new key or second-principal mutation.
"""

from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import re
import sys
import tomllib
import urllib.error
import urllib.request
import uuid

from staging_second_principal import BUCKET, KEY, NoRedirect, object_inventory


ROOT = Path(__file__).resolve().parents[2]
API = "https://api.cloudflare.com/client/v4"
SENTINEL = b"amail staging R2 capability sentinel v1\nnot an email or verification code\n"
BOUNDARY = "amail-staging-r2-capability-v1"
MAX_REPLY = 65_536


class ProbeFailure(Exception):
    """Carry only a source-owned fixed failure label to the workflow log."""


OPENER = urllib.request.build_opener(NoRedirect())


def require(condition: bool, label: str) -> None:
    """Reject a state without interpolating private/provider material."""

    if not condition:
        raise ProbeFailure(label)


def audit(script: str, *args: str) -> None:
    """Run existing private-config/route checks without redirecting bearer tokens."""

    path = ROOT / "workers" / "identity-test-inbox" / script
    spec = importlib.util.spec_from_file_location("staging_r2_audit", path)
    require(spec is not None and spec.loader is not None, "staging_preflight_failed")
    module = importlib.util.module_from_spec(spec)
    prior_urlopen = urllib.request.urlopen
    try:
        # These already-reviewed helpers use urllib.request.urlopen. Override
        # only during synchronous audit so a 30x cannot forward either token.
        urllib.request.urlopen = OPENER.open
        spec.loader.exec_module(module)
        if script == "check_config.py" and args == ("--live", "--deployed"):
            with path.with_name("wrangler.toml").open("rb") as stream:
                config = tomllib.load(stream)
            require(module.valid(config), "staging_preflight_failed")
            account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
            token = os.environ["CLOUDFLARE_API_TOKEN"]
            module.private_bucket(account, token)
            module.deployed_bindings(account, token, config)
        elif script == "ensure_route.py" and args == ("--all-absent",):
            require(module.audit_all_absent(os.environ["CLOUDFLARE_ZONE_ID"],
                                            os.environ["CF_EMAIL_ROUTING_TOKEN"]) == "absent",
                    "staging_preflight_failed")
        else:
            raise ProbeFailure("staging_preflight_failed")
    except (OSError, ValueError, RuntimeError, KeyError, AttributeError, TypeError):
        raise ProbeFailure("staging_preflight_failed") from None
    finally:
        urllib.request.urlopen = prior_urlopen


def call(method: str, path: str, token: str, data: bytes | None = None,
         content_type: str | None = None) -> tuple[int, bytes]:
    """Make one bounded REST request, with neither redirect nor automatic retry."""

    headers = {"Authorization": "Bearer " + token, "Accept": "*/*"}
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(API + path, data=data, method=method,
                                     headers=headers)
    try:
        with OPENER.open(request, timeout=25) as response:
            raw = response.read(MAX_REPLY + 1)
            require(len(raw) <= MAX_REPLY, "r2_response_oversize")
            return response.status, raw
    except urllib.error.HTTPError as error:
        # Do not read or log provider error bodies; status alone is diagnostic.
        return error.code, b""
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProbeFailure("r2_outcome_ambiguous") from None


def object_path(account: str, key: str) -> str:
    """Keep the documented path's slash literal and constrain every other byte."""

    require(KEY.fullmatch(key) is not None, "r2_key_invalid")
    return f"/accounts/{account}/r2/buckets/{BUCKET}/objects/{key}"


def upload_body() -> bytes:
    """Encode the REST API's required multipart ``body`` file field."""

    return (f"--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"body\"; "
            "filename=\"sentinel.bin\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + \
        SENTINEL + f"\r\n--{BOUNDARY}--\r\n".encode()


def upload(account: str, key: str, token: str) -> None:
    """Require a matching Cloudflare success envelope; never repeat a PUT."""

    status, raw = call("PUT", object_path(account, key), token, upload_body(),
                       f"multipart/form-data; boundary={BOUNDARY}")
    if status == 403:
        raise ProbeFailure("r2_put_denied")
    require(status == 200, "r2_put_ambiguous")
    try:
        value = json.loads(raw)
        result = value.get("result")
        valid = (value.get("success") is True and isinstance(result, dict)
                 and result.get("key") == key and str(result.get("size")) == str(len(SENTINEL)))
    except (ValueError, AttributeError, TypeError):
        valid = False
    require(valid, "r2_put_ambiguous")


def observed(account: str, key: str, token: str) -> str:
    """Resolve the exact key as owned sentinel or absent via GET and full LIST."""

    status, raw = call("GET", object_path(account, key), token)
    if status == 200:
        require(raw == SENTINEL, "r2_object_mismatch")
        return "present"
    if status == 404:
        require(key not in object_inventory(account, token), "r2_absence_ambiguous")
        return "absent"
    raise ProbeFailure("r2_get_denied" if status == 403 else "r2_get_ambiguous")


def delete(account: str, key: str, token: str) -> None:
    """Issue one exact-key DELETE; an uncertain outcome needs readback first."""

    status, raw = call("DELETE", object_path(account, key), token)
    if status == 403:
        raise ProbeFailure("r2_delete_denied")
    require(status in (200, 204), "r2_delete_ambiguous")
    if status == 200 and raw:
        try:
            value = json.loads(raw)
            result = value.get("result")
            require(value.get("success") is True and isinstance(result, dict)
                    and result.get("key") in (None, key), "r2_delete_ambiguous")
        except (ValueError, AttributeError, TypeError):
            raise ProbeFailure("r2_delete_ambiguous") from None


def cleanup(account: str, key: str, token: str, delete_attempted: bool) -> bool:
    """Reconcile before another DELETE; never repeat an ambiguous mutation blind."""

    for _ in range(2):
        try:
            state = observed(account, key, token)
        except Exception:
            if delete_attempted:
                return False
            # A possible PUT needs one bounded exact-key cleanup even if GET
            # is unavailable; the preflight proved this random key absent.
            try:
                delete(account, key, token)
            except Exception:
                return False
            delete_attempted = True
            continue
        if state == "absent":
            return True
        try:
            delete(account, key, token)
        except Exception:
            # The next iteration performs GET/LIST before any further delete.
            pass
        delete_attempted = True
    try:
        return observed(account, key, token) == "absent"
    except Exception:
        return False


def execute() -> None:
    """Perform a one-shot staging probe with fail-closed exact-key cleanup."""

    require(os.environ.get("AMAIL_R2_CAPABILITY_CONFIRM") ==
            "RUN_STAGING_R2_OBJECT_CAPABILITY", "explicit_confirmation_required")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    require(re.fullmatch(r"[0-9a-fA-F]{32}", account) is not None and bool(token)
            and bool(os.environ.get("CF_EMAIL_ROUTING_TOKEN")), "provider_credentials_missing")
    audit("check_config.py", "--live", "--deployed")
    audit("ensure_route.py", "--all-absent")
    baseline = object_inventory(account, token)
    key = f"verification/{uuid.uuid4()}.eml"
    require(KEY.fullmatch(key) is not None and key not in baseline, "r2_key_not_absent")
    # Re-list immediately before PUT. A future concurrent B delivery is held
    # by the same Actions concurrency group, but external writers still exist.
    require(key not in object_inventory(account, token), "r2_key_not_absent")
    put_possible = False
    delete_attempted = False
    failure: ProbeFailure | None = None
    try:
        put_possible = True
        upload(account, key, token)
        require(observed(account, key, token) == "present", "r2_get_mismatch")
        delete_attempted = True
        delete(account, key, token)
        require(observed(account, key, token) == "absent", "r2_delete_ambiguous")
    except ProbeFailure as error:
        failure = error
    except Exception:
        failure = ProbeFailure("r2_outcome_ambiguous")
    finally:
        if put_possible and not cleanup(account, key, token, delete_attempted):
            failure = ProbeFailure("r2_cleanup_unverified")
    if failure:
        raise failure
    print("staging_r2_object_capability_verified")


def main() -> int:
    """Print only fixed labels, even for unexpected errors and provider replies."""

    try:
        execute()
        return 0
    except ProbeFailure as error:
        label = str(error)
        print("staging_r2_object_capability_failed:" +
              (label if re.fullmatch(r"[a-z][a-z0-9_]{2,100}", label)
               else "unexpected_failure"), file=sys.stderr)
    except Exception:
        print("staging_r2_object_capability_failed:unexpected_failure", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
