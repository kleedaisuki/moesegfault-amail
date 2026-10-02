"""Recheck same-run public generated modules immediately before a provider write.

The workflow's successful full Worker gate is admission; this module is byte and
identity verification, not an alternative admission or cross-run reuse policy.
No ancestry exemption, fallback rebuild, provider capability or test verdict exists.
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ci"))
import worker_artifact as artifact
from control_plane_trace import span


def require_artifact(component: str) -> None:
    """Match original and installed trees to this checkout/run/compiler manifest.

    All component trees and fixed tracked entry wrappers are verified, not merely
    the selected entrypoint. A post-test wrapper edit cannot add RPC exports.
    Restoring on a fresh hosted runner and rechecking before submit prevents silent
    post-test rebuilds or partially mixed generated output from reaching deploy.
    """
    if component not in ("mail_api", "trace_sink", "mail_ingress", "mail_events", "identity_test_inbox"):
        raise ValueError("artifact_component_unreviewed")
    with span("workers.artifact", "precondition", component=component) as facts:
        facts.reason = "same_run_artifact_required"
        manifest = artifact.FOLDER / "manifest.json"
        if artifact.FOLDER.is_symlink() or manifest.is_symlink() or manifest.stat().st_size > 262144:
            raise ValueError("artifact_manifest_invalid")
        value = json.loads(manifest.read_text(encoding="utf-8"))
        identity = artifact.context()
        if (not isinstance(value, dict) or set(value) != set(identity) | {"files"}
                or any(type(value.get(key)) is not type(expected) or value.get(key) != expected
                       for key, expected in identity.items())):
            facts.reason = "artifact_provenance_mismatch"
            raise ValueError("artifact_provenance_mismatch")
        hashes = artifact.files(artifact.FOLDER)
        names = {path.relative_to(artifact.FOLDER).as_posix()
                 for path in artifact.FOLDER.rglob("*") if path.is_file()}
        if (value["files"] != hashes or names != set(hashes) | {"manifest.json"}
                or artifact.files(artifact.ROOT) != hashes):
            facts.reason = "artifact_file_integrity_mismatch"
            raise ValueError("artifact_file_integrity_mismatch")
        facts.reason = "same_run_artifact_verified"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=("mail_api", "trace_sink", "mail_ingress", "mail_events", "identity_test_inbox"))
    require_artifact(parser.parse_args().component)
