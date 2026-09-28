import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "editorial_record_decision", Path(__file__).with_name("record_decision.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RecordDecisionTests(unittest.TestCase):
    def write_fixture(self, root):
        output = root / "latest.json"
        decisions = root / "decisions.json"
        output.write_text(json.dumps({
            "proposals": [{
                "id": "proposal", "title": "운영 후보", "issue_key": "운영",
                "source": "뉴스", "url": "https://example.org/proposal",
            }],
            "shadow_reviews": [{
                "id": "shadow", "title": "감사 검증 카드", "issue_key": "감사",
                "source": "서울시 감사 결과", "url": "https://example.org/shadow",
            }],
        }, ensure_ascii=False), encoding="utf-8")
        decisions.write_text("[]", encoding="utf-8")
        return output, decisions

    def test_records_exact_shadow_card_and_marks_type(self):
        with tempfile.TemporaryDirectory() as folder:
            output, decisions = self.write_fixture(Path(folder))
            with patch.object(module, "OUTPUT", output), patch.object(module, "DECISIONS", decisions):
                row = module.record("shadow", "DISCARD", "검토 가치 없음")
        self.assertEqual(row["record_type"], "검증 전용")
        self.assertEqual(row["source"], "서울시 감사 결과")
        self.assertEqual(row["decision"], "DISCARD")

    def test_rejects_unknown_or_already_decided_id(self):
        with tempfile.TemporaryDirectory() as folder:
            output, decisions = self.write_fixture(Path(folder))
            with patch.object(module, "OUTPUT", output), patch.object(module, "DECISIONS", decisions):
                with self.assertRaisesRegex(ValueError, "없는 ID"):
                    module.record("unknown", "HOLD", "")
                module.record("proposal", "COMPLETE", "")
                with self.assertRaisesRegex(ValueError, "이미 판정"):
                    module.record("proposal", "HOLD", "")


if __name__ == "__main__":
    unittest.main()
