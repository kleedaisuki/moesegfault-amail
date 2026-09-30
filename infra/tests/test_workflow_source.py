"""Synthetic regression contracts for insertion-safe workflow job extraction."""

import unittest

from workflow_source import job_block, jobs


class WorkflowSourceTests(unittest.TestCase):
    """Unrelated jobs must neither satisfy nor contaminate safety assertions."""

    def test_adjacent_job_cannot_contaminate_secret_or_guard_contract(self) -> None:
        """A newly inserted credential-bearing job remains outside its neighbor."""
        source = (
            "name: synthetic\njobs:\n"
            "  read-only:\n    if: manual\n    steps:\n"
            "      - name: nested\n        run: |\n          echo safe\n"
            "  unrelated_new:\n    if: automatic\n"
            "    env:\n      TOKEN: ${{ secrets.UNRELATED }}\n"
            "  old-successor:\n    runs-on: ubuntu-latest\n"
            "permissions:\n  contents: read\n"
        )
        block = job_block(source, "read-only")
        self.assertIn("if: manual", block)
        self.assertIn("echo safe", block)
        self.assertNotIn("secrets.", block)
        self.assertNotIn("if: automatic", block)
        self.assertEqual(set(jobs(source)), {"read-only", "unrelated_new", "old-successor"})
        self.assertNotIn("permissions:", job_block(source, "old-successor"))
        self.assertEqual(job_block(source.replace("\n", "\r\n"), "read-only"), block)
        changed = source.replace("    if: manual\n", "").replace("    if: automatic\n", "    if: manual\n")
        self.assertNotIn("if: manual", job_block(changed, "read-only"))

    def test_missing_and_duplicate_jobs_fail_closed(self) -> None:
        """Malformed fixtures cannot silently substitute an adjacent safety job."""
        for source, target in (
            ("jobs:\n  other:\n    if: manual\n", "missing"),
            ("jobs:\n  same:\n    if: first\n  same:\n    if: second\n", "same"),
            ("jobs:\n  same:\n    if: first\njobs:\n  same:\n    if: second\n", "same"),
            ("jobs:\n  same:\n    if: manual\n  inline: {}\n", "same"),
            ("name: no-jobs\n", "missing"),
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                job_block(source, target)

    def test_unsupported_sibling_cannot_supply_missing_guard(self) -> None:
        """Quoted keys and shallow layout must fail, not extend the target body."""
        prefix = "jobs:\n  read-only:\n    runs-on: ubuntu-latest\n"
        for header in (
            '  "unrelated":\n', "  'unrelated':\n", "  unrelated.key:\n",
            "  unrelated: {}\n", " unrelated:\n", "   unrelated:\n",
            "\tunrelated:\n", "  ? unrelated\n", "  :\n",
        ):
            source = prefix + header + "    if: manual\n"
            with self.subTest(header=header), self.assertRaises(ValueError):
                job_block(source, "read-only")
        plain = prefix + "  unrelated: # valid sibling\n    if: manual\n"
        self.assertNotIn("if: manual", job_block(plain, "read-only"))


if __name__ == "__main__":
    unittest.main()
