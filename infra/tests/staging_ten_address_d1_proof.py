"""Explicit hosted D1 schema/provider proof; synthetic mirror state only.

This does not dispatch quota acceptance, authenticate a real mailbox owner,
create an alias, send mail, finalize a real recovery, or access a recovery key.
Real escrow DDL is applied only by the separately confirmed apply-schema mode.
Synthetic terminal metadata lives exclusively in staging_d1_probe_* tables.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

import staging_ten_address_escrow as escrow
import staging_ten_address_manifest as manifest
from staging_second_principal import json_result, request
from staging_ten_address_acceptance import checkout
from staging_ten_address_provenance import mail_pin, successful_source
from staging_worker_created_r2 import github_json

require = manifest.require
PREFIX = "staging_d1_probe_"
ORIGINAL = "staging_acceptance_"
WORKFLOW = ".github/workflows/staging-ten-address-d1-proof.yml"
GENERATION = "synthetic-d1-provider-v1"
KEY = "a7" * 32  # Public fixture key; NEVER use with an actual recovery manifest.
CONFIRMS = {"inspect": "INSPECT_STAGING_D1_READ_ONLY",
            "apply-schema": "APPLY_STAGING_D1_ESCROW_SCHEMA",
            "write-synthetic": "WRITE_STAGING_D1_SYNTHETIC_ONLY",
            "read-terminal": "READ_TERMINAL_STAGING_D1_SYNTHETIC_ONLY"}
SCHEMA_SQL = "SELECT name,type,sql FROM sqlite_master WHERE substr(name,1,?)=? AND sql IS NOT NULL ORDER BY name"
HELD_SQL = "SELECT state FROM send_policy WHERE scope='global' AND owner_iss='*' AND owner_sub='*'"
PROBE_SQL = {kind: sql.replace(ORIGINAL, PREFIX) for kind, sql in escrow.SQL.items() if kind != "purge"}


def schema_objects(prefix: str) -> dict[str, tuple[str, str]]:
    """Derive the mirror only by renaming reviewed objects; no second DDL model."""
    require(prefix in (ORIGINAL, PREFIX), "d1_proof_namespace_invalid")
    return {name.replace(ORIGINAL, prefix): (kind, sql.replace(ORIGINAL, prefix))
            for name, (kind, sql) in escrow.expected_schema().items()}


def schema_observation(rows: list[dict], prefix: str) -> dict[str, tuple[str, str]]:
    """Parse exact namespaced DDL; parameter transport shape never weakens equality."""
    require(prefix in (ORIGINAL, PREFIX), "d1_proof_namespace_invalid")
    observed = {}
    for row in rows:
        require(set(row) == {"name", "type", "sql"}
                and all(isinstance(row[key], str) for key in row)
                and row["name"].startswith(prefix) and row["name"] not in observed,
                "d1_proof_schema_unverified")
        observed[row["name"]] = (row["type"], re.sub(r"\s+", " ", row["sql"]).strip().removesuffix(";"))
    return observed


class Provider:
    """Bound native REST operations to exact staging DB and source-owned statements."""

    def __init__(self, account: str, token: str):
        """Require protected capabilities; callers cannot choose DB, table, or SQL."""
        require(isinstance(account, str) and re.fullmatch(r"[a-f0-9]{32}", account) is not None
                and isinstance(token, str) and bool(token), "d1_proof_capability_invalid")
        self.account, self._token = account, token
        self._allowed = {SCHEMA_SQL, HELD_SQL, *PROBE_SQL.values()}
        self._ddl = {sql for prefix in (ORIGINAL, PREFIX) for kind, sql in schema_objects(prefix).values()}

    def query(self, sql: str, params: tuple = (), *, migration: bool = False) -> escrow.Result:
        """One bounded query without redirects/retries; ambiguous writes stop."""
        require(isinstance(sql, str) and sql in (self._ddl if migration else self._allowed)
                and len(sql.encode()) < 16_384 and isinstance(params, tuple) and len(params) <= 100
                and (not migration or params == ()), "d1_proof_query_unreviewed")
        body = json.dumps({"sql": sql, "params": list(params)}).encode()
        require(len(body) < 100_000, "d1_proof_query_bounds")
        try:
            value = json_result(request("POST", f"/accounts/{self.account}/d1/database/{escrow.DB}/query",
                                        self._token, body, limit=escrow.MAX_RESPONSE))
        except Exception:
            raise manifest.ContractFailure("d1_proof_query_unverified") from None
        return escrow.query_result(value)

    def schema(self, prefix: str) -> dict[str, tuple[str, str]]:
        """Compare every namespaced object; never accept IF NOT EXISTS as equality."""
        require(prefix in (ORIGINAL, PREFIX), "d1_proof_namespace_invalid")
        rows = self.query(SCHEMA_SQL, (len(prefix), prefix)).rows
        return schema_observation(rows, prefix)

    def apply(self) -> None:
        """Apply only absent schemas; partial/drifted schemas stop for manual review.

        Each DDL request is separate. A lost acknowledgement or partially applied
        migration is deliberately not repaired by retry, DROP, or rollback.
        """
        for prefix in (ORIGINAL, PREFIX):
            actual = self.schema(prefix)
            require(not actual or actual == schema_objects(prefix), "d1_proof_schema_partial_or_drift")
        for prefix in (ORIGINAL, PREFIX):
            actual = self.schema(prefix)
            require(not actual or actual == schema_objects(prefix), "d1_proof_schema_partial_or_drift")
            if actual:
                continue
            for kind, sql in schema_objects(prefix).values():
                self.query(sql, migration=True)
            require(self.schema(prefix) == schema_objects(prefix), "d1_proof_schema_unverified")

    def provenance(self) -> tuple[str, str]:
        """Pin DB and the exact frozen c3f predecessor contract between stable deployments.

        This D1-only mechanics proof selects historical binding provenance, not
        the current direct-only deployment policy or privacy/send permission.
        """
        def get(path):
            """Fetch one fixed metadata path; private provider errors never escape."""
            try:
                value = json_result(request("GET", f"/accounts/{self.account}/" + path, self._token))
                require(isinstance(value.get("result"), dict), "d1_proof_resource_unverified")
                return value["result"]
            except Exception:
                raise manifest.ContractFailure("d1_proof_resource_unverified") from None
        database = get(f"d1/database/{escrow.DB}")
        require(database.get("uuid") == escrow.DB and database.get("name") == "moesegfault-mail-staging",
                "d1_proof_database_unverified")
        base = "workers/scripts/amail-mail-staging/"
        first = mail_pin.serving_deployment(get(base + "deployments?per_page=1&page=1"))
        require(first is not None, "d1_proof_worker_unverified")
        version = get(base + "versions/" + first[1])
        require(mail_pin.containment_bindings_match(version, first[1]), "d1_proof_binding_unverified")
        require(mail_pin.serving_deployment(get(base + "deployments?per_page=1&page=1")) == first,
                "d1_proof_worker_changed")
        require(self.query(HELD_SQL).rows == [{"state": "held"}], "d1_proof_sending_not_held")
        return first


class SyntheticEscrow(escrow.Escrow):
    """Exercise the escrow implementation against synthetic mirror tables only.

    No purge statement exists in this capability. The mirror's terminal check
    set is a SQL-mechanics fixture, NOT an executed mailbox cleanup attestation.
    """

    def __init__(self, provider: Provider):
        """Keep original escrow invariants while replacing only fixed table names."""
        super().__init__(provider.account, provider._token)
        self._provider = provider

    def _run(self, kind: str, params: tuple = ()) -> escrow.Result:
        """Map source-owned queries; remap schema names only for exact DDL checking."""
        require(kind in PROBE_SQL, "d1_proof_query_unreviewed")
        if kind == "schema":
            rows = self._provider.query(SCHEMA_SQL, (len(PREFIX), PREFIX)).rows
            # Reverse only the fixed namespace, never ciphertext or bound metadata.
            return escrow.Result([{**row, "name": row["name"].replace(PREFIX, ORIGINAL),
                                   "sql": row["sql"].replace(PREFIX, ORIGINAL)} for row in rows], 0)
        return self._provider.query(PROBE_SQL[kind], params)


def fixture(run: str, sha: str) -> dict:
    """Build only invented identities/baseline; require a full chunk and partial tail."""
    objects = {f"synthetic-object-{index:03d}-" + "x" * 900: "b" * 64 for index in range(80)}
    return manifest.build(KEY, run, GENERATION, "synthetic-d1-provider-owner", sha,
                          "00000000-0000-0000-0000-000000000001", 1000,
                          manifest.Snapshot({}, [], 0, objects),
                          {"identity_revision": "00000000-0000-0000-0000-000000000002",
                           "login_revision": "00000000-0000-0000-0000-000000000003",
                           "verified_username": "synthetic_d1_provider", "client_id": "amail-cli-staging"})


def dispatch(run: str, token: str, sha: str | None = None) -> dict:
    """Independently bind current/prior manual proof invocation; no arbitrary run reuse."""
    manifest.coordinates(run, "1")
    value = github_json(f"/repos/{manifest.REPOSITORY}/actions/runs/{run}/attempts/1", token)
    require(value.get("id") == int(run) and value.get("run_attempt") == 1
            and value.get("event") == "workflow_dispatch"
            and value.get("head_branch") == manifest.BRANCH.removeprefix("refs/heads/")
            and value.get("path") in (WORKFLOW, WORKFLOW + "@" + manifest.BRANCH)
            and isinstance(value.get("repository"), dict)
            and value["repository"].get("full_name") == manifest.REPOSITORY
            and isinstance(value.get("head_sha"), str) and re.fullmatch(r"[a-f0-9]{40}", value["head_sha"])
            and (sha is None or value["head_sha"] == sha and value.get("status") == "in_progress"),
            "d1_proof_dispatch_unverified")
    return value


def guard(mode: str) -> None:
    """Reject local/unconfirmed/retried calls before reading any Secret capability."""
    require(mode in CONFIRMS and os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
            and os.environ.get("GITHUB_REPOSITORY") == manifest.REPOSITORY
            and os.environ.get("GITHUB_REF") == manifest.BRANCH
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1"
            and os.environ.get("AMAIL_D1_PROOF_ENVIRONMENT") == "staging"
            and os.environ.get("AMAIL_D1_PROOF_CONFIRM") == CONFIRMS[mode], "d1_proof_dispatch_unconfirmed")
    manifest.coordinates(os.environ.get("GITHUB_RUN_ID", ""), "1")
    prior = os.environ.get("AMAIL_D1_PROOF_PRIOR_RUN", "")
    require((mode in ("read-terminal", "inspect")) == bool(prior), "d1_proof_prior_run_invalid")
    if mode == "inspect":
        from staging_ten_address_d1_inspect import FAILED_RUN
        require(prior == FAILED_RUN, "d1_proof_prior_run_invalid")
        manifest.coordinates(os.environ.get("AMAIL_D1_PROOF_SOURCE_RUN", ""), "1")
    if prior:
        manifest.coordinates(prior, "1")
        require(prior != os.environ["GITHUB_RUN_ID"], "d1_proof_prior_run_invalid")


def execute(mode: str) -> dict:
    """Apply/read/write fixed synthetic proof; real campaign authority is never returned."""
    if mode == "inspect":
        from staging_ten_address_d1_inspect import execute as inspect
        return inspect()
    guard(mode)
    sha = checkout()
    token = os.environ.pop("GITHUB_TOKEN", "")
    dispatch(os.environ["GITHUB_RUN_ID"], token, sha)
    successful_source(os.environ.get("AMAIL_D1_PROOF_SOURCE_RUN", ""), sha, token)
    provider = Provider(os.environ.pop("CLOUDFLARE_ACCOUNT_ID", ""),
                        os.environ.pop("CLOUDFLARE_API_TOKEN", ""))
    pins = provider.provenance()
    evidence = {"mode": mode, "source_sha": sha, "schema_sha256": escrow.hash_bytes(
        manifest.canonical(schema_objects(ORIGINAL))), "synthetic_only": True,
        "real_cleanup_attested": False}
    if mode == "apply-schema":
        provider.apply()
    else:
        require(all(provider.schema(prefix) == schema_objects(prefix) for prefix in (ORIGINAL, PREFIX)),
                "d1_proof_schema_unverified")
        client = SyntheticEscrow(provider)
        run = os.environ.get("AMAIL_D1_PROOF_PRIOR_RUN") or os.environ["GITHUB_RUN_ID"]
        if mode == "write-synthetic":
            require(client.parent(run) is None, "d1_proof_record_preexisting")
            blob = manifest.seal(fixture(run, sha), KEY, run, GENERATION)
            require(escrow.CHUNK < len(blob) < 2 * escrow.CHUNK, "d1_proof_fixture_bounds")
            client.put(blob, KEY, run, GENERATION)
            client.attach(run, KEY, GENERATION, run, blob)  # Synthetic ID, NOT an artifact attestation.
            client.arm(run, KEY, GENERATION, run, blob)  # Result is discarded; no alias callback exists.
        else:
            original = dispatch(run, token)
            require(original.get("status") == "completed", "d1_proof_original_not_completed")
            row, blob = client.read(run, KEY, GENERATION)
            require(manifest.open_manifest(blob, KEY, run, GENERATION) == fixture(run, original["head_sha"])
                    and row["artifact_id"] == run and row["state"] in ("sealed", "armed"),
                    "d1_proof_synthetic_binding_unverified")
            client._finalize(run, KEY, GENERATION, os.environ["GITHUB_RUN_ID"], sha, blob)
            require(client.read(run, KEY, GENERATION)[1] == blob, "d1_proof_terminal_retention_unverified")
        observed, actual = client.read(run, KEY, GENERATION)
        require(actual == blob, "d1_proof_ciphertext_unverified")
        evidence.update({"original_run": run, "original_sha": observed["source_sha"],
                         "envelope_sha256": observed["envelope_sha"], "envelope_bytes": observed["envelope_bytes"],
                         "chunk_count": observed["chunk_count"], "mirror_state": observed["state"],
                         "mirror_receipt_sha256": observed["cleanup_receipt_sha"]})
    require(all(provider.schema(prefix) == schema_objects(prefix) for prefix in (ORIGINAL, PREFIX)),
            "d1_proof_schema_unverified")
    require(provider.provenance() == pins, "d1_proof_provenance_changed")
    evidence["result"] = {"apply-schema": "d1_proof_schema_verified",
                          "write-synthetic": "d1_proof_synthetic_armed_retained",
                          "read-terminal": "d1_proof_cross_dispatch_terminal_ciphertext_retained"}[mode]
    return evidence


def main() -> int:
    """Print fixed labels only, never raw provider errors, params, ciphertext or keys."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=CONFIRMS)
    args = parser.parse_args()
    try:
        evidence = execute(args.mode)
        print(json.dumps(evidence, sort_keys=True))
        if args.mode == "inspect":
            return 0 if evidence["result"] == "d1_proof_inspect_readonly_complete_no_mutation_authority" else 1
        return 0
    except Exception:
        print("d1_proof_failed_retained_no_campaign_authority", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
