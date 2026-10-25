"""Bind each reviewed staging candidate to its own explicit confirmation.

These coordinates select only the existing isolated staging graph. Historical
resume and production controllers retain their independently pinned contracts.
"""
from __future__ import annotations

LANES: dict[str, tuple[str, str]] = {
    "refs/heads/codex/v0.2.0-billing": ("RUN_STAGING_V020", "INSPECT_STAGING_V020"),
    "refs/heads/codex/v0.3.0-multitenant": ("RUN_STAGING_V030", "INSPECT_STAGING_V030"),
    "refs/heads/codex/v0.3.1-semantic-consent": ("RUN_STAGING_V031", "INSPECT_STAGING_V031"),
}


def reviewed(ref: str, confirmation: str, *, read_only: bool = False) -> bool:
    lane = LANES.get(ref)
    return lane is not None and confirmation == lane[int(read_only)]
