import json
import tempfile
import unittest
from pathlib import Path

from build_review_queue import build_queue, empty_queue
from record_shadow_decision import record

def card():
    return {
        "id": "0123456789abcdef",
        "family": "시민제안",
        "production_eligible": False,
        "briefing_output": "NONE",
        "title": "방문 신청 과정의 반복 불편",
        "date": "2026-09-28",
        "url": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=1",
        "subject": "신청 과정 접근 장벽",
        "why_now": "실제 경험 확인 필요",
        "citizen_question": "같은 불편이 반복되는가?",
        "uncommon_question": "안내와 절차 중 원인은 무엇인가?",
        "first_check": "공식 절차와 현장을 대조한다.",
        "decisive_test": "동일 조건 신청자 기록을 대조한다.",
        "counterhypothesis": "일회성 오류일 수 있다.",
        "scene_path": "신청 현장과 담당 부서를 확인한다.",
        "anchor_quote": "저는 신청했지만 방문 때문에 시간이 부담됐습니다",
        "claim_status": "시민 제안자 진술·미검증",
        "editorial_risk": "개인 사례 일반화 위험",
        "independent_review": "반복 여부 확인 필요",
    }

class CitizenShadowDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.queue = root / "queue.json"
        self.decisions = root / "decisions.json"
        queue = build_queue({"shadow_reviews": [card()]}, empty_queue(), [])
        self.queue.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_records_exact_current_id(self):
        row = record(
            "0123456789abcdef", "PROMISING", " 현장 확인 가치 있음 ",
            queue_path=self.queue, decisions_path=self.decisions,
        )
        self.assertEqual(row["decision"], "PROMISING")
        self.assertEqual(row["note"], "현장 확인 가치 있음")
        stored = json.loads(self.decisions.read_text(encoding="utf-8"))
        self.assertEqual(stored[0]["id"], "0123456789abcdef")

    def test_rejects_unknown_or_duplicate_id(self):
        with self.assertRaisesRegex(ValueError, "없는 ID"):
            record("ffffffffffffffff", "HOLD", "", queue_path=self.queue, decisions_path=self.decisions)
        record("0123456789abcdef", "HOLD", "", queue_path=self.queue, decisions_path=self.decisions)
        with self.assertRaisesRegex(ValueError, "이미 판정"):
            record("0123456789abcdef", "DISCARD", "", queue_path=self.queue, decisions_path=self.decisions)

if __name__ == "__main__":
    unittest.main()
