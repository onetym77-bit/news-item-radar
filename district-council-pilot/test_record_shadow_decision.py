import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("record_shadow_decision.py")
SPEC = importlib.util.spec_from_file_location("record_shadow_decision", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RecordShadowDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.queue = self.root / "queue.json"
        self.decisions = self.root / "decisions.json"
        self.queue.write_text(json.dumps({
            "schema": 1,
            "items": [{
                "id": "abc123",
                "title": "검토 제목",
                "issue_key": "검토 사안",
                "source": "송파구의회 회의록",
                "url": "https://example.test/minutes",
            }],
        }, ensure_ascii=False), encoding="utf-8")
        self.decisions.write_text("[]\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_records_exact_queue_id(self):
        row = MODULE.record(
            "abc123", "PROMISING", "취재 검토",
            queue_path=self.queue, decisions_path=self.decisions,
        )
        self.assertEqual(row["decision"], "PROMISING")
        saved = json.loads(self.decisions.read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["title"], "검토 제목")

    def test_rejects_unknown_and_duplicate_ids(self):
        with self.assertRaises(ValueError):
            MODULE.record(
                "missing", "HOLD", "",
                queue_path=self.queue, decisions_path=self.decisions,
            )
        MODULE.record(
            "abc123", "HOLD", "",
            queue_path=self.queue, decisions_path=self.decisions,
        )
        with self.assertRaises(ValueError):
            MODULE.record(
                "abc123", "DISCARD", "",
                queue_path=self.queue, decisions_path=self.decisions,
            )

    def test_rejects_unknown_decision(self):
        with self.assertRaises(ValueError):
            MODULE.record(
                "abc123", "COMPLETE", "",
                queue_path=self.queue, decisions_path=self.decisions,
            )


if __name__ == "__main__":
    unittest.main()
