import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_builder():
    spec = importlib.util.spec_from_file_location(
        "daily_briefing_anchor_test", HERE / "build_briefing.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("build_briefing.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = load_builder()


class BriefingEvidenceAnchorTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "item_id": "T-01",
            "canonical_topic": "시험 항목",
            "status": "보류",
            "stage_s": "S1",
            "editorial_e": "E3",
            "production_p": "미판정",
            "new_evidence": "기존 기록",
            "next_check": "원문 재확인",
            "review_by": "2026-09-14",
            "source_report": "source.md",
            "source_families": "PUBLIC",
            "scene_status": "없음",
            "upstream_gate": "HOLD",
            "structural_question": "시험 질문",
            "question_gate": "PASS",
            "question_hypothesis": "A와 B",
        }
        self.audit = {
            "item_id": "T-01",
            "quality_gate": "PASS",
            "quality_score": "10",
            "central_question": "시험 중심 질문",
            "citizen_stake": "시험 이해관계",
            "competing_hypotheses": "A: 구조 | B: 대안",
            "decision_rule": "전환: 확인 | 축소: 일부 | 폐기: 없음",
            "evidence_anchor": "",
        }
        self.as_of = date(2026, 9, 14)

    def test_legacy_pass_is_held_out_until_anchor_review(self):
        audits = {"T-01": self.audit}
        queue = builder.merge_queue([self.row], audits, {}, self.as_of)
        self.assertEqual(queue[0]["blocker"], "근거 앵커 재심사 필요")
        briefing = builder.render_briefing([self.row], audits, queue, self.as_of)
        b_section = briefing.split("## B. 오늘 4시간 검증할 아이템", 1)[1].split(
            "## 기한 초과 검증 대기열", 1
        )[0]
        self.assertNotIn("시험 항목", b_section)
        self.assertIn("v1.6 근거 앵커 재심사 대기", briefing)
        self.assertIn("시험 항목", briefing)

    def test_confirmed_anchor_can_enter_verification(self):
        self.audit["evidence_anchor"] = "STRUCTURAL_DATA"
        audits = {"T-01": self.audit}
        queue = builder.merge_queue([self.row], audits, {}, self.as_of)
        briefing = builder.render_briefing([self.row], audits, queue, self.as_of)
        b_section = briefing.split("## B. 오늘 4시간 검증할 아이템", 1)[1].split(
            "## 기한 초과 검증 대기열", 1
        )[0]
        self.assertIn("시험 항목", b_section)
        self.assertIn("근거 앵커: 분해 가능한 구조 자료", b_section)
        self.assertNotEqual(queue[0]["blocker"], "근거 앵커 재심사 필요")


if __name__ == "__main__":
    unittest.main()
