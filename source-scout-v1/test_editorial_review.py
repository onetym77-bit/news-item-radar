import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


review = load_module("editorial_review_test", "compile_editorial_review.py")


class EditorialReviewTests(unittest.TestCase):
    def base_row(self):
        return {
            "candidate_id": "abc123",
            "source_revision": "rev123",
            "text": "서울 피해 37건 발생",
            "question_basis": "서울 피해 37건 발생",
            "question": "어디에서 반복되는가?",
            "url": "https://example.invalid/source",
            "auto_evidence_anchor": "MEASURED_PROBLEM_SIGNAL",
            "grounding_status": "PASS",
        }

    def test_unreviewed_candidate_only_creates_card(self):
        payload = review.build_review([self.base_row()], [])
        self.assertEqual(len(payload["review_cards"]), 1)
        self.assertEqual(payload["transition_proposals"], [])
        self.assertIsNone(payload["killer_test"])
        self.assertFalse(payload["safety"]["scheduled_apply"])

    def test_inactive_unreviewed_candidate_is_not_shown(self):
        row = {**self.base_row(), "auto_active_today": "false"}
        payload = review.build_review([row], [])
        self.assertEqual(payload["review_cards"], [])

    def test_incomplete_promising_is_blocked(self):
        row = {**self.base_row(), "editor_judgment": "PROMISING"}
        payload = review.build_review([row], [])
        self.assertEqual(payload["transition_proposals"], [])
        self.assertIn("전이 차단", review.render_cards(payload))

    def test_complete_promising_creates_unapplied_s0_proposal(self):
        row = {
            **self.base_row(),
            "editor_judgment": "PROMISING",
            "editor_evidence_anchor": "MEASURED_PROBLEM_SIGNAL",
            "anchor_detail": "공식 집계에서 피해 37건",
            "anchor_scope": "서울·2026년",
            "central_question": "피해는 어느 자치구에 집중되는가?",
            "citizen_stake": "안전 손실",
            "competing_hypotheses": "노출 차이; 신고 차이",
            "decision_rule": "자치구 격차가 노출량 보정 뒤에도 유지",
            "reviewed_by": "editor",
            "reviewed_at": "2026-09-14T12:00:00+09:00",
            "review_revision": "rev123",
        }
        payload = review.build_review([row], [])
        self.assertEqual(len(payload["transition_proposals"]), 1)
        proposal = payload["transition_proposals"][0]
        self.assertEqual(proposal["proposed_stage"], "S0")
        self.assertEqual(proposal["proposed_upstream_gate"], "HOLD")
        self.assertFalse(proposal["applied"])
        self.assertTrue(proposal["approval_required"])

    def test_verify_never_creates_s0_proposal_but_can_plan_test(self):
        row = {
            **self.base_row(),
            "editor_judgment": "VERIFY",
            "minimum_test": "원자료 표를 확보한다",
            "test_timebox_hours": "4",
            "test_pass_rule": "지역별 값이 존재",
            "test_kill_rule": "총량만 존재",
        }
        payload = review.build_review([row], [])
        self.assertEqual(payload["transition_proposals"], [])
        self.assertEqual(payload["killer_test"]["test_status"], "PLANNED")
        self.assertEqual(payload["killer_test"]["test_evidence_ref"], "")

    def test_duplicate_requires_existing_parent(self):
        row = {
            **self.base_row(),
            "editor_judgment": "DUPLICATE",
            "duplicate_parent_id": "missing",
        }
        payload = review.build_review([row], [{"item_id": "real"}])
        self.assertIn("decision_blocker", payload["review_cards"][0])
        self.assertEqual(payload["transition_proposals"], [])

    def test_legacy_missing_source_is_not_auto_anchored(self):
        audit = [{"item_id": "one", "quality_gate": "PASS", "quality_score": "12", "evidence_anchor": ""}]
        ledger = [{"item_id": "one", "source_report": "missing/report.md", "stage_s": "S1", "editorial_e": "E3"}]
        rows = review.build_legacy_rereview(audit, ledger)
        self.assertEqual(rows[0]["source_status"], "SOURCE_REQUIRED")
        self.assertEqual(rows[0]["evidence_anchor"], "UNREVIEWED")
        self.assertEqual(rows[0]["action"], "원자료 복구 후 0점부터 재심사")


if __name__ == "__main__":
    unittest.main()
