import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("editorial_pipeline", Path(__file__).with_name("pipeline.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BASE = {"id": "one", "family": "서울시의회", "source": "서울시의회 회의록",
        "headline": "새 사업의 접근성", "url": "https://example.org/1",
        "evidence_text": "이 사업을 새로 시작하면서 대상별 접근 방식이 달라졌습니다.",
        "date": "2026-09-22", "claim_status": "의원 발언·미검증"}
GOOD = {"id": "one", "verdict": "PROPOSE", "issue_key": "접근 방식",
        "title": "새 사업의 이용 경로는 누구에게 열리는가",
        "subject": "대상에 따라 서로 다른 접근 경로가 있는 서울 신규 사업",
        "why_now": "새 사업이 시작돼 이용 경로를 선택해야 하는 시점이다",
        "citizen_question": "지원 대상마다 어디서 신청하고 무엇을 포기해야 하는가?",
        "uncommon_question": "같은 자격인데 신청 경로에 따라 실제 이용 가능성이 달라지는가?",
        "first_check": "공식 접수 기준과 접수·탈락 사례를 나란히 확인한다",
        "counterhypothesis": "경로는 달라도 실제 이용 자격과 처리 속도는 같을 수 있다",
        "scene_path": "신청 현장, 담당자, 두 경로의 이용자를 취재한다",
        "anchor_quote": "이 사업을 새로 시작하면서 대상별 접근 방식이 달라졌습니다.",
        "reason": "신청 방식의 차이가 이용 기회를 바꿀 수 있는지 확인할 가치가 있다"}


class PipelineTests(unittest.TestCase):
    def test_ungrounded_quote_is_held(self):
        bad = {**GOOD, "anchor_quote": "원문에 없는 피해가 확인됐다"}
        proposals, holds = module.assess_result([BASE], {"assessments": [bad]})
        self.assertEqual(proposals, [])
        self.assertEqual(holds[0]["reason"], "원문 인용 불일치")

    def test_generic_question_is_held(self):
        bad = {**GOOD, "citizen_question": "시민에게 어떤 영향이 있는가?"}
        proposals, _ = module.assess_result([BASE], {"assessments": [bad]})
        self.assertEqual(proposals, [])

    def test_single_source_and_issue_dedup(self):
        second = {**BASE, "id": "two", "url": "https://example.org/2"}
        other = {**GOOD, "id": "two", "title": "두 번째 다른 기획 제목이 있는가"}
        proposals, holds = module.assess_result([BASE, second], {"assessments": [GOOD, other]})
        self.assertEqual(len(proposals), 1)
        self.assertEqual(holds[0]["reason"], "같은 소스 계열 또는 사안 중복")

    def test_missing_assessment_is_held(self):
        proposals, holds = module.assess_result([BASE], {"assessments": []})
        self.assertEqual(proposals, [])
        self.assertEqual(holds[0]["reason"], "모델 평가 누락")

    def test_prior_lead_requires_anchor_not_only_shared_url(self):
        lead = {"source_url": BASE["url"], "title": "수어통역센터 재정",
                "anchor_text": "수어통역센터는 자체수입이 발생해도"}
        self.assertEqual(module.excluded(BASE, [lead], set()), "")
        matched = {**BASE, "evidence_text": lead["anchor_text"] + " 서비스에 영향을 준다"}
        self.assertEqual(module.excluded(matched, [lead], set()), "기존 취재 착수 사안")

    def test_reviewed_id_is_skipped(self):
        self.assertEqual(module.excluded(BASE, [], {"one"}), "사람 판정 완료·보류")

    def test_sources_require_body_or_context(self):
        old_root = module.ROOT
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "interest-signal-pilot/output").mkdir(parents=True)
            (root / "source-scout-v1/output").mkdir(parents=True)
            (root / "source-onboarding-v1/output/audit-l4").mkdir(parents=True)
            (root / "interest-signal-pilot/output/review_queue_latest.json").write_text(json.dumps(
                {"items": [{"headline": "제목만", "source_context_status": "TITLE_ONLY"},
                           {"headline": "본문", "publisher_url": "https://example.org/news",
                            "source_context_status": "BODY_READ",
                            "content_assessment": {"anchor_quote": "본문에서 확인한 연속 구절입니다",
                                                   "what_happened": "구체적인 사건 서술",
                                                   "question_worth": "HIGH"}}]}), encoding="utf-8")
            (root / "source-scout-v1/output/daily_feed_latest.json").write_text(json.dumps(
                {"editorial_triage": [{"source_id": "council_minutes", "url": "https://example.org/council",
                                       "text": "새 사업에 관한 의원 발언의 구체적 원문이 충분히 길게 저장돼 있습니다. 실제 세부 내용은 주장 상태로만 취급합니다."}]}),
                encoding="utf-8")
            (root / "source-onboarding-v1/output/audit-l4/state_latest.json").write_text(
                json.dumps({"runs": [], "records": []}), encoding="utf-8")
            try:
                module.ROOT = root
                records, gaps = module.source_inputs()
                self.assertEqual({x["family"] for x in records}, {"뉴스·시민 관심", "서울시의회"})
                self.assertTrue(any(x["source"] == "25개 자치구의회" for x in gaps))
            finally:
                module.ROOT = old_root


if __name__ == "__main__":
    unittest.main()
