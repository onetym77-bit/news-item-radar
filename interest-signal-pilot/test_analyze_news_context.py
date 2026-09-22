#!/usr/bin/env python3
"""Offline regression tests for the publisher-body review boundary."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE = Path(__file__).with_name("analyze_news_context.py")
spec = importlib.util.spec_from_file_location("analyze_news_context", MODULE)
context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(context)


class NewsContextTests(unittest.TestCase):
    def test_title_match_rejects_different_story(self):
        self.assertTrue(context.titles_match(
            "강서구 통학버스 비용 부담 커져 - 서울신문",
            "강서구 통학버스 비용 부담 커져",
        ))
        self.assertFalse(context.titles_match(
            "강서구 통학버스 비용 부담 커져",
            "강서구 재개발 갈등 조정 회의 개최",
        ))

    def test_extract_body_uses_article_not_navigation(self):
        body = "시민이 실제로 겪은 일을 기사에 적었습니다. " * 20
        document = "<nav>관계없는 메뉴</nav><article><h1>제목</h1><p>" + body + "</p></article>"
        self.assertIn("시민이 실제로", context.extract_body(document))
        self.assertNotIn("관계없는 메뉴", context.extract_body(document))

    def test_bad_quote_is_rejected(self):
        value = {
            "document_type": "INCIDENT", "claim_type": "OBSERVED_EVENT",
            "what_happened": "사건", "citizen_relevance": "주민",
            "question_worth": "HIGH", "editorial_question": "해당 주민은 왜 이 비용을 부담하는가?",
            "missing_check": "당사자 확인", "counterpossibility": "일시적 사례",
            "anchor_quote": "본문에 없는 근거 문장", "reason": "실제 비용",
        }
        with self.assertRaisesRegex(ValueError, "ungrounded_quote"):
            context.validated_assessment(value, "본문에는 실제 비용이 표시되어 있습니다.")

    def test_promotion_cannot_emit_question(self):
        body = "구청은 지원센터를 새로 열겠다고 발표했습니다."
        value = {
            "document_type": "PROMOTION", "claim_type": "ANNOUNCEMENT",
            "what_happened": "지원센터 발표", "citizen_relevance": "",
            "question_worth": "HIGH", "editorial_question": "새 지원센터가 주민에게 필요한가?",
            "missing_check": "대상 확인", "counterpossibility": "기존 서비스 이용 가능",
            "anchor_quote": "지원센터를 새로 열겠다고 발표했습니다", "reason": "정책 발표",
        }
        assessed = context.validated_assessment(value, body)
        self.assertEqual(assessed["editorial_question"], "")
        self.assertEqual(assessed["question_worth"], "UNCLEAR")

    def test_unavailable_body_stays_unassessed(self):
        queue = {"items": [{
            "headline": "서울 기사", "evidence": [{"type": "news_search_result", "url": "https://news.google.com/a"}],
            "problem_status": "UNASSESSED", "promotion_status": "HOLD",
        }]}
        with patch.object(context, "resolve_publisher", return_value=(None, "NO_TITLE_MATCH")):
            result = context.analyze(queue, "id", "secret", "key", "test", 1, 1)
        item = result["items"][0]
        self.assertEqual(item["source_context_status"], "BODY_UNAVAILABLE")
        self.assertEqual(item["problem_status"], "UNASSESSED")
        self.assertEqual(result["context_review"]["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
