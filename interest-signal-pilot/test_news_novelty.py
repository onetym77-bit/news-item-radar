import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NewsNoveltyTests(unittest.TestCase):
    def test_collector_seeds_seen_keys_from_previous_snapshot(self):
        module = load_module("collect_interest_signals_test", "interest-signal-pilot/collect_interest_signals.py")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            module.SEEN = root / "seen.json"
            module.OUT = root / "latest.json"
            module.OUT.write_text(json.dumps({
                "news_signals": [{"title": "서울의 오래된 기사 - 매체"}]
            }, ensure_ascii=False), encoding="utf-8")
            self.assertIn(module.title_key("서울의 오래된 기사 - 매체"), module.load_seen_keys())

    def test_review_queue_contains_only_unseen_articles(self):
        module = load_module("build_review_queue_test", "interest-signal-pilot/build_review_queue.py")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            module.INPUT = root / "signals.json"
            module.OUTPUT = root / "queue.json"
            module.INPUT.write_text(json.dumps({
                "generated_at_utc": "2026-09-29T00:00:00+00:00",
                "quality_gate": {"seen_news_count": 1},
                "news_signals": [
                    {"title": "새 기사 - 매체", "url": "https://example.com/new",
                     "query": "서울 시민 부담", "published_at": "Tue, 29 Sep 2026 00:00:00 GMT",
                     "editorial_reason": "새 단서", "is_new": True},
                    {"title": "지난 기사 - 매체", "url": "https://example.com/old",
                     "query": "서울 시민 부담", "published_at": "Mon, 28 Sep 2026 00:00:00 GMT",
                     "editorial_reason": "기존 단서", "is_new": False},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            module.main()
            result = json.loads(module.OUTPUT.read_text(encoding="utf-8"))
            self.assertEqual(result["review_count"], 1)
            self.assertEqual(result["items"][0]["headline"], "새 기사")
            self.assertTrue(result["items"][0]["is_new"])

    def test_integrated_head_rejects_seen_news_and_stale_council_rows(self):
        module = load_module("editorial_pipeline_novelty_test", "editorial-v4/pipeline.py")
        article = {
            "source_context_status": "BODY_READ",
            "publisher_url": "https://example.com/new",
            "headline": "서울의 새로운 시민 부담",
            "published_at": "2026-09-29",
            "is_new": True,
            "content_assessment": {
                "document_type": "INCIDENT", "question_worth": "HIGH",
                "anchor_quote": "서울 시민이 새로 겪는 구체적인 부담이 확인됐다는 기사 문장입니다.",
                "what_happened": "이번 회차에 처음 포착된 사건의 구체적인 경위",
                "citizen_relevance": "서울 시민의 비용과 이용 선택에 직접 연결",
                "editorial_question": "누가 어떤 기준으로 부담을 떠안게 됐나?",
                "counterpossibility": "일시적 사례일 수 있음",
            },
        }
        old = {**article, "publisher_url": "https://example.com/old",
               "headline": "지난 회차 기사", "is_new": False}
        stale_council = {
            "source_id": "council_minutes", "freshness_status": "STALE_CARRYOVER",
            "text": "오래된 회의록 발언 " * 10, "url": "https://example.com/minutes",
            "source_date": "2026-09-11", "context_subject": "오래된 사안",
            "context_text": "이미 여러 차례 검토한 오래된 회의록 문맥입니다.",
        }
        documents = {
            "interest-signal-pilot/output/review_queue_latest.json": {"items": [old, article]},
            "source-scout-v1/output/daily_feed_latest.json": {
                "editorial_triage": [stale_council], "stale_carryover": [stale_council],
                "metrics": [{"id": "council_minutes", "stale_carryover": 1, "context_holds": 0}],
            },
            "source-onboarding-v1/output/audit-l4/state_latest.json": {},
            "editorial-v4/output/youtube_shadow_latest.json": {},
        }
        original_read = module.read
        module.read = lambda path, fallback: documents.get(path, fallback)
        try:
            records, gaps = module.source_inputs()
        finally:
            module.read = original_read
        self.assertEqual([row["headline"] for row in records], ["서울의 새로운 시민 부담"])
        council_gap = next(row for row in gaps if row["source"] == "서울시의회")
        self.assertIn("오래된 이월 자료 1건은 재평가에서 제외", council_gap["reason"])


if __name__ == "__main__":
    unittest.main()
