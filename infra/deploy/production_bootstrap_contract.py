"""Accountable, bounded production bootstrap admission without a pristine claim.

Current inventory is not universal historical absence. These source-derived
resource and held-state contracts are inspection facts, not a drain admission,
first deployment authorization, or an additional human Secret-management process.
No send, release, Cron or global unhold is authorized here.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
PRODUCTION = "mail.moesegfault.dev"
ISSUER = "https://identity.moesegfault.dev"


@dataclass(frozen=True)
class ProductionResources:
    """Reviewed checked-in production capability identities; never caller origins."""

    database: str
    bucket: str
    source_sha: str
    api: str = "amail-mail"
    issuer: str = ISSUER
    client: str = "amail-cli"
    domain: str = PRODUCTION

    def validate(self) -> None:
        """Reject staging, invalid source pins, and arbitrary external realm overrides."""
        if (not all(isinstance(value, str) for value in (self.database, self.source_sha, self.bucket))
                or not UUID.fullmatch(self.database) or not SHA.fullmatch(self.source_sha)
                or not re.fullmatch(r"moesegfault-mail-raw-production(?:-[a-f0-9]{16,32})?", self.bucket)
                or self.api != "amail-mail" or self.issuer != ISSUER
                or self.client != "amail-cli" or self.domain != PRODUCTION):
            raise ValueError("production_resources_unverified")



def stable_digest(snapshot: dict) -> str:
    """Hash private canonical facts; callers never print raw capability identities."""
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def held_state(policy: list[dict], gates: list[dict], journals: list[dict],
               reservations: list[dict], object_count: int) -> None:
    """Admit only held/no-grant/no-journal/no-reservation first bootstrap facts.

    Used or ambiguous retained state requires a different reviewed recovery
    operation. Zero counts are necessary here, never a pristine/history label.
    Any future outbound acceptance must use a separate one-key grant contract.
    """
    if policy != [{"state": "held"}]:
        raise ValueError("bootstrap_hold_unverified")
    zero = {"feedback_verified": 0, "abuse_contact_verified": 0,
            "delivery_canary_verified": 0, "preview_reviewed": 0, "live_grant": 0}
    if gates != [zero] or any(type(value) is not int for value in gates[0].values()):
        raise ValueError("bootstrap_grant_or_release_gate_unverified")
    if (journals != [{"n": 0}] or reservations != [{"n": 0}]
            or type(journals[0].get("n")) is not int or type(reservations[0].get("n")) is not int
            or type(object_count) is not int or object_count != 0):
        raise ValueError("bootstrap_retained_state_requires_reconciliation")
