"""Structured control-plane spans without provider bodies, SQL, URLs or credentials.

These are correlated operation records, not proof of native Cloudflare tracing.
Source/run coordinates and CF-Ray connect a provider request to hosted execution.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
import re
import time
from urllib.parse import urlsplit
import uuid

_TRACE_ID = uuid.uuid4().hex
_PARENT: ContextVar[str | None] = ContextVar("control_plane_parent", default=None)


@dataclass
class Facts:
    """Source-owned operational fields; never assign raw provider/user text here."""
    http_status: int | None = None
    cf_ray: str | None = None
    process_exit_code: int | None = None
    version: str | None = None
    version_count: int | None = None
    reason: str | None = None
    error_type: str | None = None
    schema_field: str | None = None
    schema_expected: str | None = None
    schema_actual_type: str | None = None
    provider_error_codes: list[int] | None = None


def endpoint(suffix: str) -> dict:
    """Retain reviewed infrastructure coordinates, never query/body or unknown paths."""
    path = urlsplit(suffix).path
    patterns = (
        (r"/accounts/([0-9a-f]{32})/workers/scripts", "workers.scripts", ("account_id",)),
        (r"/accounts/([0-9a-f]{32})/workers/scripts/([A-Za-z0-9_-]{1,63})/settings",
         "workers.settings", ("account_id", "script_name")),
        (r"/accounts/([0-9a-f]{32})/workers/domains", "workers.domains", ("account_id",)),
        (r"/accounts/([0-9a-f]{32})/d1/database/([0-9a-f-]{36})/query",
         "d1.query", ("account_id", "database_id")),
        (r"/zones/([0-9a-f]{32})/workers/routes", "workers.routes", ("zone_id",)),
        (r"/zones/([0-9a-f]{32})", "zones.get", ("zone_id",)),
    )
    for pattern, family, keys in patterns:
        match = re.fullmatch(pattern, path)
        if match:
            return {"endpoint": family, **dict(zip(keys, match.groups()))}
    return {"endpoint": "unclassified"}


def response_facts(facts: Facts, status: object, headers: object) -> None:
    """Extract only observed numeric status and the provider's operational request ID."""
    if type(status) is int and 100 <= status <= 599:
        facts.http_status = status
    ray = headers.get("cf-ray") if hasattr(headers, "get") else None
    if isinstance(ray, str) and re.fullmatch(r"[A-Za-z0-9-]{1,64}", ray):
        facts.cf_ray = ray


def _context() -> dict:
    """Project hosted coordinates only; the environment may also contain secrets."""
    result = {}
    for field, variable, pattern in (
        ("source_sha", "GITHUB_SHA", r"[0-9a-f]{40}"),
        ("run_id", "GITHUB_RUN_ID", r"[0-9]+"),
        ("run_attempt", "GITHUB_RUN_ATTEMPT", r"[0-9]+"),
        ("job", "GITHUB_JOB", r"[A-Za-z0-9_-]{1,100}"),
    ):
        value = os.getenv(variable, "")
        if re.fullmatch(pattern, value):
            result[field] = value
    return result


def _emit(event: dict) -> None:
    """Diagnostic transport failure must not change or replay a provider operation."""
    try:
        print(json.dumps(event, sort_keys=True), flush=True)
    except OSError:
        pass


@contextmanager
def span(operation: str, phase: str, **coordinates):
    """Emit one bounded operation's start/end, preserve its result and never retry.

    Callers pass static operation/phase and reviewed public infrastructure fields.
    Exception type is useful; exception text/args/tracebacks can contain secrets
    and never enter the receipt. Timing is monotonic; UTC enables log joins.
    """
    allowed = {"method", "realm", "component", "endpoint", "account_id", "zone_id", "database_id", "script_name"}
    if coordinates.keys() - allowed:
        raise ValueError("unreviewed_trace_coordinate")
    base = {"schema": "control-plane-span/v1", **_context(),
            "trace_id": _TRACE_ID, "span_id": uuid.uuid4().hex[:16],
            "parent_span_id": _PARENT.get(), "operation": operation,
            "phase": phase, **coordinates}
    started = time.monotonic()
    token = _PARENT.set(base["span_id"])
    facts = Facts()
    _emit({**base, "event": "control_plane_start",
           "started_at": datetime.now(timezone.utc).isoformat()})
    outcome = "success"
    try:
        yield facts
    except BaseException as error:
        outcome = "failure"
        if facts.error_type is None:
            facts.error_type = type(error).__name__
        raise
    finally:
        _PARENT.reset(token)
        fields = {key: value for key, value in asdict(facts).items() if value is not None}
        _emit({**base, **fields, "event": "control_plane_end", "outcome": outcome,
               "finished_at": datetime.now(timezone.utc).isoformat(),
               "duration_ms": round((time.monotonic() - started) * 1000, 3)})
