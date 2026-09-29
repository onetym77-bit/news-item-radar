import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("dispatch_workflow.py")
SPEC = importlib.util.spec_from_file_location("dispatch_workflow", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class DispatchWorkflowTest(unittest.TestCase):
    def test_parse_inputs_preserves_json_value(self):
        self.assertEqual(
            MODULE.parse_inputs(["run_id=123", 'collection_runs=[{"run_id":1}]']),
            {"run_id": "123", "collection_runs": '[{"run_id":1}]'},
        )

    def test_choose_new_main_dispatch_run(self):
        runs = [
            {"id": 10, "event": "workflow_dispatch", "head_branch": "main", "created_at": "2026-09-29T01:00:00Z"},
            {"id": 11, "event": "push", "head_branch": "main", "created_at": "2026-09-29T01:01:00Z"},
            {"id": 12, "event": "workflow_dispatch", "head_branch": "feature", "created_at": "2026-09-29T01:02:00Z"},
            {"id": 13, "event": "workflow_dispatch", "head_branch": "main", "created_at": "2026-09-29T01:03:00Z"},
        ]
        self.assertEqual(MODULE.choose_new_run({"10"}, runs)["id"], 13)

    def test_choose_new_run_returns_none_for_preexisting_runs(self):
        runs = [{"id": 10, "event": "workflow_dispatch", "head_branch": "main", "created_at": "2026-09-29T01:00:00Z"}]
        self.assertIsNone(MODULE.choose_new_run({"10"}, runs))

if __name__ == "__main__":
    unittest.main()
