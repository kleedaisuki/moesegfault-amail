"""Only exact reviewed native patches and package versions may narrow coverage."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch as mock_patch

ROOT: Path = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/release"))
sys.path.insert(0, str(ROOT / "infra/ci"))
import native_patch as patch
import changes


class NativePatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.before: dict[str, str] = {
            patch.MANIFEST: '[package]\nname="amail"\nversion="0.3.1"\n',
            "Cargo.lock": 'version=4\n[[package]]\nname="amail"\nversion="0.3.1"\n',
            patch.PROFILES: "fn lease() {\n                && !generation.is_empty()\n}\n#[cfg(test)]\nmod tests {}\n",
        }
        self.after: dict[str, str] = {name: source.replace('"0.3.1"', '"0.3.2"')
                                      for name, source in self.before.items()}
        self.after[patch.PROFILES] = "// Permanent generation is opaque.\nfn lease() {\n}\n#[cfg(test)]\nmod tests { /* regression */ }\n"

    def test_exact_lease_and_version_delta_is_admitted(self) -> None:
        patch.validate(self.before, self.after, set(self.after))

    def test_unrelated_runtime_or_dependencies_cannot_narrow_checks(self) -> None:
        with self.assertRaisesRegex(ValueError, "native_patch_runtime_scope_changed"):
            patch.validate(self.before, self.after, set(self.after) | {"crates/amail/src/api.rs"})
        dependency: dict[str, str] = deepcopy(self.after)
        dependency["Cargo.lock"] += '\n[[package]]\nname="new-dependency"\nversion="1.0.0"\n'
        with self.assertRaisesRegex(ValueError, "native_patch_dependencies_changed"):
            patch.validate(self.before, dependency, set(dependency))
        unrelated: dict[str, str] = deepcopy(self.after)
        unrelated[patch.PROFILES] = unrelated[patch.PROFILES].replace("fn lease()", "fn changed()")
        with self.assertRaisesRegex(ValueError, "native_patch_implementation_changed"):
            patch.validate(self.before, unrelated, set(unrelated))

    def test_later_source_delta_falls_back_to_normal_coverage(self) -> None:
        with mock_patch.object(patch, "applies", side_effect=ValueError("native_patch_runtime_scope_changed")):
            self.assertFalse(changes.native_scope("a" * 40))


class ApprovalPatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.before: dict[str, str] = {
            patch.MANIFEST: '[package]\nname="amail"\nversion="0.3.2"\n',
            "Cargo.lock": 'version=4\n[[package]]\nname="amail"\nversion="0.3.2"\n',
            patch.APPROVAL: 'fn respond() {\n    ("Referrer-Policy", "no-referrer"),\n}\n#[cfg(test)]\nmod tests {}\n',
        }
        self.after: dict[str, str] = {name: source.replace('"0.3.2"', '"0.3.3"')
                                      for name, source in self.before.items()}
        self.after[patch.APPROVAL] = self.before[patch.APPROVAL].replace(
            '"no-referrer"', '"same-origin"').replace(
                "mod tests {}", "mod tests { /* browser policy regression */ }")

    def test_exact_header_and_version_delta_is_admitted(self) -> None:
        patch.validate(self.before, self.after, set(self.after))
        selected: patch.Patch = patch.PATCHES["0.3.3"]
        self.assertEqual(selected.base, "e9d91c294c265be85540aa188748bd45110e12b8")
        self.assertEqual(selected.test_filter, "approval::tests::")
        self.assertEqual(selected.acceptance_kind, "approval")

    def test_unchanged_header_and_origin_validation_changes_are_rejected(self) -> None:
        unchanged: dict[str, str] = deepcopy(self.after)
        unchanged[patch.APPROVAL] = self.before[patch.APPROVAL]
        with self.assertRaisesRegex(ValueError, "native_patch_implementation_changed"):
            patch.validate(self.before, unchanged, set(unchanged))
        altered: dict[str, str] = deepcopy(self.after)
        altered[patch.APPROVAL] = altered[patch.APPROVAL].replace("fn respond()", "fn bypass_origin()")
        with self.assertRaisesRegex(ValueError, "native_patch_implementation_changed"):
            patch.validate(self.before, altered, set(altered))

    def test_other_runtime_dependencies_and_wrong_predecessor_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "native_patch_runtime_scope_changed"):
            patch.validate(self.before, self.after, set(self.after) | {patch.PROFILES})
        dependencies: dict[str, str] = deepcopy(self.after)
        dependencies[patch.MANIFEST] += '\n[dependencies]\nunreviewed="1"\n'
        with self.assertRaisesRegex(ValueError, "native_patch_dependencies_changed"):
            patch.validate(self.before, dependencies, set(dependencies))
        predecessor: dict[str, str] = deepcopy(self.before)
        predecessor[patch.MANIFEST] = predecessor[patch.MANIFEST].replace('"0.3.2"', '"0.3.1"')
        with self.assertRaisesRegex(ValueError, "native_patch_version_unverified"):
            patch.validate(predecessor, self.after, set(self.after))


if __name__ == "__main__":
    unittest.main()
