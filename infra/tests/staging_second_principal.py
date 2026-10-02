"""Private Identity verification inbox used by the owned production-user journey.

This module retains bounded read and exact-object cleanup helpers, not the retired
staging principal registration/recovery command. No credentials or MIME are logged.
"""

from __future__ import annotations


from datetime import datetime, timezone


from email import policy


from email.parser import BytesParser


from email.utils import getaddresses, parsedate_to_datetime


import json


import re


import time


import urllib.error


import urllib.parse


import urllib.request


ADDRESS = "amail-e2e-isolation@moesegfault.dev"


BUCKET = "amail-identity-test-inbox-staging"


API = "https://api.cloudflare.com/client/v4"


KEY = re.compile(r"verification/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\.eml\Z")


class ProvisionFailure(Exception):
    """A fixed source-owned, non-sensitive failure label."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward the Cloudflare bearer capability to another origin."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Reject all redirects, including same-origin redirects."""

        return None


OPENER = urllib.request.build_opener(NoRedirect())


def require(condition: bool, label: str) -> None:
    """Fail without emitting any sensitive provider or message material."""

    if not condition:
        raise ProvisionFailure(label)


def request(method: str, path: str, token: str, data: bytes | None = None,
            limit: int = 65_536) -> bytes:
    """Perform one bounded Cloudflare API request with no redirect/retry."""

    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "*/*",
                 **({"Content-Type": "application/json"} if data is not None else {})},
    )
    try:
        with OPENER.open(req, timeout=25) as response:
            raw = response.read(limit + 1)
            require(response.status in (200, 204) and len(raw) <= limit, "cloudflare_response_invalid")
            return raw
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        raise ProvisionFailure("cloudflare_request_failed") from None


def json_result(raw: bytes) -> object:
    """Require a successful Cloudflare envelope without logging its contents."""

    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ProvisionFailure("cloudflare_json_invalid") from None
    require(isinstance(value, dict) and value.get("success") is True,
            "cloudflare_envelope_invalid")
    return value


def object_inventory(account: str, token: str) -> set[str]:
    """List UUID-keyed MIME by strict keyset order until an explicit empty page.

    REST ``result_info`` is optional; a short page does not prove completion.
    Always request the next lexicographic slice after the last validated key.
    """

    keys: set[str] = set()
    last: str | None = None
    for _ in range(20):
        query = "?prefix=verification/&per_page=100"
        if last is not None:
            query += "&start_after=" + urllib.parse.quote(last, safe="")
        raw = request("GET", f"/accounts/{account}/r2/buckets/{BUCKET}/objects{query}", token,
                      limit=262_144)
        value = json_result(raw)
        batch = value.get("result")
        require(isinstance(batch, list), "r2_result_invalid")
        require(len(batch) <= 100, "r2_page_size_invalid")
        info = value.get("result_info")
        if "result_info" in value:
            require(isinstance(info, dict), "r2_result_info_invalid")
            if "is_truncated" in info:
                require(type(info["is_truncated"]) is bool, "r2_result_info_invalid")
        if not batch:
            require(not (isinstance(info, dict) and info.get("is_truncated") is True),
                    "r2_empty_page_truncated")
            return keys
        for item in batch:
            require(isinstance(item, dict), "r2_object_entry_invalid")
            key = item.get("key")
            require(isinstance(key, str) and KEY.fullmatch(key) is not None,
                    "r2_object_key_invalid")
            require(key not in keys, "r2_duplicate_key")
            require(last is None or key > last, "r2_key_order_invalid")
            keys.add(key)
            require(len(keys) <= 1000, "r2_inventory_too_large")
            last = key
    raise ProvisionFailure("r2_page_limit")


def verification_code(raw: bytes) -> str:
    """Extract only one code from a single exact-recipient Identity text part."""

    require(0 < len(raw) <= 65_536, "verification_mime_size")
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
        sender = message["From"]
        recipient = message["To"]
        date = message["Date"]
        senders = getaddresses([str(sender)]) if sender is not None else []
        recipients = getaddresses([str(recipient)]) if recipient is not None else []
        require(len(senders) == 1 and senders[0][1].lower() == "identity@moesegfault.dev"
                and len(recipients) == 1 and recipients[0][1].lower() == ADDRESS
                and date is not None, "verification_provenance_invalid")
        timestamp = parsedate_to_datetime(str(date))
        require(timestamp.tzinfo is not None and
                abs((datetime.now(timezone.utc) - timestamp).total_seconds()) <= 600,
                "verification_time_invalid")
        parts = [p for p in message.walk() if p.get_content_type() == "text/plain"
                 and p.get_content_disposition() != "attachment"]
        require(len(parts) == 1, "verification_text_ambiguous")
        body = parts[0].get_content()
        match = re.findall(r"Verification code: ([0-9]{8})(?![0-9])", body)
        require(len(match) == 1 and f"Address: {ADDRESS}" in body,
                "verification_code_ambiguous")
        return match[0]
    except (UnicodeError, ValueError, TypeError, KeyError):
        raise ProvisionFailure("verification_mime_invalid") from None


def guarded_code(account: str, token: str, baseline: set[str], started: float) -> str:
    """Poll one new private object; never return an unvetted or stale OTP."""

    deadline = min(started + 8 * 60, time.monotonic() + 150)
    while time.monotonic() < deadline:
        new = object_inventory(account, token) - baseline
        require(len(new) <= 1, "verification_delivery_ambiguous")
        if new:
            key = next(iter(new))
            raw = request("GET", f"/accounts/{account}/r2/buckets/{BUCKET}/objects/{key}",
                          token, limit=65_536)
            return verification_code(raw)
        time.sleep(5)
    raise ProvisionFailure("verification_delivery_timeout")
