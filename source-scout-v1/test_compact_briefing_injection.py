import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_injector():
    spec = importlib.util.spec_from_file_location(
        "compact_source_briefing_test", HERE / "inject_feed_into_briefing.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("inject_feed_into_briefing.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


injector = load_injector()


class CompactSourceBriefingTests(unittest.TestCase):
    def test_briefing_keeps_decision_and_removes_evidence_excerpts(self):
        feed = {
            "core_discovery": [
                {
                    "context_subject": "위기 청소년 지원 공백",
                    "question": "시설 폐쇄 뒤 실제 보호 공백이 생겼나?",
                    "source_name": "서울시의회 회의록",
                    "speech_date": "2026-09-11",
                    "url": "https://example.test/council",
                    "display_fact": "브리핑에서 제외할 긴 근거 문장",
                    "text": "브리핑에서 제외할 발언 조각",
                }
            ],
            "auxiliary_discovery": [],
            "localization_discovery": [],
            "context_holds": [
                {
                    "text": "보류된 긴 발언 원문",
                    "context_reason": "수치 기준기간 미확인",
                }
            ],
            "rediscovered_carryover": [{"text": "중복 원문 상세"}],
            "stale_carryover": [{"text": "오래된 원문 상세"}],
            "archived_stale": [],
            "freshness_holds": [],
            "activity_baselines": [],
            "verification_metadata_leads": [{"text": "데이터셋 설명 원문"}],
            "verification_schema_leads": [],
            "metrics": [
                {
                    "name": "한국소비자원",
                    "http_ok": False,
                    "status_detail": "FETCH_FAILED",
                    "error": "인증서 오류 상세",
                }
            ],
        }

        rendered = injector.render(feed)

        self.assertIn("오늘 사람이 검토할 새 질문 후보는 1건", rendered)
        self.assertIn("위기 청소년 지원 공백", rendered)
        self.assertIn("시설 폐쇄 뒤 실제 보호 공백이 생겼나?", rendered)
        self.assertIn("문맥 미확정 1건", rendered)
        self.assertIn("이미 본 원문 1건", rendered)
        self.assertIn("실제 값 미확인 데이터 1건", rendered)
        self.assertIn("한국소비자원: FETCH_FAILED", rendered)
        self.assertNotIn("브리핑에서 제외할 긴 근거 문장", rendered)
        self.assertNotIn("브리핑에서 제외할 발언 조각", rendered)
        self.assertNotIn("보류된 긴 발언 원문", rendered)
        self.assertNotIn("중복 원문 상세", rendered)
        self.assertNotIn("오래된 원문 상세", rendered)
        self.assertNotIn("데이터셋 설명 원문", rendered)
        self.assertNotIn("인증서 오류 상세", rendered)
        self.assertNotIn("발언 조각:", rendered)
        self.assertNotIn("데이터 구조 확인", rendered)

    def test_empty_day_leads_with_largest_bottleneck(self):
        feed = {
            "core_discovery": [],
            "auxiliary_discovery": [],
            "localization_discovery": [],
            "context_holds": [{}, {}, {}],
            "rediscovered_carryover": [{}],
            "stale_carryover": [],
            "archived_stale": [],
            "freshness_holds": [],
            "activity_baselines": [],
            "verification_metadata_leads": [],
            "verification_schema_leads": [],
            "metrics": [],
        }

        rendered = injector.render(feed)

        self.assertIn("오늘 새 질문 후보는 없습니다", rendered)
        self.assertIn("가장 큰 병목은 문맥 미확정 3건", rendered)
        self.assertIn("### 오늘 검토할 후보\n\n- 없음", rendered)


if __name__ == "__main__":
    unittest.main()
