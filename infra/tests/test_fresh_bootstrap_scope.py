"""Hosted synthetic storage/transport/config contracts; never access a provider."""

from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).parents[1] / "deploy"))
import fresh_bootstrap_scope as fresh
from fresh_bootstrap_contract import Epoch, Scope, ORIGINAL_DATABASE, STAGING_DATABASE

EPOCH = Epoch("a" * 40, "123", 42, "b" * 64, "1.90.0")
DATABASE = "c8f64bb6-748b-4a97-9d37-310be3f0d523"
TIME = "2026-10-01T12:34:56.123456Z"


def envelope(result, info=None):
    """Create a successful CF envelope without real credentials or requests."""
    value = {"success": True, "errors": [], "result": result}
    if info is not None:
        value["result_info"] = info
    return value


class FakeProvider:
    """In-memory source-owned API with durable pre-submit intent assertions."""

    account = "a" * 32

    def __init__(self, journal):
        """Every write checks the already persisted matching intent event."""
        self.journal = journal
        self.calls = []
        self.d1_inventory = envelope([], {"page": 1, "per_page": 1000, "count": 0, "total_count": 0})
        self.r2_inventory = envelope({"buckets": []}, {"per_page": 1000})
        self.database = {"uuid": DATABASE, "name": EPOCH.database_name, "created_at": TIME}
        self.bucket = {"name": EPOCH.bucket_name, "creation_date": TIME}
        self.fail_create = None
        self.drift = False

    def envelope(self, method, path, body=None):
        """Return complete synthetic inventory, not failed-read-as-empty fixtures."""
        self.calls.append((method, path))
        return copy.deepcopy(self.d1_inventory if "/d1/" in path else self.r2_inventory)

    def post(self, path, body):
        """Verify intent was on disk before simulating the one write submission."""
        self.calls.append(("POST", path))
        database = path.endswith("/d1/database")
        records = [json.loads(line) for line in self.journal.read_text().splitlines()]
        expected = "d1_submit_intent" if database else "r2_submit_intent"
        if records[-1]["event"] != expected or body != {"name": EPOCH.database_name if database else EPOCH.bucket_name}:
            raise AssertionError("write intent must precede submission")
        if self.fail_create:
            raise fresh.FreshError(self.fail_create)
        return copy.deepcopy(self.database if database else self.bucket)

    def get(self, path):
        """One exact identity read; optional drift must remain a failure."""
        self.calls.append(("GET", path))
        value = copy.deepcopy(self.database if "/d1/" in path else self.bucket)
        if self.drift:
            value["name"] = "unowned-name"
        return value


class FreshScopeTests(unittest.TestCase):
    """Positive creation, exact ownership and preserved external config contracts."""

    def setUp(self):
        """Keep every fixture under the repository's owned .temp directory."""
        folder = fresh.ROOT / ".temp"
        folder.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=folder, prefix="fresh-scope-test-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.journal = self.folder / "scope.jsonl"
        self.provider = FakeProvider(self.journal)

    def test_complete_absence_intent_create_and_exact_readback(self):
        """Both inventories precede any create; successful timestamps are provider-owned."""
        scope = fresh.create_scope(self.provider, EPOCH, self.journal)
        self.assertEqual(scope, Scope(EPOCH, DATABASE, "2026-10-01T12:34:56Z", "2026-10-01T12:34:56Z"))
        self.assertEqual([method for method, _ in self.provider.calls], ["GET", "GET", "POST", "GET", "POST", "GET"])
        records = [json.loads(line) for line in self.journal.read_text().splitlines()]
        self.assertEqual(records[0]["epoch"]["source_sha"], EPOCH.source_sha)
        self.assertFalse(records[0]["may_replay_write"])
        self.assertEqual(records[-1]["event"], "scope_readback_verified")
        self.assertNotIn(ORIGINAL_DATABASE, self.journal.read_text())

    def test_existing_journal_refuses_before_any_provider_operation(self):
        """A partial previous invocation cannot be automatically replayed."""
        self.journal.write_text("partial")
        with self.assertRaises(FileExistsError):
            fresh.create_scope(self.provider, EPOCH, self.journal)
        self.assertEqual(self.provider.calls, [])

    def test_inventory_failures_never_become_absence(self):
        """Missing metadata, failed envelope, bad count and duplicate IDs stop writes."""
        invalid = [envelope([]), {"success": False, "errors": [], "result": []},
                   envelope([], {"page": 1, "per_page": 1000, "count": False, "total_count": 0}),
                   envelope([], {"page": 1, "per_page": 1000, "count": 0, "total_count": 1})]
        for index, value in enumerate(invalid):
            with self.subTest(index=index):
                journal = self.folder / f"invalid-{index}.jsonl"
                provider = FakeProvider(journal)
                provider.d1_inventory = value
                with self.assertRaises(fresh.FreshError):
                    fresh.create_scope(provider, EPOCH, journal)
                self.assertFalse(any(method == "POST" for method, _ in provider.calls))

    def test_existing_derived_name_is_not_adopted(self):
        """A correct name in inventory is still an existing store, not fresh proof."""
        self.provider.d1_inventory = envelope([self.provider.database], {"page": 1, "per_page": 1000, "count": 1, "total_count": 1})
        with self.assertRaisesRegex(fresh.FreshError, "existing_refused"):
            fresh.create_scope(self.provider, EPOCH, self.journal)
        self.assertFalse(any(method == "POST" for method, _ in self.provider.calls))

    def test_r2_incomplete_or_existing_blocks_first_post(self):
        """Missing bucket rows or malformed metadata cannot establish absence."""
        for index, value in enumerate((envelope({}), envelope({"buckets": []}, {"per_page": False}),
                                      envelope({"buckets": [self.provider.bucket]}, {"per_page": 1000}))):
            journal = self.folder / f"r2-{index}.jsonl"
            provider = FakeProvider(journal)
            provider.r2_inventory = value
            with self.assertRaises(fresh.FreshError):
                fresh.create_scope(provider, EPOCH, journal)
            self.assertFalse(any(method == "POST" for method, _ in provider.calls))

    def test_r2_optional_metadata_and_server_page_limit_follow_documented_cursor_contract(self):
        """Successful explicit bucket rows remain complete after every cursor terminates."""
        for index, info in enumerate((None, {}, {"cursor": ""}, {"per_page": 20})):
            with self.subTest(info=info):
                journal = self.folder / f"r2-optional-{index}.jsonl"
                provider = FakeProvider(journal)
                provider.r2_inventory = envelope({"buckets": [{"name": "unrelated"}]}, info)
                fresh.create_scope(provider, EPOCH, journal)
                self.assertEqual(sum(method == "POST" for method, _ in provider.calls), 2)

        self.provider.envelope = Mock(side_effect=[self.provider.d1_inventory,
            envelope({"buckets": [{"name": "unrelated"}]}, {"cursor": "next", "per_page": 20}),
            envelope({"buckets": []})])
        fresh._absence(self.provider, EPOCH)
        self.assertEqual(self.provider.envelope.call_count, 3)
        self.assertIn("cursor=next", self.provider.envelope.call_args.args[1])

    def test_inventory_pagination_is_complete_and_duplicate_free(self):
        """All D1 pages and R2 cursor pages finish before a positive absence verdict."""
        d1 = {"uuid": DATABASE, "name": "unrelated-database"}
        buckets = {"name": "unrelated-bucket"}
        pages = [envelope([d1], {"page": 1, "per_page": 1000, "count": 1, "total_count": 2}),
                 envelope([{"uuid": "d8f64bb6-748b-4a97-9d37-310be3f0d523", "name": "another"}],
                          {"page": 2, "per_page": 1000, "count": 1, "total_count": 2}),
                 envelope({"buckets": [buckets]}, {"per_page": 1000, "cursor": "next"}),
                 envelope({"buckets": []}, {"per_page": 1000})]
        self.provider.envelope = Mock(side_effect=pages)
        fresh._absence(self.provider, EPOCH)
        self.assertEqual(self.provider.envelope.call_count, 4)
        self.assertIn("cursor=next", self.provider.envelope.call_args.args[1])
        self.provider.envelope = Mock(side_effect=[pages[0], envelope([d1],
            {"page": 2, "per_page": 1000, "count": 1, "total_count": 2})])
        with self.assertRaises(fresh.FreshError):
            fresh._absence(self.provider, EPOCH)

    def test_cursor_cycle_and_count_drift_fail_closed(self):
        """A repeating cursor or changed total cannot hide a partial inventory."""
        r2 = envelope({"buckets": [{"name": "unrelated"}]}, {"per_page": 1000, "cursor": "cycle"})
        self.provider.envelope = Mock(side_effect=[self.provider.d1_inventory, r2,
            envelope({"buckets": [{"name": "other"}]}, {"per_page": 1000, "cursor": "cycle"})])
        with self.assertRaises(fresh.FreshError):
            fresh._absence(self.provider, EPOCH)

    def test_second_create_failure_retains_successful_first_coordinates(self):
        """Partial provision retains new D1 recovery facts without deleting it."""
        original = self.provider.post
        def post(path, body):
            """Simulate one R2 transport ambiguity after successful exact D1 readback."""
            if path.endswith("/r2/buckets"):
                self.provider.fail_create = "fresh_write_ambiguous"
            return original(path, body)
        self.provider.post = post
        with self.assertRaisesRegex(fresh.FreshError, "write_ambiguous"):
            fresh.create_scope(self.provider, EPOCH, self.journal)
        result = fresh.reconcile_scope(self.provider, EPOCH, self.journal)
        self.assertEqual(result["database"], "CREATED_IDENTITY_OBSERVED")
        self.assertEqual(result["bucket"], "UNKNOWN")
        self.assertEqual(sum(method == "POST" for method, _ in self.provider.calls), 2)

    def test_create_conflict_and_timeout_are_recovery_only_no_retry(self):
        """An ambiguous single write retains intent but grants neither UUID nor replay."""
        for index, reason in enumerate(("fresh_write_ambiguous", "fresh_create_existing_refused")):
            journal = self.folder / f"failure-{index}.jsonl"
            provider = FakeProvider(journal)
            provider.fail_create = reason
            with self.assertRaisesRegex(fresh.FreshError, reason):
                fresh.create_scope(provider, EPOCH, journal)
            self.assertEqual(sum(method == "POST" for method, _ in provider.calls), 1)
            result = fresh.reconcile_scope(provider, EPOCH, journal)
            self.assertEqual(result["database"], "UNKNOWN")
            self.assertFalse(result["may_replay_write"])

    def test_readback_drift_prevents_second_create(self):
        """A response is not sufficient without exact follow-up identity agreement."""
        self.provider.drift = True
        with self.assertRaises(fresh.FreshError):
            fresh.create_scope(self.provider, EPOCH, self.journal)
        self.assertEqual(sum(method == "POST" for method, _ in self.provider.calls), 1)
        self.assertIn('"event":"d1_created"', self.journal.read_text())

    def test_original_and_staging_database_response_refused(self):
        """A matching name cannot disguise an old or staging UUID."""
        for value in (ORIGINAL_DATABASE, STAGING_DATABASE):
            self.provider.database["uuid"] = value
            with self.assertRaises(fresh.FreshError):
                fresh._identity(self.provider.database, EPOCH, True)

    def test_provider_timestamp_validation_never_invents_time(self):
        """UTC fractional precision may normalize; malformed/non-UTC times cannot."""
        self.assertEqual(fresh._timestamp(TIME), "2026-10-01T12:34:56Z")
        for value in (None, "2026-02-30T12:34:56Z", "2026-10-01T12:34:56+01:00", "2026-10-01", "now"):
            with self.assertRaises(fresh.FreshError):
                fresh._timestamp(value)

    def test_readonly_reconcile_never_grants_adoption_or_absence(self):
        """Successful recovery reads observe known creates, not permission to write."""
        fresh.create_scope(self.provider, EPOCH, self.journal)
        self.provider.calls.clear()
        observed = fresh.reconcile_scope(self.provider, EPOCH, self.journal)
        self.assertEqual(observed["database"], "CREATED_IDENTITY_OBSERVED")
        self.assertEqual(observed["bucket"], "CREATED_IDENTITY_OBSERVED")
        self.assertEqual(observed["adoption"], "NOT_GRANTED")
        self.assertTrue(all(method == "GET" for method, _ in self.provider.calls))
        self.provider.get = Mock(side_effect=fresh.FreshError("fresh_provider_http_failure"))
        observed = fresh.reconcile_scope(self.provider, EPOCH, self.journal)
        self.assertEqual(observed["database"], "UNKNOWN")
        self.assertEqual(observed["bucket"], "UNKNOWN")

    def test_recovery_journal_epoch_and_event_order_are_closed(self):
        """An invented create without the owned preceding intent is not recovery proof."""
        fresh.create_scope(self.provider, EPOCH, self.journal)
        records = [json.loads(line) for line in self.journal.read_text().splitlines()]
        records.pop(1)
        self.journal.write_text("\n".join(json.dumps(row) for row in records))
        self.provider.calls.clear()
        with self.assertRaisesRegex(fresh.FreshError, "journal_unverified"):
            fresh.reconcile_scope(self.provider, EPOCH, self.journal)
        self.assertEqual(self.provider.calls, [])

    def test_render_preserves_staging_and_changes_only_reviewed_fields(self):
        """No source rebuild, route override, secret value or Cron activation is added."""
        scope = Scope(EPOCH, DATABASE, "2026-10-01T12:34:56Z", "2026-10-01T12:34:56Z")
        paths = fresh.render_configs(scope, self.folder / "configs")
        self.assertEqual(set(paths), {"api", "maintenance"})
        for key, path in paths.items():
            source = fresh.ROOT / "crates/mail-worker" / path.name
            original = tomllib.loads(source.read_text())
            updated = tomllib.loads(path.read_text())
            self.assertEqual(updated["env"], original["env"])
            self.assertEqual(updated["routes"], original["routes"])
            self.assertEqual(updated["triggers"]["crons"], [])
            self.assertTrue(Path(updated["main"]).is_absolute())
            self.assertEqual(updated["d1_databases"][0]["database_id"], DATABASE)
            self.assertEqual(updated["r2_buckets"][0]["bucket_name"], EPOCH.bucket_name)
            expected = copy.deepcopy(original)
            expected["main"] = updated["main"]
            expected["d1_databases"][0].update(database_id=DATABASE, database_name=EPOCH.database_name)
            expected["r2_buckets"][0]["bucket_name"] = EPOCH.bucket_name
            if key == "api":
                expected["preview_urls"] = False
                self.assertIs(updated["preview_urls"], False)
                expected["d1_databases"][0]["migrations_dir"] = updated["d1_databases"][0]["migrations_dir"]
                self.assertTrue(Path(updated["d1_databases"][0]["migrations_dir"]).is_absolute())
            self.assertEqual(updated, expected)


class FreshTransportTests(unittest.TestCase):
    """Concrete HTTP transport is bounded, no-redirect, one-attempt and privacy-safe."""

    def setUp(self):
        """Construct transport with a dummy token and replace its network opener."""
        self.provider = fresh.FreshProvider("a" * 32, "private-dummy-token")
        self.provider.opener = Mock()
        self.output = io.StringIO()
        self.redirect = redirect_stdout(self.output)
        self.redirect.__enter__()
        self.addCleanup(self.redirect.__exit__, None, None, None)
        self.path = f"accounts/{self.provider.account}/d1/database?page=1&per_page=1000"

    def response(self, raw, status=200):
        """Fake one HTTP response including a safe Cloudflare request identifier."""
        value = Mock(status=status, headers={"cf-ray": "abcd-SIN"})
        value.read.return_value = raw
        context = Mock()
        context.__enter__ = Mock(return_value=value)
        context.__exit__ = Mock(return_value=False)
        self.provider.opener.open.return_value = context
        return value

    def test_concrete_request_is_one_bounded_get(self):
        """Canonical no-leading-slash paths normalize to the sole provider authority."""
        response = self.response(json.dumps(envelope([])).encode())
        self.assertEqual(self.provider.envelope("GET", self.path), envelope([]))
        self.assertEqual(response.read.call_args.args, (fresh.LIMIT + 1,))
        self.assertEqual(self.provider.opener.open.call_count, 1)
        request = self.provider.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, fresh.API + "/" + self.path)
        self.assertNotIn("private-dummy", self.output.getvalue())

    def test_off_authority_methods_and_arbitrary_creates_refused(self):
        """No generic resource-name, account, delete, redirect or SQL mutation exists."""
        for method, path, body in (("GET", "https://evil.test/", None),
                                   ("GET", "//evil.test/path", None),
                                   ("GET", "accounts/" + "b" * 32 + "/workers/scripts", None),
                                   ("DELETE", self.path, None),
                                   ("POST", f"accounts/{self.provider.account}/d1/database", {"name": "arbitrary"})):
            with self.assertRaises(fresh.FreshError):
                self.provider.envelope(method, path, body)
        self.provider.opener.open.assert_not_called()
        self.assertIsNone(fresh.NoRedirect().redirect_request(None, None, 302, None, None, "https://evil.test"))

    def test_old_writer_inventory_settings_are_readonly_and_bounded(self):
        """All named current writers can be inspected without granting their deploys."""
        self.response(json.dumps(envelope({"bindings": []})).encode())
        path = f"accounts/{self.provider.account}/workers/scripts/unrelated-existing-worker/settings"
        self.assertEqual(self.provider.get(path), {"bindings": []})
        for suffix in ("deployments", "versions/a" + "b" * 35, "../settings"):
            with self.assertRaises(fresh.FreshError):
                self.provider.get(path.rsplit("/", 1)[0] + "/" + suffix)
        with self.assertRaises(fresh.FreshError):
            self.provider.envelope("POST", path, {})
        self.assertEqual(self.provider.opener.open.call_count, 1)

    def test_http_error_retains_typed_diagnostics_not_raw_body(self):
        """409 is failure, and status/ray/codes/timing survive without provider prose."""
        self.provider._epoch = EPOCH
        error = HTTPError("private-url", 409, "private-text", {"cf-ray": "abcd-SIN"},
                          io.BytesIO(b'{"errors":[{"code":1001,"message":"private-body"}]}'))
        self.provider.opener.open.side_effect = error
        with self.assertRaisesRegex(fresh.FreshError, "existing_refused"):
            self.provider.post(f"accounts/{self.provider.account}/d1/database", {"name": EPOCH.database_name})
        event = json.loads(self.output.getvalue().splitlines()[-1])
        self.assertEqual(event["http_status"], 409)
        self.assertEqual(event["cf_ray"], "abcd-SIN")
        self.assertEqual(event["provider_error_codes"], [1001])
        self.assertGreaterEqual(event["duration_ms"], 0)
        self.assertNotIn("private-", self.output.getvalue())
        self.assertEqual(self.provider.opener.open.call_count, 1)

    def test_timeout_never_retries(self):
        """Transport uncertainty on write is an explicit recovery-only reason."""
        self.provider._epoch = EPOCH
        self.provider.opener.open.side_effect = TimeoutError("private-token")
        with self.assertRaisesRegex(fresh.FreshError, "write_ambiguous"):
            self.provider.post(f"accounts/{self.provider.account}/r2/buckets", {"name": EPOCH.bucket_name})
        self.assertEqual(self.provider.opener.open.call_count, 1)
        self.assertNotIn("private-token", self.output.getvalue())
        with self.assertRaisesRegex(fresh.FreshError, "replay_refused"):
            self.provider.post(f"accounts/{self.provider.account}/r2/buckets", {"name": EPOCH.bucket_name})
        self.assertEqual(self.provider.opener.open.call_count, 1)

    def test_query_capability_is_only_readonly_successful_new_scope(self):
        """An original/staging SQL write can never enter the protected transport."""
        self.provider._scope = Scope(EPOCH, DATABASE, "2026-10-01T12:34:56Z", "2026-10-01T12:34:56Z")
        path = f"accounts/{self.provider.account}/d1/database/{DATABASE}/query"
        self.response(json.dumps(envelope([])).encode())
        self.provider.post(path, {"sql": "SELECT state FROM send_policy", "params": []})
        for sql in ("DELETE FROM send_policy", "SELECT 1; DROP TABLE send_policy", "PRAGMA journal_mode=WAL;"):
            with self.assertRaises(fresh.FreshError):
                self.provider.post(path, {"sql": sql, "params": []})
        with self.assertRaises(fresh.FreshError):
            self.provider.post(path.replace(DATABASE, ORIGINAL_DATABASE), {"sql": "SELECT 1", "params": []})
        self.assertEqual(self.provider.opener.open.call_count, 1)

    def test_oversized_duplicate_or_failed_envelope_refused(self):
        """A nominal 200 cannot smuggle truncated identities or duplicate success."""
        for raw in (b"x" * (fresh.LIMIT + 1), b'{"success":false,"success":true,"errors":[],"result":[]}',
                    b'{"success":false,"errors":[{"code":1234,"message":"private"}],"result":[]}',
                    b'[]'):
            self.response(raw)
            with self.assertRaises(fresh.FreshError):
                self.provider.envelope("GET", self.path)


if __name__ == "__main__":
    unittest.main()
