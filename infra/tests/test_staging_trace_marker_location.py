"""Synthetic tests for the fixed-label historical marker-location classifier."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_trace_marker_location as target  # noqa: E402


SUFFIX = "a" * 32
PATH_MARKER = f"amail_path_canary_{SUFFIX}"
QUERY_MARKER = f"amail_query_canary_{SUFFIX}"


def row(*, record_id: str = "test-row", kind: str = "cf-worker-log",
        metadata_url: str | None = None, source: object = "{}",
        workers: object = None, timestamp: int = target.START + 1000) -> dict:
    """Build an in-scope synthetic event with optional carrier fields."""

    metadata = {"id": record_id, "service": target.WORKER, "type": kind}
    if metadata_url is not None:
        metadata["url"] = metadata_url
    value = {"$metadata": metadata, "dataset": "cloudflare-workers",
             "source": source, "timestamp": timestamp}
    if workers is not None:
        value["$workers"] = workers
    return value


class MarkerLocationTests(unittest.TestCase):
    """Keep request-derived strings out of every diagnostic result."""

    def test_custom_log_metadata_path_only(self) -> None:
        """Classify the plausible platform-enrichment case, not as a privacy pass."""

        value = row(metadata_url=f"https://test.invalid/v1/messages/{PATH_MARKER}")
        self.assertEqual(target.classify([value]),
                         ("metadata_url", "cf_worker_log", "path_only", "1"))

    def test_invocation_log_full_url_retains_both_components(self) -> None:
        """A shared suffix identifies the path/query pair without returning it."""

        value = row(kind="cf-worker-event",
                    metadata_url=f"https://test.invalid/v1/messages/{PATH_MARKER}?probe={QUERY_MARKER}")
        self.assertEqual(target.classify([value]),
                         ("metadata_url", "cf_worker_event", "both_same_suffix", "1"))

    def test_application_payload_and_workers_enrichment_are_distinct(self) -> None:
        """Do not mistake a source marker for automatic URL metadata."""

        source = row(source={"message": PATH_MARKER})
        workers = row(record_id="other", workers={"event": {"request": {"path": PATH_MARKER}}})
        self.assertEqual(target.classify([source]),
                         ("source_or_message", "cf_worker_log", "path_only", "1"))
        self.assertEqual(target.classify([workers]),
                         ("workers_event_request", "cf_worker_log", "path_only", "1"))
        self.assertEqual(target.classify([source, workers]),
                         ("other_or_multiple", "cf_worker_log", "path_only", "2_plus"))

    def test_mixed_types_are_not_silently_promoted(self) -> None:
        """A genuine event plus a custom log has a fixed mixed type only."""

        first = row(metadata_url=PATH_MARKER)
        second = row(record_id="second", kind="cf-worker-event", metadata_url=PATH_MARKER)
        self.assertEqual(target.classify([first, second]),
                         ("metadata_url", "other_or_mixed", "path_only", "2_plus"))

    def test_truncated_or_malformed_workers_rejects_even_with_a_marker(self) -> None:
        """Partial platform records cannot establish path-only or any other bin."""

        for workers in ({"truncated": True}, {"truncated": "false"},
                        {"truncated": None}, {"truncated": 0}, []):
            with self.subTest(workers=workers):
                with self.assertRaises(target.LocationError):
                    target.classify([row(metadata_url=PATH_MARKER, workers=workers)])
        missing_shape = row(metadata_url=PATH_MARKER)
        missing_shape["$workers"] = None
        with self.assertRaises(target.LocationError):
            target.classify([missing_shape])
        unrelated_truncation = row(record_id="second", workers={"truncated": True})
        with self.assertRaises(target.LocationError):
            target.classify([row(metadata_url=PATH_MARKER), unrelated_truncation])
        self.assertEqual(target.classify([
            row(metadata_url=PATH_MARKER, workers={"truncated": False})]),
            ("metadata_url", "cf_worker_log", "path_only", "1"))

    def test_required_event_envelope_rejects_missing_or_bad_fields(self) -> None:
        """A visible marker in metadata cannot rescue an incomplete event."""

        for key in ("dataset", "source"):
            value = row(metadata_url=PATH_MARKER)
            del value[key]
            with self.subTest(missing=key):
                with self.assertRaises(target.LocationError):
                    target.classify([value])
        for dataset in ("", None, 3):
            value = row(metadata_url=PATH_MARKER)
            value["dataset"] = dataset
            with self.subTest(dataset_type=type(dataset).__name__):
                with self.assertRaises(target.LocationError):
                    target.classify([value])
        for source in (None, [], [PATH_MARKER], 42, True):
            with self.subTest(source_type=type(source).__name__):
                with self.assertRaises(target.LocationError):
                    target.classify([row(metadata_url=PATH_MARKER, source=source)])

    def test_conflicting_or_partial_markers_fail_closed(self) -> None:
        """Unknown suffixes and malformed prefixes cannot be classified as absence."""

        cases = (
            row(metadata_url=f"{PATH_MARKER}?probe=amail_query_canary_{'b' * 32}"),
            row(metadata_url=f"{PATH_MARKER}?probe=amail_query_canary_bad"),
            row(metadata_url=f"{PATH_MARKER}f"),
        )
        for value in cases:
            with self.subTest(value=value["$metadata"]["id"]):
                with self.assertRaises(target.LocationError):
                    target.classify([value])

    def test_scope_keys_and_empty_window_fail_closed(self) -> None:
        """A diagnostic never converts missing or out-of-scope data to a pass."""

        wrong_service = row(metadata_url=PATH_MARKER)
        wrong_service["$metadata"]["service"] = "another-worker"
        with self.assertRaises(target.LocationError):
            target.classify([wrong_service])
        with self.assertRaises(target.LocationError):
            target.classify([row(metadata_url=PATH_MARKER, timestamp=target.END + 1)])
        with self.assertRaises(target.LocationError):
            target.classify([row(source={PATH_MARKER: "value"})])
        with self.assertRaises(target.LocationError):
            target.classify([row(metadata_url=PATH_MARKER), row(metadata_url=PATH_MARKER)])
        with self.assertRaises(target.LocationError):
            target.classify([])

    def test_main_emits_only_fixed_bins_and_never_provider_text(self) -> None:
        """Hosted stdout remains safe even if a query raises arbitrary text."""

        environment = {"CLOUDFLARE_ACCOUNT_ID": "f" * 32,
                       "CLOUDFLARE_API_TOKEN": "private-deploy-token",
                       "CF_OBSERVABILITY_TOKEN": "private-query-token"}
        output = StringIO()
        with patch.dict(target.os.environ, environment), \
                patch.object(target.sys, "argv", ["diagnostic", "--confirm", target.CONFIRM]), \
                patch.object(target, "preflight"), \
                patch.object(target, "retained_events", return_value=[row(metadata_url=PATH_MARKER)]), \
                redirect_stdout(output):
            self.assertEqual(target.main(), 0)
        self.assertEqual(output.getvalue(),
                         "staging_trace_marker_location: CLASSIFIED "
                         "carrier=metadata_url type=cf_worker_log component=path_only records=1\n")
        self.assertNotIn(SUFFIX, output.getvalue())
        output = StringIO()
        with patch.dict(target.os.environ, environment), \
                patch.object(target.sys, "argv", ["diagnostic", "--confirm", target.CONFIRM]), \
                patch.object(target, "preflight"), \
                patch.object(target, "retained_events", side_effect=RuntimeError("private-provider-text")), \
                redirect_stdout(output):
            self.assertEqual(target.main(), 1)
        self.assertEqual(output.getvalue(),
                         "staging_trace_marker_location: UNVERIFIED (query_unverified)\n")


if __name__ == "__main__":
    unittest.main()
