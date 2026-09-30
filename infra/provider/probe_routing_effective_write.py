"""Exercise one valid, disabled staging Email Routing rule and remove it.

The manual probe and its independent recovery mode share an exact HMAC-derived
alias. All provider bodies, rule IDs, aliases, and credentials stay in memory;
only fixed labels and numeric Cloudflare status/error codes reach job logs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import urllib.error
import urllib.request


API = "https://api.cloudflare.com/client/v4"
ZONE = "6edff81c6ed02f412e70868076411a5e"
DOMAIN = "mail-staging.moesegfault.dev"
WORKER = "amail-inbound-staging"
MAX_BODY = 262_144
PAGE_SIZE = 50
MAX_PAGES = 200
PROBE_CONFIRM = "CREATE_ONE_DISABLED_STAGING_ROUTING_PROBE"
RECOVER_CONFIRM = "RECOVER_ONE_STAGING_ROUTING_PROBE"
AUDIT_CONFIRM = "AUDIT_ONE_STAGING_ROUTING_PROBE"


class ProbeFailure(Exception):
    """Carry only a fixed diagnostic code, never provider text."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Keep the scoped routing bearer on the exact Cloudflare API origin."""

    def redirect_request(self, request: urllib.request.Request, file: object, code: int, message: str, headers: object, newurl: str) -> None:
        """Treat any API redirect as a failed response, not a credential transfer."""

        return None


_NO_REDIRECT = urllib.request.build_opener(NoRedirect())


def coordinates(mode: str, confirm: str, run: str, attempt: str) -> None:
    """Gate both entry points before reading a bearer credential."""

    expected = {"probe": PROBE_CONFIRM, "recover": RECOVER_CONFIRM, "audit": AUDIT_CONFIRM}.get(mode)
    if expected is None or confirm != expected:
        raise ProbeFailure("confirmation_required")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run) or not re.fullmatch(r"[1-9][0-9]{0,2}", attempt):
        raise ProbeFailure("coordinates_invalid")


def identity(secret: str, run: str, attempt: str) -> tuple[str, str]:
    """Construct a private, run-recoverable non-user alias and exact owner name."""

    digest = hmac.new(
        secret.encode("utf-8"), f"amail-routing-write-probe/v1:{run}:{attempt}".encode("ascii"), hashlib.sha256
    ).hexdigest()[:32]
    alias = f"probe-{digest}@{DOMAIN}"
    return alias, f"amail probe {alias}"


def _codes(payload: dict) -> str:
    """Render only the first numeric provider error code, never messages."""

    errors = payload.get("errors")
    if not isinstance(errors, list):
        return "none"
    for entry in errors:
        code = entry.get("code") if isinstance(entry, dict) else None
        if type(code) is int and 0 <= code <= 999999:
            return str(code)
    return "none"


def call(method: str, path: str, token: str, body: dict | None = None) -> tuple[int, dict]:
    """Bound Cloudflare JSON responses and suppress network/provider exception text."""

    data = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{API}{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with _NO_REDIRECT.open(request, timeout=20) as response:
            status, raw = response.status, response.read(MAX_BODY + 1)
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read(MAX_BODY + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, {}
    if len(raw) > MAX_BODY:
        return status, {}
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return status, {}
    return status, parsed if isinstance(parsed, dict) else {}


def inventory(token: str) -> list[dict]:
    """Read every page with stable exact pagination, rejecting partial inventories."""

    found: list[dict] = []
    seen_ids: set[str] = set()
    total: int | None = None
    for page in range(1, MAX_PAGES + 1):
        status, payload = call("GET", f"/zones/{ZONE}/email/routing/rules?per_page={PAGE_SIZE}&page={page}", token)
        batch, info = payload.get("result"), payload.get("result_info")
        if status != 200 or payload.get("success") is not True or not isinstance(batch, list) or not isinstance(info, dict):
            raise ProbeFailure(f"inventory_http_{status}")
        available, count, per_page, page_number = (info.get(k) for k in ("total_count", "count", "per_page", "page"))
        if (
            type(available) is not int or not 0 <= available <= 10_000 or
            type(count) is not int or count != len(batch) or
            type(per_page) is not int or per_page != PAGE_SIZE or
            type(page_number) is not int or page_number != page or
            total is not None and available != total or
            not all(isinstance(rule, dict) for rule in batch)
        ):
            raise ProbeFailure("inventory_invalid")
        total = available
        pages = max(1, (available + PAGE_SIZE - 1) // PAGE_SIZE)
        reported_pages = info.get("total_pages")
        if (reported_pages is not None and (type(reported_pages) is not int or
                reported_pages != pages and not (available == 0 and reported_pages == 0))):
            raise ProbeFailure("inventory_invalid")
        if page > pages or count != min(PAGE_SIZE, max(0, available - (page - 1) * PAGE_SIZE)):
            raise ProbeFailure("inventory_invalid")
        for rule in batch:
            rule_id = rule.get("id")
            if (not isinstance(rule_id, str) or re.fullmatch(r"[a-f0-9]{1,32}", rule_id) is None or
                    rule_id in seen_ids):
                raise ProbeFailure("inventory_invalid")
            seen_ids.add(rule_id)
        found.extend(batch)
        if page == pages:
            if len(found) != available:
                raise ProbeFailure("inventory_invalid")
            return found
    raise ProbeFailure("inventory_too_large")


def target_rules(rules: list[dict], alias: str, name: str) -> tuple[list[dict], int]:
    """Find both alias and name collisions; reject malformed inventory entries."""

    matched: list[dict] = []
    staging_count = 0
    for rule in rules:
        matchers = rule.get("matchers")
        actions = rule.get("actions")
        if not isinstance(matchers, list) or not isinstance(actions, list):
            raise ProbeFailure("inventory_invalid")
        for action in actions:
            if not isinstance(action, dict) or not isinstance(action.get("type"), str):
                raise ProbeFailure("inventory_invalid")
            value = action.get("value")
            if value is not None and (not isinstance(value, list) or not all(isinstance(item, str) for item in value)):
                raise ProbeFailure("inventory_invalid")
        alias_hit = False
        staging_hit = False
        for matcher in matchers:
            if not isinstance(matcher, dict):
                raise ProbeFailure("inventory_invalid")
            kind, field, value = matcher.get("type"), matcher.get("field"), matcher.get("value")
            if not isinstance(kind, str) or field is not None and not isinstance(field, str) or value is not None and not isinstance(value, str):
                raise ProbeFailure("inventory_invalid")
            if kind == "literal" and field == "to" and isinstance(value, str):
                if value.lower().endswith("@" + DOMAIN):
                    staging_hit = True
                alias_hit |= value.lower() == alias
        staging_count += int(staging_hit)
        if alias_hit or rule.get("name") == name:
            matched.append(rule)
    return matched, staging_count


def owned(rule: dict, alias: str, name: str) -> bool:
    """Require the entire probe identity before deleting any rule."""

    return (
        isinstance(rule.get("id"), str) and re.fullmatch(r"[a-f0-9]{1,32}", rule["id"]) is not None and
        rule.get("name") == name and rule.get("enabled") is False and rule.get("source") == "api" and
        rule.get("matchers") == [{"type": "literal", "field": "to", "value": alias}] and
        rule.get("actions") == [{"type": "worker", "value": [WORKER]}]
    )


def cleanup(token: str, alias: str, name: str, expected_id: str | None = None) -> str:
    """Delete only one exact owned rule after GET-by-ID confirmation and readback."""

    matches, _ = target_rules(inventory(token), alias, name)
    if not matches:
        return "absent"
    if len(matches) != 1 or not owned(matches[0], alias, name):
        raise ProbeFailure("recovery_ownership_unverified")
    rule_id = matches[0]["id"]
    if expected_id is not None and rule_id != expected_id:
        raise ProbeFailure("recovery_id_mismatch")
    status, payload = call("GET", f"/zones/{ZONE}/email/routing/rules/{rule_id}", token)
    if (status != 200 or payload.get("success") is not True or
            not isinstance(payload.get("result"), dict) or
            payload["result"].get("id") != rule_id or not owned(payload["result"], alias, name)):
        raise ProbeFailure(f"recovery_get_http_{status}")
    status, payload = call("DELETE", f"/zones/{ZONE}/email/routing/rules/{rule_id}", token)
    if status != 204 and (status != 200 or payload.get("success") is not True):
        # A timed-out DELETE may have committed. Reconcile by list; never
        # replay the destructive request against a changed control plane.
        matches, _ = target_rules(inventory(token), alias, name)
        if not matches:
            return "absent_after_ambiguous_delete"
        raise ProbeFailure(f"recovery_delete_http_{status}_codes_{_codes(payload)}")
    matches, _ = target_rules(inventory(token), alias, name)
    if matches:
        raise ProbeFailure("recovery_absence_unverified")
    return "removed"


def probe(token: str, alias: str, name: str) -> tuple[str, str]:
    """Create exactly one disabled valid Worker route and always attempt cleanup."""

    matches, count = target_rules(inventory(token), alias, name)
    if matches:
        raise ProbeFailure("probe_alias_not_absent")
    if count > 198:
        raise ProbeFailure("staging_route_capacity_low")
    body = {
        "name": name, "enabled": False, "source": "api",
        "matchers": [{"type": "literal", "field": "to", "value": alias}],
        "actions": [{"type": "worker", "value": [WORKER]}],
    }
    # Exactly one POST. Finally also runs on failed/ambiguous responses and
    # readback failures; cancellation still requires the separate recovery job.
    outcome = "create_outcome_uncertain"
    cleanup_allowed = True
    expected_id: str | None = None
    denied = False
    denial_absent = False
    try:
        status, payload = call("POST", f"/zones/{ZONE}/email/routing/rules", token, body)
        denied = 400 <= status < 500 or payload.get("success") is False
        if denied:
            cleanup_allowed = False
        result = payload.get("result")
        if (status in (200, 201) and payload.get("success") is True and isinstance(result, dict) and
                isinstance(result.get("id"), str) and re.fullmatch(r"[a-f0-9]{1,32}", result["id"])):
            expected_id = result["id"]
        created = status in (200, 201) and payload.get("success") is True and isinstance(result, dict) and owned(result, alias, name)
        kind = "rejected" if status in (401, 403) else (
            "create_outcome_uncertain" if status == 0 or status in (200, 201) else "unverified"
        )
        outcome = "created" if created else f"{kind}_http_{status}_codes_{_codes(payload)}"
        matches, _ = target_rules(inventory(token), alias, name)
        if denied:
            denial_absent = not matches
        if created and (len(matches) != 1 or not owned(matches[0], alias, name)):
            outcome = "create_readback_unverified"
        if created and len(matches) == 1 and owned(matches[0], alias, name) and matches[0]["id"] != result["id"]:
            outcome = "create_id_mismatch"
            cleanup_allowed = False
        if denied and matches:
            outcome = "create_denial_conflict"
        if not created and matches:
            if cleanup_allowed:
                outcome = "create_outcome_uncertain"
    except ProbeFailure:
        if outcome == "created":
            outcome = "create_readback_unverified"
    except Exception:
        if outcome == "created":
            outcome = "create_readback_unverified"
    finally:
        if not cleanup_allowed:
            removed = "absent_after_denial" if denied and denial_absent else (
                "frozen_after_denial" if denied else "frozen_ownership"
            )
        else:
            try:
                removed = cleanup(token, alias, name, expected_id)
            except ProbeFailure as error:
                removed = "frozen_ownership" if str(error) == "recovery_id_mismatch" else f"failed_{error}"
            except Exception:
                removed = "unverified"
    return outcome, removed


def main(argv: list[str] | None = None) -> int:
    """Emit only fixed labels/status codes; recovery is separate from creation."""

    argv = sys.argv if argv is None else argv
    try:
        if len(argv) != 5:
            raise ProbeFailure("arguments_invalid")
        _, mode, confirm, run, attempt = argv
        coordinates(mode, confirm, run, attempt)
        secret, token = os.environ.get("STAGING_E2E_PASSWORD", ""), os.environ.get("CF_EMAIL_ROUTING_TOKEN", "")
        if not 15 <= len(secret) <= 128 or not token or os.environ.get("CF_ZONE_ID") != ZONE:
            raise ProbeFailure("configuration_invalid")
        alias, name = identity(secret, run, attempt)
        if mode == "audit":
            matches, _ = target_rules(inventory(token), alias, name)
            print(f"routing_write_audit={'absent' if not matches else 'present'}")
            return 0 if not matches else 1
        if mode == "recover":
            print(f"routing_write_recovery={cleanup(token, alias, name)}")
            return 0
        if run != os.environ.get("GITHUB_RUN_ID") or attempt != os.environ.get("GITHUB_RUN_ATTEMPT"):
            raise ProbeFailure("probe_coordinates_not_current_run")
        outcome, removed = probe(token, alias, name)
        print(f"routing_write_probe={outcome}")
        print(f"routing_write_cleanup={removed}")
        print("routing_write_audit=pending")
        return 0 if outcome == "created" and removed == "removed" else 1
    except ProbeFailure as error:
        label = str(error)
        print(f"routing_write_probe_failed={label if re.fullmatch(r'[a-z0-9_,]+', label) else 'unverified'}")
        return 1
    except Exception:
        print("routing_write_probe_failed=unverified")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
