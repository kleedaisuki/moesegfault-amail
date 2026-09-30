"""Format non-secret pins only after a successful hosted deployment/privacy check.

This formatter is not an independent verification oracle. Its workflow step must
follow the exact sink isolation check or actual retained-record canary, with no
intervening mutation. Historical consumers require that enclosing job to succeed.
"""

from __future__ import annotations

import argparse
import os
import re

UUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}\Z")
ID = re.compile(r"[0-9a-f]{32}\Z")
DEPLOY_MARKER = "staging_trace_sink_attestation="
CANARY_MARKER = "staging_trace_sink_privacy_attestation="


def format_attestation(kind: str, source: str, sink: str, queue: str, dlq: str) -> str:
    """Reject malformed pins and distinguish config evidence from bounded privacy."""
    if (kind not in ("sink-deploy", "sink-canary") or UUID.fullmatch(sink) is None
            or ID.fullmatch(queue) is None or ID.fullmatch(dlq) is None or queue == dlq):
        raise ValueError("attestation_pins_unverified")
    if kind == "sink-deploy":
        return f"{DEPLOY_MARKER}deploy-v1 sink={sink} queue={queue} dlq={dlq}"
    if UUID.fullmatch(source) is None:
        raise ValueError("attestation_pins_unverified")
    return f"{CANARY_MARKER}bounded-v1 source={source} sink={sink} queue={queue} dlq={dlq}"


def main() -> int:
    """Print one exact provenance marker; no secret or provider data is accepted."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("sink-deploy", "sink-canary"), required=True)
    args = parser.parse_args()
    try:
        marker = format_attestation(args.kind, os.getenv("AMAIL_EXPECTED_WORKER_VERSION", ""),
                                   os.getenv("AMAIL_EXPECTED_TRACE_SINK_VERSION", ""),
                                   os.getenv("AMAIL_TRACE_QUEUE_ID", ""),
                                   os.getenv("AMAIL_TRACE_DLQ_ID", ""))
    except ValueError:
        print("trace_rollout_attestation=UNVERIFIED")
        return 1
    print(marker)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
