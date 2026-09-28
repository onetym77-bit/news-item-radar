import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).with_name("pipeline.py")
SPEC = importlib.util.spec_from_file_location("editorial_pipeline", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

RUNS = [
    {"source": "뉴스", "workflow": "collect-interest-signals.yml", "run_id": 1, "conclusion": "success"},
    {"source": "원자료", "workflow": "daily-briefing.yml", "run_id": 2, "conclusion": "success"},
    {"source": "감사", "workflow": "source-onboarding-audit-l4-shadow.yml", "run_id": 3, "conclusion": "success"},
    {"source": "구의회", "workflow": "district-council-recent-l3.yml", "run_id": 4, "conclusion": "success"},
    {"source": "시민제안", "workflow": "citizen-proposal-shadow.yml", "run_id": 5, "conclusion": "success"},
    {"source": "시민제안 큐", "workflow": "publish-citizen-shadow.yml", "run_id": 6, "conclusion": "success"},
]

class CollectionCycleTest(unittest.TestCase):
    def test_manual_run_is_labeled_stored_snapshot(self):
        with patch.dict(os.environ, {}, clear=True):
            cycle = MODULE.collection_cycle_from_env()
        self.assertEqual(cycle["mode"], "STORED_SNAPSHOT")
        self.assertFalse(cycle["verified"])

    def test_complete_cycle_is_verified(self):
        env = {
            "EDITORIAL_COLLECTION_CYCLE_ID": "fresh-100-1",
            "EDITORIAL_COLLECTION_STARTED_AT_UTC": "2026-09-29T00:00:00Z",
            "EDITORIAL_COLLECTION_RUNS": json.dumps(RUNS, ensure_ascii=False),
        }
        with patch.dict(os.environ, env, clear=True):
            cycle = MODULE.collection_cycle_from_env()
        self.assertEqual(cycle["mode"], "FRESH_CYCLE")
        self.assertTrue(cycle["verified"])
        self.assertEqual(len(cycle["runs"]), 6)

    def test_partial_cycle_is_rejected(self):
        env = {
            "EDITORIAL_COLLECTION_CYCLE_ID": "fresh-100-1",
            "EDITORIAL_COLLECTION_STARTED_AT_UTC": "2026-09-29T00:00:00Z",
            "EDITORIAL_COLLECTION_RUNS": json.dumps(RUNS[:-1]),
        }
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "필수 실행 누락"):
                MODULE.collection_cycle_from_env()

if __name__ == "__main__":
    unittest.main()
