"""Static and mocked readback tests for the mail observability privacy gate."""

from __future__ import annotations

import unittest
from unittest.mock import patch
import copy
import os

import check_trace_sink_isolation as isolation

import check_observability as gate


class ObservabilityGateTests(unittest.TestCase):
    """Require independent explicit settings in every mail API realm."""

    def test_both_local_realms_are_explicitly_safe(self) -> None:
        """Production and staging must not depend on inherited defaults."""

        for realm in gate.SCRIPT:
            with self.subTest(realm=realm):
                self.assertTrue(gate.safe_observability(gate.local_settings(realm)["observability"]))

    def test_each_capture_and_export_path_fails_closed(self) -> None:
        """No missing or contradictory readback field may be treated as safe."""

        safe = gate.local_settings("production")
        self.assertTrue(gate.safe_settings(safe))
        cloudflare_sink = {"observability": {**safe["observability"]}}
        cloudflare_sink["observability"]["logs"] = {
            **safe["observability"]["logs"], "destinations": ["cloudflare"]
        }
        cloudflare_sink["observability"]["traces"] = {
            **safe["observability"]["traces"], "destinations": ["cloudflare"]
        }
        self.assertTrue(gate.safe_settings(cloudflare_sink))
        for field, value in (("redact_query_string", False), ("enabled", True), ("head_sampling_rate", 0.1)):
            changed = {"observability": {**safe["observability"], field: value}}
            self.assertFalse(gate.safe_settings(changed))
        for section, field, value in (
            ("logs", "enabled", True),
            ("logs", "invocation_logs", True),
            ("logs", "persist", False),
            ("logs", "head_sampling_rate", 0.1),
            ("logs", "destinations", ["export"]),
            ("traces", "enabled", True),
            ("traces", "destinations", ["export"]),
        ):
            observation = {**safe["observability"]}
            observation[section] = {**observation[section], field: value}
            self.assertFalse(gate.safe_settings({"observability": observation}))
        self.assertFalse(gate.safe_settings({**safe, "logpush": True}))
        self.assertFalse(gate.safe_settings({**safe, "tail_consumers": [{"service": "other"}]}))

    def test_local_api_requires_independent_issues_off(self) -> None:
        """Source intent explicitly disables Issues in every API realm, not the sink."""
        for realm in gate.SCRIPT:
            observation = copy.deepcopy(gate.local_settings(realm)["observability"])
            self.assertEqual(observation["issues"], {"enabled": False})
            for bad in (None, {}, {"enabled": True}):
                observation["issues"] = bad
                self.assertFalse(gate.safe_observability(observation))
            del observation["issues"]
            self.assertFalse(gate.safe_observability(observation))

    def test_private_sink_is_independently_safe(self) -> None:
        """Only the Queue sink retains reviewed logs; public API settings cannot mask it."""

        for realm in gate.SINK_SCRIPT:
            safe = gate.local_settings(realm, sink=True)
            self.assertTrue(gate.safe_settings(safe, sink=True))
            self.assertFalse(gate.safe_settings(safe))
            self.assertFalse(gate.safe_settings(gate.local_settings(realm), sink=True))
            for section, field, value in (("logs", "invocation_logs", True),
                                           ("traces", "enabled", True),
                                           ("logs", "destinations", ["private-export"])):
                obs = {**safe["observability"]}
                obs[section] = {**obs[section], field: value}
                self.assertFalse(gate.safe_settings({"observability":obs}, sink=True))
        with patch.object(isolation, "verify", return_value=True) as verify:
            self.assertTrue(gate.verify("staging", "account", "token", sink=True))
            self.assertEqual(verify.call_args.args[:4],("account","token","staging","amail-trace-sink-staging"))


class EffectiveApiTests(unittest.TestCase):
    """Positive current-resource evidence and stable serving replace legacy defaults."""
    VERSION = "00000000-0000-4000-8000-000000000001"
    DEPLOYMENT = "00000000-0000-4000-8000-000000000002"

    def worker(self, realm="staging"):
        """Match live inactive preferences, requiring independent Issues off."""
        return {"id": self.VERSION, "name": gate.SCRIPT[realm], "logpush": False,
                "tail_consumers": [], "observability": {
                    "enabled": False, "head_sampling_rate": 1,
                    "redact_query_string": False,
                    "logs": {"enabled": False, "invocation_logs": True,
                             "persist": True, "head_sampling_rate": 1,
                             "destinations": []},
                    "traces": {"enabled": False, "persist": True,
                               "head_sampling_rate": 1, "destinations": []},
                    "issues": {"enabled": False}}}

    def deployment(self):
        """Return exactly one active version with an immutable deployment identity."""
        return {"deployments": [{"id": self.DEPLOYMENT, "strategy": "percentage",
            "versions": [{"version_id": self.VERSION, "percentage": 100}]}]}

    def test_explicit_off_accepts_inactive_preferences_and_unsupported_legacy(self):
        """Missing/null old observability cannot mask explicit current capture-off."""
        for realm in gate.SCRIPT:
            self.assertTrue(gate.effective_api_settings(self.worker(realm), gate.SCRIPT[realm],
                {}, {"observability": None, "logpush": False, "tail_consumers": []}))
        self.assertFalse(gate.effective_api_settings({}, gate.SCRIPT["staging"], {}, {}))

    def test_independent_capture_fields_are_required(self):
        """Issues and every capture switch need literal false, never absent/null/coerced."""
        for section in (None, "logs", "traces", "issues"):
            for bad in (None, True, 0, "false", []):
                worker = self.worker()
                obs = worker["observability"]
                container = obs if section is None else obs[section]
                container["enabled"] = bad
                self.assertFalse(gate.effective_api_settings(worker, gate.SCRIPT["staging"]))
                del container["enabled"]
                self.assertFalse(gate.effective_api_settings(worker, gate.SCRIPT["staging"]))
        worker = self.worker()
        del worker["observability"]["issues"]
        self.assertFalse(gate.effective_api_settings(worker, gate.SCRIPT["staging"]))

    def test_identity_exports_and_malformed_preferences_fail(self):
        """Current resource identity, exports and optional shapes are never inferred."""
        for key, bad in (("name", "another-worker"), ("id", None), ("id", ""),
                         ("logpush", None), ("logpush", True),
                         ("tail_consumers", None), ("tail_consumers", [{}]),
                         ("streaming_tail_consumers", [{}])):
            worker = self.worker(); worker[key] = bad
            self.assertFalse(gate.effective_api_settings(worker, gate.SCRIPT["staging"]))
        for section, key, bad in (("logs", "destinations", ["external"]),
                ("traces", "destinations", None), ("logs", "persist", 1),
                ("logs", "invocation_logs", None), ("traces", "head_sampling_rate", True),
                ("logs", "head_sampling_rate", float("nan")),
                ("issues", "unreviewed", False)):
            worker = self.worker(); worker["observability"][section][key] = bad
            self.assertFalse(gate.effective_api_settings(worker, gate.SCRIPT["staging"]))

    def test_explicit_legacy_conflicts_are_rejected(self):
        """An enabled legacy field or export cannot be dismissed as unsupported."""
        for legacy in ({"observability": True}, {"logpush": True},
                {"tail_consumers": [{}]}, {"tail_consumers": None},
                {"streaming_tail_consumers": [{}]},
                {"observability": {"enabled": True}},
                {"observability": {"logs": {"enabled": True}}},
                {"observability": {"issues": {"enabled": True}}},
                {"observability": {"traces": {"destinations": ["external"]}}}):
            self.assertFalse(gate.effective_api_settings(self.worker(), gate.SCRIPT["staging"], legacy))

    def test_stable_single100_resource_readback_is_required(self):
        """Both realms bracket current/legacy readback and reject changed serving."""
        for realm in gate.SCRIPT:
            with patch.object(gate, "readback", side_effect=[self.deployment(), {},
                    {"observability": None}, self.deployment()]) as fetch, \
                 patch.object(gate, "worker_readback", return_value=self.worker(realm)), \
                 patch.dict(os.environ, {}, clear=True):
                self.assertTrue(gate.verify(realm, "account", "token"))
                self.assertEqual(fetch.call_count, 4)
        changed = self.deployment(); changed["deployments"][0]["id"] = self.VERSION
        for final in (changed, {"deployments": []}):
            with patch.object(gate, "readback", side_effect=[self.deployment(), {}, {}, final]), \
                 patch.object(gate, "worker_readback", return_value=self.worker()), \
                 patch.dict(os.environ, {}, clear=True):
                self.assertFalse(gate.verify("staging", "account", "token"))
        with patch.object(gate, "readback", side_effect=ValueError("unavailable")):
            with self.assertRaises(ValueError):
                gate.verify("staging", "account", "token")

    def test_expected_version_and_split_deployment_fail_closed(self):
        """Optional caller pin is enforced and partial traffic never establishes safety."""
        split = self.deployment()
        split["deployments"][0]["versions"][0]["percentage"] = 99
        for first in (split, {"deployments": []}):
            with patch.object(gate, "readback", return_value=first), \
                 patch.object(gate, "worker_readback") as worker:
                self.assertFalse(gate.verify("staging", "account", "token"))
                worker.assert_not_called()
        with patch.object(gate, "readback", return_value=self.deployment()), \
             patch.dict(os.environ, {"AMAIL_EXPECTED_WORKER_VERSION": self.DEPLOYMENT}):
            self.assertFalse(gate.verify("staging", "account", "token"))

    def test_current_resource_transport_is_exact_and_fail_closed(self):
        """Bounded successful envelopes only; denial/null result never become off."""
        from unittest.mock import MagicMock
        import json
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = json.dumps({"success": True, "result": self.worker()}).encode()
        with patch.object(gate, "urlopen", return_value=response) as fetch:
            self.assertEqual(gate.worker_readback("account", "token", "amail-mail-staging"), self.worker())
            self.assertEqual(fetch.call_args.args[0].full_url,
                "https://api.cloudflare.com/client/v4/accounts/account/workers/workers/amail-mail-staging")
            self.assertEqual(fetch.call_args.kwargs["timeout"], 15)
            response.read.assert_called_with(262_145)
        for payload in (b"null", b"[]", b"invalid", b'{"success":true,"result":null}',
                        b'{"success":false,"result":{}}', b"x" * 262_145):
            response.read.return_value = payload
            with patch.object(gate, "urlopen", return_value=response), self.assertRaises(ValueError):
                gate.worker_readback("account", "token", "amail-mail-staging")
        with patch.object(gate, "urlopen", side_effect=gate.URLError("private")), self.assertRaises(ValueError):
            gate.worker_readback("account", "token", "amail-mail-staging")


class SinkIsolationTests(unittest.TestCase):
    """Actual serving capabilities and account inventories, not source intent, prove isolation."""

    VERSION="00000000-0000-4000-8000-000000000001"
    DEPLOYMENT="00000000-0000-4000-8000-000000000002"
    ACCOUNT="a"*32
    QUEUE="b"*32
    DLQ="c"*32

    def fixture(self):
        """Return independent mutable deployment/version/surface and Queue fixtures."""
        deployment={"deployments":[{"id":self.DEPLOYMENT,"strategy":"percentage",
            "versions":[{"version_id":self.VERSION,"percentage":100}]}]}
        version={"id":self.VERSION,"resources":{"bindings":[],"script":{"handlers":["queue"],"named_handlers":[]}}}
        responses={"deployments?per_page=1&page=1":deployment,f"versions/{self.VERSION}":version,
            "settings":gate.local_settings("staging",sink=True),
            "script-settings":gate.local_settings("staging",sink=True),
            "subdomain":{"enabled":False,"previews_enabled":False},"schedules":{"schedules":[]}}
        main={"queue_name":"amail-trace-events-staging","queue_id":self.QUEUE,
            "settings":{"message_retention_period":86400,"delivery_delay":0,"delivery_paused":False},
            "consumers_total_count":1,"producers_total_count":0,"producers":[],
            "consumers":[{"type":"worker","script_name":"amail-trace-sink-staging",
                "dead_letter_queue":"amail-trace-dlq-staging","settings":{"batch_size":10,"max_wait_time_ms":1000,
                    "max_retries":3,"retry_delay":30,"max_concurrency":2}}]}
        dlq={"queue_name":"amail-trace-dlq-staging","queue_id":self.DLQ,
            "settings":copy.deepcopy(main["settings"]),"consumers_total_count":0,
            "producers_total_count":0,"producers":[],"consumers":[]}
        return responses,[main,dlq]

    def invoke(self,responses,queues):
        """Mock transport only; run all capability/shape assertions without network."""
        def readback(account,token,script,suffix):
            self.assertEqual(script,"amail-trace-sink-staging")
            return copy.deepcopy(responses[suffix])
        def inventory(token,path):
            return [{"id":"d"*32,"account":{"id":self.ACCOUNT}}] if path.startswith("/zones?") else []
        def queue_detail(account,token,path):
            return {"result":next(row for row in queues if path.endswith(row["queue_id"]))}
        with patch.dict(os.environ,{"AMAIL_EXPECTED_TRACE_SINK_VERSION":self.VERSION,
                     "AMAIL_TRACE_QUEUE_ID":self.QUEUE,"AMAIL_TRACE_DLQ_ID":self.DLQ}), \
             patch.object(isolation,"inventory",side_effect=inventory), \
             patch.object(isolation,"worker_domains",return_value=[]), \
             patch.object(isolation,"envelope",return_value={"success":True,"result":[]}), \
             patch.object(isolation.queues,"inventory",return_value=queues), \
             patch.object(isolation.queues,"request",side_effect=queue_detail):
            return isolation.verify(self.ACCOUNT,"token","staging","amail-trace-sink-staging",readback,gate.safe_settings)

    def test_actual_serving_private_queue_only_version(self):
        """Stable 100% deployment with exact handler/empty bindings/private surfaces passes."""
        responses,queues=self.fixture()
        self.assertTrue(self.invoke(responses,queues))
        responses[f"versions/{self.VERSION}"]["resources"]["bindings"]={"result":[]}
        self.assertTrue(self.invoke(responses,queues))

    def test_http_handler_capability_and_surface_drift_rejected(self):
        """One contradictory runtime publication or capability defeats source configuration."""
        for key,field,value in [("subdomain","enabled",True),("subdomain","previews_enabled",True),
                                ("schedules","schedules",[{"cron":"* * * * *"}])]:
            responses,queues=self.fixture(); responses[key][field]=value
            self.assertFalse(self.invoke(responses,queues))
        for resource,value in [("bindings",{}),("bindings",[{"name":"DATA","type":"r2_bucket"}])]:
            responses,queues=self.fixture(); responses[f"versions/{self.VERSION}"]["resources"][resource]=value
            self.assertFalse(self.invoke(responses,queues))
        for field,value in [("handlers",["queue","fetch"]),("handlers",[]),
                            ("named_handlers",[{"name":"PrivateRPC","handlers":["fetch"]}])]:
            responses,queues=self.fixture(); responses[f"versions/{self.VERSION}"]["resources"]["script"][field]=value
            self.assertFalse(self.invoke(responses,queues))

    def test_exact_only_queue_subscription_required(self):
        """Missing, extra, mismatched or incompletely listed subscriptions never pass."""
        responses,queues=self.fixture(); queues[0]["consumers"]=[];queues[0]["consumers_total_count"]=0
        self.assertFalse(self.invoke(responses,queues))
        responses,queues=self.fixture();queues[0]["consumers_total_count"]=2
        self.assertFalse(self.invoke(responses,queues))
        responses,queues=self.fixture();queues[0]["consumers"][0]["script_name"]="unexpected-sink"
        with self.assertRaises(ValueError):self.invoke(responses,queues)
        responses,queues=self.fixture(); extra=copy.deepcopy(queues[0]);extra["queue_id"]="e"*32;extra["queue_name"]="other";queues.append(extra)
        self.assertFalse(self.invoke(responses,queues))

    def test_incomplete_queue_inventory_cannot_prove_exclusivity(self):
        """Real shared inventory validation rejects an omitted third Queue before detail reads."""
        _,rows=self.fixture()
        metadata={"page":1,"per_page":100,"count":2,"total_count":2,"total_pages":1}
        for field,bad in [("count",1),("total_count",3),("per_page",1),("page",True),("total_pages",2)]:
            info={**metadata,field:bad}
            with patch.dict(os.environ,{"AMAIL_TRACE_QUEUE_ID":self.QUEUE,"AMAIL_TRACE_DLQ_ID":self.DLQ}), \
                 patch.object(isolation.queues,"request",return_value={"success":True,"result":rows,"result_info":info}) as request, \
                 self.assertRaises(ValueError):
                isolation.queue_trigger_exact(self.ACCOUNT,"token","staging","amail-trace-sink-staging")
            self.assertEqual(request.call_count,1)
        for optional_info in (None, {}, {"count":2,"total_count":2,"page":1,"total_pages":1,"per_page":20}):
            payload={"success":True,"result":rows}
            if optional_info is not None:payload["result_info"]=optional_info
            with patch.dict(os.environ,{"AMAIL_TRACE_QUEUE_ID":self.QUEUE,"AMAIL_TRACE_DLQ_ID":self.DLQ}), \
                 patch.object(isolation.queues,"request",side_effect=[payload,{"result":rows[0]},{"result":rows[1]}]) as request:
                self.assertTrue(isolation.queue_trigger_exact(self.ACCOUNT,"token","staging","amail-trace-sink-staging"))
                self.assertEqual(request.call_args_list[0].args[2],"queues")

    def test_unpinned_split_or_changed_serving_fails(self):
        """No implicit latest version can replace explicit reviewed 100% serving provenance."""
        responses,queues=self.fixture();responses["deployments?per_page=1&page=1"]["deployments"][0]["versions"][0]["percentage"]=99
        self.assertFalse(self.invoke(responses,queues))
        with patch.dict(os.environ,{"AMAIL_EXPECTED_TRACE_SINK_VERSION":""}):
            self.assertFalse(isolation.verify(self.ACCOUNT,"token","staging","amail-trace-sink-staging",None,None))
        responses,queues=self.fixture()
        first=responses["deployments?per_page=1&page=1"]
        second=copy.deepcopy(first);second["deployments"][0]["id"]="00000000-0000-4000-8000-000000000003"
        sequence=iter([first,second])
        def readback(account,token,script,suffix):
            return next(sequence) if suffix.startswith("deployments?") else responses[suffix]
        with patch.dict(os.environ,{"AMAIL_EXPECTED_TRACE_SINK_VERSION":self.VERSION}), \
             patch.object(isolation,"surfaces_private",return_value=True), \
             patch.object(isolation,"queue_trigger_exact",return_value=True):
            self.assertFalse(isolation.verify(self.ACCOUNT,"token","staging","amail-trace-sink-staging",readback,gate.safe_settings))

    def test_inventory_requires_complete_unique_stable_counts(self):
        """Empty/malformed pagination cannot establish route/domain absence."""
        empty={"success":True,"result":[],"result_info":{"page":1,"per_page":50,"count":0,"total_count":0,"total_pages":0}}
        with patch.object(isolation,"envelope",return_value=empty):self.assertEqual(isolation.inventory("token","/zones?account.id=fixture"),[])
        for key,value in [("count",1),("total_count",1),("page",2),("per_page",20),("total_pages",2)]:
            bad=copy.deepcopy(empty);bad["result_info"][key]=value
            with patch.object(isolation,"envelope",return_value=bad),self.assertRaises(ValueError):
                isolation.inventory("token","/zones?account.id=fixture")
        with patch.object(isolation,"envelope",side_effect=ValueError("denied")),self.assertRaises(ValueError):
            isolation.inventory("token","/zones?account.id=fixture")

    def test_domains_single_page_uses_no_invented_paging(self):
        """Official SinglePage array accepts absent or coherent optional generic metadata."""
        row={"id":"f"*32,"service":"another-worker"}
        for metadata in (None,{}, {"count":1,"total_count":1,"page":1,"per_page":20,"total_pages":1}):
            payload={"success":True,"result":[row]}
            if metadata is not None:payload["result_info"]=metadata
            with patch.object(isolation,"envelope",return_value=payload) as request:
                self.assertEqual(isolation.worker_domains(self.ACCOUNT,"token"),[row])
                self.assertEqual(request.call_args.args[1],f"/accounts/{self.ACCOUNT}/workers/domains")
        for metadata in ({"count":0},{"total_count":2},{"page":2},{"total_pages":2},
                         {"per_page":0},{"per_page":True},{"next_cursor":"opaque"},[] ):
            with patch.object(isolation,"envelope",return_value={"success":True,"result":[row],"result_info":metadata}),self.assertRaises(ValueError):
                isolation.worker_domains(self.ACCOUNT,"token")
        with patch.object(isolation,"envelope",return_value={"success":True,"result":[row,{**row,"id":"e"*32}],"result_info":{"per_page":1}}),self.assertRaises(ValueError):
            isolation.worker_domains(self.ACCOUNT,"token")
        with patch.object(isolation,"envelope",return_value={"success":True,"result":[row,row]}),self.assertRaises(ValueError):
            isolation.worker_domains(self.ACCOUNT,"token")

    def test_domains_unknown_completeness_claims_are_rejected(self):
        """Closed transport metadata rejects explicit truncation/cursors without alias guessing."""
        for field,value in (("next_cursor","opaque"),("truncated",True),("has_more",True)):
            payload={"success":True,"result":[],field:value}
            with patch.object(isolation,"envelope",return_value=payload),self.assertRaises(ValueError):
                isolation.worker_domains(self.ACCOUNT,"token")
        with patch.object(isolation,"envelope",return_value={"success":True,"result":[],"result_info":{"cursors":{"after":"opaque"}}}),self.assertRaises(ValueError):
            isolation.worker_domains(self.ACCOUNT,"token")

    def test_account_routes_and_domains_are_read_not_assumed(self):
        """Every readable account zone is checked, including non-project zone routes."""
        script="amail-trace-sink-staging"
        readback=lambda account,token,name,part: ({"enabled":False,"previews_enabled":False} if part=="subdomain" else {"schedules":[]})
        domains=[{"id":"f"*32,"service":script}]
        with patch.object(isolation,"worker_domains",return_value=domains):
            self.assertFalse(isolation.surfaces_private(self.ACCOUNT,"token",script,readback))
        zones=[{"id":"d"*32,"account":{"id":self.ACCOUNT}},{"id":"e"*32,"account":{"id":self.ACCOUNT}}]
        route={"id":"f"*32,"pattern":"other.invalid/*","script":script}
        with patch.object(isolation,"worker_domains",return_value=[]), \
             patch.object(isolation,"inventory",return_value=zones), \
             patch.object(isolation,"envelope",side_effect=[{"result":[]},{"result":[route]}]) as request:
            self.assertFalse(isolation.surfaces_private(self.ACCOUNT,"token",script,readback))
            self.assertEqual(request.call_count,2)


if __name__ == "__main__":
    unittest.main()
