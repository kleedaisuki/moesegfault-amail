"""Incident-bound read-only D1 phase diagnosis; never grants mutation authority.

Only fixed provider metadata and schema/global-hold SELECTs are admitted.
Provider responses stay in memory; published evidence is a fixed label map.
"""

from __future__ import annotations

import json
import os
import re

import staging_ten_address_d1_proof as proof
import staging_ten_address_escrow as escrow
import staging_ten_address_manifest as manifest

require = manifest.require
FAILED_RUN = "36787173756"
FAILED_SHA = "242b5abfee461d04188757e8b365d387d46fcdf9"
WORKER = "workers/scripts/amail-mail-staging/"
DEPLOYMENTS = WORKER + "deployments?per_page=1&page=1"
PHASES = ("guard", "checkout", "github_dispatch", "github_failed_apply", "source",
          "capability", "database", "worker", "binding", "held", "formal_schema",
          "mirror_schema", "formal_schema_integer", "formal_schema_numeric_string",
          "mirror_schema_integer", "mirror_schema_numeric_string", "worker_recheck", "held_recheck", "schema_recheck")


class ReadOnlyProvider:
    """Independent least-authority facade; no apply/mirror/DDL capability exists."""

    def __init__(self, account: str, token: str):
        """Keep protected credentials private; bind every call to fixed staging DB."""
        require(isinstance(account, str) and re.fullmatch(r"[a-f0-9]{32}", account) is not None
                and isinstance(token, str) and bool(token), "d1_inspect_capability_unverified")
        self.account, self._token = account, token

    def metadata(self, path: str) -> dict:
        """Read only reviewed DB/deployment/version endpoints, without retries."""
        require(path in (f"d1/database/{escrow.DB}", DEPLOYMENTS)
                or re.fullmatch(re.escape(WORKER + "versions/")
                                + r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}", path) is not None,
                "d1_inspect_metadata_unreviewed")
        value = proof.json_result(proof.request("GET", f"/accounts/{self.account}/" + path, self._token))
        require(value.get("success") is True and isinstance(value.get("result"), dict),
                "d1_inspect_metadata_unverified")
        return value["result"]

    def query(self, sql: str, params: tuple = ()) -> escrow.Result:
        """Admit just two fixed SELECTs and their exact parameters; reject changed rows.

        Native D1 uses POST for SELECT transport. HTTP POST here does not admit
        DDL or data mutation; no user-controlled SQL, parameters or endpoint exist.
        """
        require(type(params) is tuple and ((sql == proof.HELD_SQL and params == ())
                or (sql == proof.SCHEMA_SQL and len(params) == 2 and type(params[0]) in (int, str)
                    and type(params[1]) is str and params in
                    tuple((length, prefix) for prefix in (proof.ORIGINAL, proof.PREFIX)
                          for length in (len(prefix), str(len(prefix)))))),
                "d1_inspect_query_unreviewed")
        body = json.dumps({"sql": sql, "params": list(params)}).encode()
        value = proof.json_result(proof.request("POST", f"/accounts/{self.account}/d1/database/{escrow.DB}/query",
                                               self._token, body, limit=escrow.MAX_RESPONSE))
        result = escrow.query_result(value)
        require(result.changes == 0, "d1_inspect_query_changed_rows")
        return result

    def database(self) -> None:
        """Require the exact independently observed DB UUID and staging name."""
        value = self.metadata(f"d1/database/{escrow.DB}")
        require(value.get("uuid") == escrow.DB and value.get("name") == "moesegfault-mail-staging",
                "d1_inspect_database_unverified")

    def worker(self) -> tuple[str, str]:
        """Require one actual 100%-serving staging deployment/version."""
        pin = proof.mail_pin.serving_deployment(self.metadata(DEPLOYMENTS))
        require(pin is not None, "d1_inspect_worker_unverified")
        return pin

    def binding(self, pin: tuple[str, str]) -> None:
        """Require the serving version's sole D1 binding and no duplicate MAIL_DB."""
        value = self.metadata(WORKER + "versions/" + pin[1])
        resources = value.get("resources")
        bindings = resources.get("bindings") if isinstance(resources, dict) else None
        require(value.get("id") == pin[1] and isinstance(bindings, list)
                and all(isinstance(item, dict) and isinstance(item.get("name"), str) for item in bindings),
                "d1_inspect_binding_unverified")
        databases = [item for item in bindings if item.get("type") == "d1"]
        require(len(databases) == 1 and databases[0].get("name") == "MAIL_DB"
                and databases[0].get("id") == escrow.DB
                and sum(item.get("name") == "MAIL_DB" for item in bindings) == 1,
                "d1_inspect_binding_unverified")

    def held(self) -> None:
        """Require exactly one held global singleton; missing/extra states stop."""
        require(self.query(proof.HELD_SQL).rows == [{"state": "held"}], "d1_inspect_held_unverified")

    def schema(self, prefix: str, *, numeric_string: bool = False) -> dict[str, tuple[str, str]]:
        """Compare integer versus exact decimal-string params without changing SQL.

        These are independently labeled read-only protocol probes, not retries
        of the failed DDL operation. Equality parsing is shared with the proof.
        """
        require(prefix in (proof.ORIGINAL, proof.PREFIX), "d1_inspect_namespace_invalid")
        length = str(len(prefix)) if numeric_string else len(prefix)
        return proof.schema_observation(self.query(proof.SCHEMA_SQL, (length, prefix)).rows, prefix)


def failed_apply(token: str) -> None:
    """Bind inspection to the original failed attempt, never reinterpret its ACK."""
    value = proof.dispatch(FAILED_RUN, token)
    require(value.get("head_sha") == FAILED_SHA and value.get("status") == "completed"
            and value.get("conclusion") == "failure", "d1_inspect_failed_apply_unverified")


def classify_schema(actual: dict, prefix: str) -> str:
    """Empty means absent; every nonexact object set means partial or drift, not safe."""
    if not actual:
        return "absent"
    return "exact" if actual == proof.schema_objects(prefix) else "partial_or_drift"


class Inspection:
    """Keep stage evidence bounded and fixed; failures never render exceptions."""

    def __init__(self):
        """Initialize all phases as unobserved and explicitly deny campaign authority."""
        self.evidence = {"mode": "inspect", "read_only": True, "mutation_authority": False,
                         "real_cleanup_attested": False, "inspected_failed_run": FAILED_RUN,
                         "stages": {phase: "not_checked" for phase in PHASES},
                         "result": "d1_proof_inspect_failed_no_mutation_authority"}

    def stage(self, phase: str, operation):
        """Return a one-element value container on success; None denotes fixed failure."""
        require(phase in PHASES, "d1_inspect_phase_unreviewed")
        try:
            value = operation()
        except Exception:
            self.evidence["stages"][phase] = "unverified"
            return None
        self.evidence["stages"][phase] = "verified"
        return (value,)

    def run(self) -> dict:
        """Stop at the first failed gate, but classify both readable schema namespaces."""
        if self.stage("guard", lambda: proof.guard("inspect")) is None:
            return self.evidence
        checkout = self.stage("checkout", proof.checkout)
        if checkout is None:
            return self.evidence
        sha = checkout[0]
        self.evidence["source_sha"] = sha
        token = os.environ.pop("GITHUB_TOKEN", "")
        if self.stage("github_dispatch", lambda: proof.dispatch(os.environ["GITHUB_RUN_ID"], token, sha)) is None:
            return self.evidence
        if self.stage("github_failed_apply", lambda: failed_apply(token)) is None:
            return self.evidence
        if self.stage("source", lambda: proof.successful_source(os.environ["AMAIL_D1_PROOF_SOURCE_RUN"], sha, token)) is None:
            return self.evidence
        capability = self.stage("capability", lambda: ReadOnlyProvider(os.environ.pop("CLOUDFLARE_ACCOUNT_ID", ""),
                                                                       os.environ.pop("CLOUDFLARE_API_TOKEN", "")))
        if capability is None:
            return self.evidence
        provider = capability[0]
        if self.stage("database", provider.database) is None:
            return self.evidence
        worker = self.stage("worker", provider.worker)
        if worker is None:
            return self.evidence
        pin = worker[0]
        if self.stage("binding", lambda: provider.binding(pin)) is None:
            return self.evidence
        if self.stage("held", provider.held) is None:
            return self.evidence
        observed = {}
        self.evidence["schema_parameter_shapes"] = {}
        for phase, prefix in (("formal_schema", proof.ORIGINAL), ("mirror_schema", proof.PREFIX)):
            integer = self.stage(phase + "_integer", lambda: provider.schema(prefix))
            numeric = self.stage(phase + "_numeric_string", lambda: provider.schema(prefix, numeric_string=True))
            shape = "integer_and_numeric_string" if integer is not None and numeric is not None else (
                "integer_only" if integer is not None else "numeric_string_only" if numeric is not None else "unverified")
            self.evidence["schema_parameter_shapes"][phase] = shape
            if integer is None and numeric is None:
                self.evidence["stages"][phase] = "unverified"
                continue
            if integer is not None and numeric is not None and integer[0] != numeric[0]:
                self.evidence["stages"][phase] = "unverified"
                continue
            actual = integer[0] if integer is not None else numeric[0]
            observed[prefix] = (actual, integer is not None, numeric is not None)
            self.evidence["stages"][phase] = classify_schema(actual, prefix)
        if len(observed) != 2:
            return self.evidence
        if self.stage("worker_recheck", lambda: require(provider.worker() == pin,
                                                       "d1_inspect_worker_changed")) is None:
            return self.evidence
        if self.stage("held_recheck", provider.held) is None:
            return self.evidence
        if self.stage("schema_recheck", lambda: require(all(provider.schema(prefix, numeric_string=shape) == actual
                                                          for prefix, (actual, integer, numeric) in observed.items()
                                                          for shape, admitted in ((False, integer), (True, numeric))
                                                          if admitted),
                                                        "d1_inspect_schema_changed")) is None:
            return self.evidence
        partial = any(self.evidence["stages"][phase] == "partial_or_drift"
                      for phase in ("formal_schema", "mirror_schema"))
        self.evidence["result"] = ("d1_proof_inspect_partial_or_drift_no_mutation_authority" if partial
                                   else "d1_proof_inspect_readonly_complete_no_mutation_authority")
        return self.evidence


def execute() -> dict:
    """Run diagnosis with fixed evidence only; success does not authorize any writer."""
    return Inspection().run()
