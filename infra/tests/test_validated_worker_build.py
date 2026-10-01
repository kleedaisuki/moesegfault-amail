"""Hosted artifact admission tests, stronger than diagnostic-only replay."""

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import validated_worker_build as build

SHA = "a" * 40


def fixture():
    """One fully successful exact-main source run and fixed producer artifact."""
    run = {"id":123, "run_attempt":1, "path":".github/workflows/ci.yml", "status":"completed",
           "conclusion":"success", "head_branch":"main", "head_sha":SHA, "event":"push"}
    rows = [{"name":name,"conclusion":"success"} for name in build.REQUIRED]
    jobs = {"jobs":rows,"total_count":len(rows)}
    artifacts = {"total_count":1,"artifacts":[{"name":"worker-native-modules-"+SHA,"id":789,"expired":False}]}
    return run,jobs,artifacts


class ValidatedWorkerBuildTests(unittest.TestCase):
    """A green producer alone cannot admit deployment and source drift cannot borrow CI."""

    def test_exact_main_all_checks_and_fixed_artifact(self):
        self.assertEqual(build.identity(*fixture(), SHA),
                         {"source_sha":SHA,"run_id":"123","run_attempt":1,"artifact_id":789})

    def test_failed_partial_pr_or_wrong_source_run_refused(self):
        for field, value in [("conclusion","failure"),("head_branch","codex/example"),
                             ("head_sha","b"*40),("event","pull_request"),("status","in_progress")]:
            run,jobs,artifacts=fixture();run[field]=value
            with self.assertRaises(ValueError):build.identity(run,jobs,artifacts,SHA)
        for name in build.REQUIRED:
            run,jobs,artifacts=fixture()
            next(row for row in jobs["jobs"] if row["name"]==name)["conclusion"]="skipped"
            with self.assertRaises(ValueError):build.identity(run,jobs,artifacts,SHA)

    def test_reuse_changes_are_narrowly_non_build_only(self):
        self.assertEqual(build.build_changes(list(build.NON_BUILD_FILES) + ["docs/result.md", ".agents/skills/amail/SKILL.md"]), [])
        for path in ("Cargo.lock", "rust-toolchain.toml", "crates/mail-worker/src/lib.rs",
                     "workers/native-trace-canary/wrangler.toml", "infra/ci/worker_artifact.py",
                     "infra/tests/worker-boundary/trace-sink.test.mjs", ".github/workflows/ci.yml",
                     "infra/deploy/other.py", "new-unknown-file"):
            self.assertEqual(build.build_changes([path]), [path])

    def test_expired_ambiguous_artifact_and_partial_inventory_refused(self):
        for mode in ("expired","duplicate","partial_jobs","partial_artifacts"):
            run,jobs,artifacts=fixture()
            if mode=="expired":artifacts["artifacts"][0]["expired"]=True
            if mode=="duplicate":artifacts["artifacts"]*=2;artifacts["total_count"]=2
            if mode=="partial_jobs":jobs["total_count"]+=1
            if mode=="partial_artifacts":artifacts["total_count"]+=1
            with self.assertRaises(ValueError):build.identity(run,jobs,artifacts,SHA)


if __name__ == "__main__":unittest.main()
