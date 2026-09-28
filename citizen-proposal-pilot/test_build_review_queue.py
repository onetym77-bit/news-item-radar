import unittest

from build_review_queue import build_queue, empty_queue, public_item
from publish_review_queue import publish

def shadow_item(**overrides):
    item = {
        "id": "0123456789abcdef",
        "family": "시민제안",
        "production_eligible": False,
        "briefing_output": "NONE",
        "title": "방문 신청 과정의 반복 불편",
        "date": "2026-09-28",
        "url": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=1",
        "subject": "신청 과정에서 발생하는 접근 장벽",
        "why_now": "새 절차 적용 뒤 실제 이용 경험 확인이 필요함",
        "citizen_question": "같은 조건의 시민에게 같은 불편이 반복되는가?",
        "uncommon_question": "안내 부족과 절차 설계 중 무엇이 더 큰 원인인가?",
        "first_check": "공식 안내와 실제 신청 절차를 대조한다.",
        "decisive_test": "동일 조건 신청자와 담당 부서 기록을 대조한다.",
        "counterhypothesis": "개인 오해 또는 일회성 오류일 수 있다.",
        "scene_path": "신청 현장과 담당 부서 답변을 함께 확인한다.",
        "anchor_quote": "저는 신청했지만 방문 때문에 시간이 부담됐습니다",
        "claim_status": "시민 제안자 진술·미검증",
        "editorial_risk": "개인 사례를 구조 문제로 과장할 위험",
        "independent_review": "반복 여부를 확인할 수 있어 검토 가치가 있음",
    }
    item.update(overrides)
    return item

class CitizenReviewQueueTests(unittest.TestCase):
    def test_public_queue_keeps_shadow_boundary_and_redacts(self):
        raw = shadow_item(
            title="제 이름은 홍길동, 방문 신청 문제",
            anchor_quote="저는 세종대로 110에서 신청했지만 01012345678 연락 뒤에도 불편했습니다",
        )
        result = build_queue({"shadow_reviews": [raw]}, empty_queue(), [])
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertFalse(item["production_eligible"])
        self.assertEqual(item["briefing_output"], "NONE")
        self.assertNotIn("홍길동", str(item))
        self.assertNotIn("01012345678", str(item))
        self.assertNotIn("세종대로 110", str(item))
        self.assertLessEqual(len(item["anchor_quote"]), 240)

    def test_non_shadow_or_non_official_item_is_rejected(self):
        self.assertIsNone(public_item(shadow_item(production_eligible=True)))
        self.assertIsNone(public_item(shadow_item(url="https://example.com/item")))

    def test_decided_item_is_removed_and_not_readded(self):
        queue = build_queue({"shadow_reviews": [shadow_item()]}, empty_queue(), [])
        result = build_queue(
            {"shadow_reviews": [shadow_item()]},
            queue,
            [{"id": "0123456789abcdef", "decision": "HOLD"}],
        )
        self.assertEqual(result["items"], [])

    def test_publisher_does_not_restore_decided_artifact_item(self):
        candidate = build_queue({"shadow_reviews": [shadow_item()]}, empty_queue(), [])
        result = publish(
            candidate,
            empty_queue(),
            [{"id": "0123456789abcdef", "decision": "DISCARD"}],
        )
        self.assertEqual(result["items"], [])

    def test_unchanged_queue_preserves_timestamp(self):
        queue = build_queue({"shadow_reviews": [shadow_item()]}, empty_queue(), [])
        again = build_queue({"shadow_reviews": [shadow_item()]}, queue, [])
        self.assertEqual(again, queue)

if __name__ == "__main__":
    unittest.main()
