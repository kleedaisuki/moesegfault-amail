"""Only the reviewed lease guard and native package version may narrow coverage."""
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


if __name__ == "__main__":
    unittest.main()
