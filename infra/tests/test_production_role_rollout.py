"""Production lifecycle/route/workflow contracts, executed only on hosted CI."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import os
import re
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "infra/deploy"))
import check_production_role_graph as graph
import production_role_routes as routes
import prepare_production_graph as prepare


class StorageTests(unittest.TestCase):
    """A pristine bootstrap is not a partially migrated or operational replacement."""
    def query(self, sql):
        """Use synthetic known schema and initial empty state, not live D1."""
        if 'sqlite_master' in sql and "type='table'" in sql:
            return [{"name": name} for name in ("role_arrivals", "role_monitor_health")]
        if sql.startswith('PRAGMA'):
            names = ("arrival_seq", "id", "role", "received_at", "forward_state", "forward_updated_at", "alerted_at") if 'arrivals' in sql else ("singleton", "lease_until", "checked_at")
            return [{"name": name, "type": "INTEGER", "pk": int(name in ("arrival_seq", "singleton"))} for name in names]
        if "type='index'" in sql:
            return [{"name": name} for name in ("role_arrivals_unalerted", "role_arrivals_forward")]
        if 'COUNT' in sql:
            return [{"n": 0}]
        return [{"singleton": 1, "lease_until": 0, "checked_at": 0, "expired": 1}]

    def test_first_bootstrap_requires_successfully_empty_inventory(self):
        """Failed inventory cannot stand in for first absence."""
        with patch.object(graph, 'query', return_value=[]):
            graph.storage('first-bootstrap')
        for value in ([{"name":"role_arrivals"}], [{"name":"unrelated"}]):
            with patch.object(graph, 'query', return_value=value), self.assertRaises(ValueError):
                graph.storage('first-bootstrap')
        with patch.object(graph, 'query', side_effect=ValueError()), self.assertRaises(ValueError):
            graph.storage('first-bootstrap')

    def test_replacement_rejects_pending_arrivals_and_live_lease(self):
        """Neither D1 deletion nor ignoring a healthy lease is a replacement gate."""
        with patch.object(graph, 'query', side_effect=lambda binding, sql: self.query(sql)):
            graph.storage('replacement')
            graph.storage('migrated')
        for bad_sql in ('COUNT', 'expired'):
            def changed(binding, sql):
                if bad_sql == 'COUNT' and 'COUNT' in sql:
                    return [{"n":1}]
                if bad_sql == 'expired' and 'expired' in sql:
                    return [{"singleton":1,"lease_until":1000,"checked_at":1,"expired":0}]
                return self.query(sql)
            with patch.object(graph, 'query', side_effect=changed), self.assertRaises(ValueError):
                graph.storage('replacement')

    def test_absence_is_complete_success_not_error(self):
        """Wrong provider shape, duplicated workers and existing role fail closed."""
        with patch.object(graph.role, 'api_get', return_value=[{"id":"other"}]):
            graph.role_absent('a'*32, 'synthetic')
        for payload in (None, {}, [{"id":graph.ROLE}], [{"id":"x"},{"id":"x"}]):
            with patch.object(graph.role, 'api_get', return_value=payload), self.assertRaises(ValueError):
                graph.role_absent('a'*32,'synthetic')

    def test_bootstrap_confirmation_precedes_provider_access(self):
        """Wrong lifecycle confirmation cannot create or even read a graph."""
        with patch.dict(os.environ, {"GITHUB_REF":"refs/heads/main", "AMAIL_PRODUCTION_GRAPH_FREEZE":"FREEZE_PRODUCTION_GRAPH_WRITERS", "AMAIL_PRODUCTION_GRAPH_CONFIRM":"wrong"}), patch.object(graph.role, 'api_get') as request, self.assertRaises(ValueError):
            prepare.prepare('bootstrap')
        request.assert_not_called()


class RouteTests(unittest.TestCase):
    """Every mixed phase has four exact reserved literal rules and fixed action targets."""
    def rows(self, switched):
        """Use a synthetic destination; real private snapshots must never be printed."""
        return [{"id":str(index),"enabled":True,"source":"api",
                 "matchers":[{"type":"literal","field":"to","value":alias}],
                 "actions":[{"type":"worker","value":[routes.WORKER]}] if index < switched else [{"type":"forward","value":["synthetic@example.invalid"]}]}
                for index,alias in enumerate(routes.forwards.ROLES)]

    def test_all_mixed_phases_and_one_rule_transition(self):
        """Whole-rule compare detects changes to untouched roles and permits exact restore."""
        originals = routes.snapshot(self.rows(0),'synthetic@example.invalid',0)
        for count in range(5):
            routes.snapshot(self.rows(count),'synthetic@example.invalid',count)
        before = originals
        after = routes.snapshot(self.rows(1),'synthetic@example.invalid',1)
        self.assertTrue(routes.one_step(before,after,0))
        self.assertTrue(routes.one_step(after,before,0,original=originals))
        changed = deepcopy(after)
        changed[routes.forwards.ROLES[1]]['priority'] = 1
        self.assertFalse(routes.one_step(before,changed,0))

    def test_conflicting_shapes_do_not_get_adopted(self):
        """Duplicate, missing, multi-match and wrong Worker rules are not a mixed graph."""
        rows = self.rows(1)
        bad = deepcopy(rows)
        bad[0]['actions'] = [{"type":"worker","value":["other"]}]
        for value in (rows[:-1],rows+[rows[0]],bad):
            with self.assertRaises(ValueError):
                routes.snapshot(value,'synthetic@example.invalid',1)


if __name__ == '__main__':
    unittest.main()
