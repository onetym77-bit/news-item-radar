import json
import tempfile
import unittest
from pathlib import Path

from build_youtube_review_queue import build_queue, empty_queue, validate_queue
from publish_youtube_review_queue import publish
from record_youtube_shadow_decision import record


def assessment(item_id="a" * 16, verdict="REVIEW", url="https://www.youtube.com/watch?v=video123"):
    return {
        "cluster_id": item_id,
        "search_cluster_name": "주거비 때문에 이동",
        "verdict": verdict,
        "anchor_url": url,
        "anchor_quote": "제가 서울에서 월세 때문에 이사했습니다 test@example.com",
        "observed_pattern": "서로 다른 시민 영상에서 월세 부담 뒤 이사 선택이 나타난다.",
        "seoul_connection": "영상 내용에서 서울 거주와 이동 지역을 직접 밝힌다.",
        "repetition_basis": "서로 다른 두 채널에서 같은 선택이 반복된다.",
        "citizen_stake_to_check": "자발적 이동인지 비용 때문에 밀려난 것인지 확인해야 한다.",
        "test_question": "서울 세입자의 이사가 월세 상승 때문에 강제된 선택이었는가?",
        "alternative_explanation": "직장 이동이나 가족 변화가 주된 이유였을 수 있다.",
        "first_check": "당사자에게 이사 전후 비용과 다른 이사 이유를 확인한다.",
        "scene_path": "이사 전후 주거지와 계약서, 당사자 인터뷰를 비교한다.",
        "reason": "제목·설명의 반복 신호이며 사실과 대표성은 아직 확인되지 않았다.",
        "source_stage": "유튜브 의미 검증 그림자",
        "claim_status": "영상 서술·미검증",
        "production_eligible": False,
        "briefing_output": "NONE",
    }


class YoutubeReviewQueueTests(unittest.TestCase):
    def test_review_becomes_bounded_shadow_card(self):
        shadow = {
            "generated_at_kst": "2026-09-28T15:00:00+09:00",
            "assessments": [assessment()],
        }
        result = build_queue(shadow, empty_queue(), [])
        self.assertEqual(len(result["items"]), 1)
        item = result["items"][0]
        self.assertEqual(item["id"], "a" * 16)
        self.assertNotIn("test@example.com", item["anchor_quote"])
        self.assertLessEqual(len(item["anchor_quote"]), 240)
        self.assertFalse(item["production_eligible"])
        self.assertEqual(item["briefing_output"], "NONE")
        validate_queue(result)

    def test_hold_bad_url_or_automatic_promotion_is_rejected(self):
        hold = assessment("b" * 16, verdict="HOLD")
        bad_url = assessment("c" * 16, url="https://example.com/watch?v=x")
        promoted = assessment("d" * 16)
        promoted["production_eligible"] = True
        shadow = {"assessments": [hold, bad_url, promoted]}
        self.assertEqual(build_queue(shadow, empty_queue(), [])["items"], [])

    def test_decided_artifact_item_is_not_restored(self):
        candidate = build_queue({"assessments": [assessment()]}, empty_queue(), [])
        decisions = [{"id": "a" * 16, "decision": "DISCARD"}]
        self.assertEqual(publish(candidate, empty_queue(), decisions)["items"], [])

    def test_record_requires_exact_current_id_and_rejects_duplicate(self):
        queue = build_queue({"assessments": [assessment()]}, empty_queue(), [])
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            queue_path = base / "queue.json"
            decisions_path = base / "decisions.json"
            queue_path.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")
            decisions_path.write_text("[]", encoding="utf-8")
            row = record("a" * 16, "PROMISING", "검토 가치", queue_path=queue_path, decisions_path=decisions_path)
            self.assertEqual(row["decision"], "PROMISING")
            with self.assertRaisesRegex(ValueError, "이미 판정"):
                record("a" * 16, "HOLD", "", queue_path=queue_path, decisions_path=decisions_path)
            with self.assertRaisesRegex(ValueError, "없는 ID"):
                record("f" * 16, "HOLD", "", queue_path=queue_path, decisions_path=decisions_path)


if __name__ == "__main__":
    unittest.main()
