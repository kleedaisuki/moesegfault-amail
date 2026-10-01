"""Cache evidence retains actual lookup state, not a green-step inference."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/ci"))
import cache_event


class CacheEventTests(unittest.TestCase):
    """A missing output or partial match is not an exact hit or proven cold cache."""

    def test_exact_non_exact_and_unknown_are_distinct(self):
        for value, state in (("true", "exact_hit"), ("false", "non_exact_or_miss"), ("", "unreported"),
                             ("provider-secret", "unreported")):
            with self.subTest(value=value):
                event = cache_event.event("worker-dependencies", value)
                self.assertEqual(event["lookup"], state)
                self.assertNotIn("provider-secret", str(event))
        with self.assertRaises(ValueError):
            cache_event.event("unreviewed", "true")


if __name__ == "__main__":
    unittest.main()
