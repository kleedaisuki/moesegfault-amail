"""不调用 OpenRouter 即验证探针判定。 / Validate probe checks without API calls."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "provider" / "probe_openrouter.py"
SPEC = importlib.util.spec_from_file_location("probe_openrouter", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ProbeOpenRouterTest(unittest.TestCase):
    """拒绝错误维度和无效数值。 / Reject wrong dimensions and invalid values."""

    def test_accepts_finite_256d_vector(self) -> None:
        """接受有效向量。 / Accept a valid vector."""

        MODULE.validate({"data": [{"embedding": [0.1] * 256}]})

    def test_rejects_ignored_dimensions(self) -> None:
        """识别提供商忽略 256 维请求。 / Detect ignored dimensionality."""

        with self.assertRaisesRegex(ValueError, "expected 256"):
            MODULE.validate({"data": [{"embedding": [0.1] * 4096}]})

    def test_rejects_non_finite(self) -> None:
        """避免非有限值污染余弦索引。 / Prevent non-finite cosine index values."""

        with self.assertRaisesRegex(ValueError, "non-finite"):
            MODULE.validate({"data": [{"embedding": [float("nan")] + [0.1] * 255}]})


if __name__ == "__main__":
    unittest.main()
