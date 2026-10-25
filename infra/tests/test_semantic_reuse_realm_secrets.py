"""The staging receiver and synthetic fixture must never receive the production key."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RealmSecretTests(unittest.TestCase):
    def block(self, name: str) -> str:
        source = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        found = re.search(rf"(?ms)^  {name}:\n.*?(?=^  [a-z][a-z0-9-]*:|\Z)", source)
        self.assertIsNotNone(found)
        return found.group() if found is not None else ""

    def test_staging_receiver_and_fixture_use_only_the_staging_secret(self) -> None:
        block = self.block("semantic-reuse-staging")
        self.assertIn("INGRESS_SECRET: ${{ secrets.INGRESS_SECRET_STAGING }}", block)
        self.assertNotIn("INGRESS_SECRET: ${{ secrets.INGRESS_SECRET }}", block)
        self.assertNotIn("INGRESS_SECRET", self.block("semantic-reuse-journey"))

    def test_production_receiver_retains_its_original_production_secret(self) -> None:
        block = self.block("semantic-reuse-production")
        self.assertIn("INGRESS_SECRET: ${{ secrets.INGRESS_SECRET }}", block)
        self.assertNotIn("INGRESS_SECRET_STAGING", block)


if __name__ == "__main__":
    unittest.main()
