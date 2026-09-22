import json
import tempfile
import unittest
from pathlib import Path

from source_exploration import build_source_exploration


class SourceExplorationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def put(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def rows(self, result):
        return {row["source_id"]: row for row in result["sources"]}

    def test_missing_outputs_are_not_zero_items(self):
        result = build_source_exploration(self.root, {})
        rows = self.rows(result)
        self.assertEqual(rows["daily_feed"]["status"], "결과 없음")
        self.assertIsNone(rows["daily_feed"]["observed"])
        self.assertEqual(rows["district_councils"]["status"], "결과 없음")
        self.assertEqual(rows["seoul_audit_results"]["status"], "결과 없음")
        self.assertEqual(result["clues"], [])
        self.assertNotIn("candidates", result)

    def test_failed_and_empty_daily_sources_are_distinct(self):
        self.put("source-scout-v1/output/daily_feed_latest.json", {
            "generated_at_kst": "2026-09-22T09:20:00+09:00",
            "metrics": [
                {"id": "failed", "name": "접속 실패 소스", "http_ok": False, "extracted": 0},
                {"id": "empty", "name": "새 항목 없는 소스", "http_ok": True, "extracted": 0},
                {"id": "council_minutes", "name": "서울시의회 회의록", "http_ok": True,
                 "extracted": 3, "qualified": 1},
            ],
            "editorial_triage": [{
                "source_id": "council_minutes", "source_name": "서울시의회 회의록",
                "triage_status": "EDITOR_REVIEW", "context_subject": "수어통역센터 지원",
                "display_fact": "의원이 수어통역센터 운영의 문제를 제기했다.",
                "triage_reason": "수치 기준기간 미확인",
                "source_date": "2026-09-11", "url": "https://example.org/minutes",
            }],
        })
        result = build_source_exploration(self.root, {"items": []})
        rows = self.rows(result)
        self.assertEqual(rows["failed"]["status"], "수집 실패")
        self.assertIsNone(rows["failed"]["observed"])
        self.assertEqual(rows["empty"]["status"], "수집됨 · 항목 없음")
        self.assertEqual(rows["empty"]["observed"], 0)
        self.assertEqual(rows["council_minutes"]["observed"], 3)
        self.assertEqual(result["clues"][0]["status"], "편집 검토 · 사실 미확인")
        self.assertEqual(result["clues"][0]["title"], "수어통역센터 지원")

    def test_shadow_and_first_page_watch_never_become_editorial_candidates(self):
        self.put("district-council-pilot/output/watch/state_latest.json", {
            "last_run": {"collected_at_kst": "2026-09-20T10:37:00+09:00",
                         "results": [{"status": "NEW_IN_VISIBLE_WINDOW", "new_count": 1},
                                     {"status": "UNKNOWN_COLLECTION", "new_count": 0}]},
        })
        self.put("source-onboarding-v1/output/audit-l4/state_latest.json", {
            "runs": [{"run_date_kst": "2026-09-21", "listing_status": "SUCCESS",
                      "selected_ids": ["123"],
                      "diagnostics": {"pdf_extracted": 1, "ready_questions": 0, "held_questions": 1}}],
            "records": [{"source_record_id": "123", "card": {
                "title": "기관운영 감사", "published_at": "2026-09-01",
                "detail_url": "https://example.org/audit", "question_status": "HOLD",
                "hold_reason": "지적 본문 미확인"}}],
        })
        self.put("interest-radar-v2/output/youtube_query_health_v2_3.json", [
            {"status": "ACTIVE", "last_run": "2026-09-21T09:00:00+09:00"},
            {"status": "PAUSED", "last_run": "2026-09-20T09:00:00+09:00"},
        ])
        result = build_source_exploration(self.root, {"items": []})
        rows = self.rows(result)
        self.assertEqual(rows["district_councils"]["review_count"], 0)
        self.assertIn("새 주소 1건", rows["district_councils"]["reason"])
        self.assertIn("본문", rows["district_councils"]["reason"])
        self.assertEqual(rows["seoul_audit_results"]["status"], "그림자 검토")
        self.assertEqual(rows["youtube_interest"]["review_count"], 0)
        self.assertEqual(result["clues"][0]["status"], "본문 검토 보류")
        self.assertNotIn("candidates", result)


if __name__ == "__main__":
    unittest.main()
