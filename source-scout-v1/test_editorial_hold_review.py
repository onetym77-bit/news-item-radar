import importlib.util
import json
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_injector():
    spec = importlib.util.spec_from_file_location(
        "editorial_hold_review_test", HERE / "inject_feed_into_briefing.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("inject_feed_into_briefing.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


injector = load_injector()


class EditorialHoldReviewTests(unittest.TestCase):
    def test_selected_hold_is_visible_but_not_promoted(self):
        source_url = "https://example.test/council"
        feed = {
            "context_holds": [{
                "source_id": "council_minutes",
                "url": source_url,
                "text": "위기 10대 여성 지원 시설 4개 중 3개소가 문을 닫았습니다.",
                "context_text": "",
                "context_status": "HOLD",
                "context_missing_fields": ["수치 기준기간"],
                "speech_date": "2026-09-11",
            }]
        }
        leads = [{
            "selected_on": "2026-09-17",
            "title": "위기 여성 청소년 보호시설 폐쇄 뒤 대체 지원",
            "source_id": "council_minutes",
            "source_url": source_url,
            "anchor_text": "위기 10대 여성 지원 시설",
            "editorial_question": "대체 지원이 보호 공백을 메우는가?",
            "first_check": "폐쇄 시설과 보호 정원을 확인",
        }]
        result = injector.render(feed, {}, leads)
        editorial = result.split("## C-실험.", 1)[0]
        self.assertIn("편집자 지정 · 취재 착수 검토", editorial)
        self.assertIn("원문 상태: HOLD", editorial)
        self.assertIn("미확인: 수치 기준기간", editorial)
        self.assertIn("발언 요지(미검증)", editorial)
        self.assertIn("이 영역은 A·B 기사·검증 게이트와 별개", editorial)
        self.assertNotIn("S0 전이 승인 대기", editorial)

    def test_missing_current_source_is_flagged(self):
        leads = [{
            "title": "시험 사안",
            "source_id": "council_minutes",
            "source_url": "https://example.test/source",
            "anchor_text": "없는 발언",
            "editorial_question": "무엇을 확인할까?",
            "first_check": "원문 재확인",
        }]
        result = injector.render({"context_holds": []}, {}, leads)
        self.assertIn("오늘 수집본에서 해당 발언 조각 미발견", result)


if __name__ == "__main__":
    unittest.main()
