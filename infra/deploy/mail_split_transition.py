"""Small closed product state/rollback contract, not a generic scheduler.

An operator record is provenance, not proof of HTTP quiescence or authorization.
This module deliberately has no provider writer or environment-only drain bypass.
Protected execution consumes an independently admitted record; uncertain drain
always selects paused. Normal code rollback never changes script-level triggers.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from check_mail_maintenance import CADENCE, REALMS, script_name


class State(str, Enum):
    """Persistent product graph states; do not infer them from latest inventory."""
    LEGACY_PINNED = "legacy-pinned"
    PREPARED = "prepared"
    OLD_DRAINING = "old-draining"
    PAUSED = "paused"
    ACTIVE = "active"
    NEW_DRAINING = "new-draining"
    LEGACY_RECOVERY = "legacy-recovery"


@dataclass(frozen=True)
class Plan:
    """One fixed successor with an exact script/cadence, never an arbitrary API URL."""
    successor: State
    topology: str
    script: str | None
    crons: tuple[str, ...] | None


def transition(realm: str, state: State, operation: str, *, admission: str = "UNVERIFIED") -> Plan:
    """Derive allowed edges; a named protected disposition is not self-asserted drain.

    Provider writers must independently verify protected admission provenance.
    No writer is exported by this module. The source-only release admits none.
    """
    if realm not in REALMS or not isinstance(state, State):
        raise ValueError("split_state_unreviewed")
    edges = {
        (State.LEGACY_PINNED, "prepare"): (State.PREPARED, "maintenance", ()),
        (State.PREPARED, "stop-old"): (State.OLD_DRAINING, "api", ()),
        (State.OLD_DRAINING, "hold"): (State.PAUSED, None, None),
        (State.NEW_DRAINING, "hold"): (State.PAUSED, None, None),
        (State.PAUSED, "activate"): (State.ACTIVE, "maintenance", CADENCE),
        (State.ACTIVE, "pause"): (State.NEW_DRAINING, "maintenance", ()),
        (State.PAUSED, "replace-api"): (State.PAUSED, None, None),
        (State.ACTIVE, "replace-api"): (State.ACTIVE, None, None),
        (State.PAUSED, "replace-sink"): (State.PAUSED, None, None),
        (State.ACTIVE, "replace-sink"): (State.ACTIVE, None, None),
        (State.PAUSED, "replace-maintenance"): (State.PAUSED, None, None),
        (State.ACTIVE, "replace-maintenance"): (State.ACTIVE, None, None),
    }
    selected = edges.get((state, operation))
    admitted = {"production-first-fenced-bootstrap", "provider-attested-old-work-end"}
    if selected is None or (operation == "activate" and admission not in admitted):
        raise ValueError("split_transition_unreviewed")
    successor, target, crons = selected
    script = None if target is None else script_name(realm, maintenance=target == "maintenance")
    return Plan(successor, "api-scheduled", script, crons)


def normal_replacement(realm: str, state: str, owner: str) -> Plan:
    """Legacy/draining states cannot reach a normal deploy or implicit Cron restore."""
    try:
        selected = State(state)
    except ValueError as error:
        raise ValueError("split_state_unreviewed") from error
    return transition(realm, selected, "replace-" + owner)

