"""Synthetic safety and discrimination contracts; run on hosted CI only."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import staging_trace_marker_discriminator as target
from test_staging_trace_marker_location import PATH_MARKER, QUERY_MARKER, SUFFIX, row



class DiscriminatorTests(unittest.TestCase):
    """Keep unknown leaf names and values private while resolving coarse bins."""

    def test_unknown_single_leaf_is_not_multiple(self) -> None:
        value = row(kind="private-type")
        value["private-key"] = PATH_MARKER
        result = target.discriminate([value])
        self.assertEqual(result["carrier"], "top_level_other")
        self.assertEqual(result["carriers"], "1")
        self.assertEqual(result["leaves"], "1")
        self.assertEqual(result["metadata_type"], "unrecognized")
        self.assertNotIn("private", str(result))

    def test_multiple_carriers_and_same_carrier_leaves_are_distinct(self) -> None:
        value = row(metadata_url=PATH_MARKER, source={"message": PATH_MARKER})
        result = target.discriminate([value])
        self.assertEqual(result["carrier"], "metadata_url+source")
        self.assertEqual(result["carriers"], "2_plus")
        value = row(source={"messages": [PATH_MARKER, PATH_MARKER]})
        result = target.discriminate([value])
        self.assertEqual(result["carriers"], "1")
        self.assertEqual(result["leaves"], "2_plus")

    def test_wrapper_is_exact_and_type_absence_is_not_mixed(self) -> None:
        value = row()
        del value["$metadata"]["type"]
        value["$cloudflare"] = {"$metadata": {"url": PATH_MARKER, "type": "cf-worker-event"}}
        result = target.discriminate([value])
        self.assertEqual(result["carrier"], "cloudflare_metadata_url")
        self.assertEqual(result["metadata_type"], "absent")
        self.assertEqual(result["wrapper_type"], "cf_worker_event")
        value["$cloudflare"] = {"$cloudflare": {"$metadata": {"url": PATH_MARKER}}}
        self.assertEqual(target.discriminate([value])["carrier"], "cloudflare_top_level_other")
        value["$metadata"]["type"] = ["secret"]
        self.assertEqual(target.discriminate([value])["metadata_type"], "malformed")

    def test_documented_context_and_diagnostics_do_not_become_unknown(self) -> None:
        value = row(workers={"diagnosticsChannelEvents": [{"message": PATH_MARKER}],
                             "eventType": "fetch"})
        value["$metadata"]["transactionName"] = PATH_MARKER
        result = target.discriminate([value])
        self.assertEqual(result["carrier"], "metadata_context+workers_diagnostic_channel")
        self.assertEqual(result["trigger"], "fetch")
        value["$workers"]["eventType"] = "private-trigger"
        self.assertEqual(target.discriminate([value])["trigger"], "unrecognized")

    def test_every_returned_record_still_passes_existing_fail_closed_gates(self) -> None:
        good = row(metadata_url=PATH_MARKER)
        for bad in (
            row(record_id="bad", workers={"truncated": True}),
            row(record_id="bad", timestamp=target.first.END + 1),
            row(record_id="bad", source={PATH_MARKER: "secret"}),
            row(record_id="bad", metadata_url=QUERY_MARKER.replace(SUFFIX, "b" * 32)),
            good,
        ):
            with self.subTest(shape=type(bad).__name__):
                with self.assertRaises(target.first.LocationError):
                    target.discriminate([good, bad])
        for flag in (True, 0, "false", None):
            bad = row(record_id="bad")
            bad["$cloudflare"] = {"$workers": {"truncated": flag}}
            with self.assertRaises(target.first.LocationError):
                target.discriminate([good, bad])

    def test_main_has_no_raw_exception_or_value_output_and_same_window(self) -> None:
        env = {"CLOUDFLARE_ACCOUNT_ID": "f" * 32,
               "CF_OBSERVABILITY_TOKEN": "secret", "CLOUDFLARE_API_TOKEN": "secret"}
        for response in ([row(metadata_url=PATH_MARKER)], RuntimeError("private-exception")):
            output = StringIO()
            kwargs = {"side_effect": response} if isinstance(response, Exception) else {"return_value": response}
            with patch.dict(target.os.environ, env), patch.object(sys, "argv", [
                    "diagnostic", "--confirm", target.CONFIRM]), \
                    patch.object(target.first, "preflight") as preflight, \
                    patch.object(target.first, "retained_events", **kwargs) as query, \
                    redirect_stdout(output):
                target.main()
            preflight.assert_called_once()
            query.assert_called_once_with("f" * 32, "secret", target.first.START, target.first.END)
            for private in (SUFFIX, "private-exception", "secret", PATH_MARKER):
                self.assertNotIn(private, output.getvalue())

if __name__ == "__main__":
    unittest.main()
