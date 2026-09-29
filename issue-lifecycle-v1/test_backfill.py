#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import backfill
import pipeline


class HistoricalBackfillTests(unittest.TestCase):
    def test_historical_seed_gets_reserved_slot(self):
        current = [{
            "source_id": "council_minutes",
            "source_name": "서울시의회 회의록",
            "speech_date": f"2026-09-{day:02d}",
            "url": f"https://example.test/current-{day}",
            "text": "현재 의회 단서의 충분히 긴 원문 문장입니다. " * 5,
        } for day in (20, 21, 22)]
        historical = {
            "historical_seed": True,
            "source_id": "gangseo",
            "source_name": "강서구의회",
            "meeting_date": "2025-09-10",
            "document_url": "https://example.test/historical",
            "context_subject": "통학로 안전시설 미설치",
            "text": "과거 지적과 행정 의무를 설명하는 충분히 긴 문장입니다. " * 5,
        }
        rows = pipeline.collect_seed_records([current, {"historical_seeds": [historical]}], 3)
        self.assertEqual(3, len(rows))
        self.assertIn("HISTORICAL", {row["seed_kind"] for row in rows})

    def test_track_extract_requires_source_quote(self):
        answer = {
            "verdict": "TRACK",
            "issue_title": "통학로 안전시설",
            "anchor_quote": "본문에 실제로 존재하지 않는 길고 구체적인 인용입니다.",
            "observed_problem": "설치 지연",
            "responsible_body": "강서구",
            "affected_group": "학생과 학부모",
            "public_obligation": "통학로 안전시설 설치",
            "promise_or_deadline": "명시적 약속·기한 없음",
            "search_keywords": ["통학로 안전시설", "어린이보호구역 시설"],
            "reason": "추적 필요",
        }
        with self.assertRaises(ValueError):
            backfill.validate_extract(answer, "다른 본문")

    def test_discovery_keeps_only_historical_window(self):
        def fake_fetch(_key, **params):
            return {"LIST": [
                {"ROW": {
                    "DOCID": "CLIKC123456",
                    "RASMBLY_ID": params["rasmblyId"],
                    "MTG_DE": "20250910",
                }},
                {"ROW": {
                    "DOCID": "CLIKC999999",
                    "RASMBLY_ID": params["rasmblyId"],
                    "MTG_DE": "20260910",
                }},
            ]}
        sources = [{"id": "gangseo", "name": "강서구", "clik_assembly_id": "002005"}]
        with patch.object(pipeline, "fetch_payload", side_effect=fake_fetch):
            rows = backfill.discover(
                "secret", sources, date(2025, 3, 1), date(2025, 12, 31), per_query=5)
        self.assertEqual(1, len(rows))
        self.assertEqual("2025-09-10", rows[0]["meeting_date"])

    def test_no_followup_cannot_become_unresolved(self):
        self.assertEqual(
            "NO_MATCH",
            pipeline.lifecycle_status(
                date(2025, 9, 1), date(2026, 9, 1), "NO_MATCH"),
        )


if __name__ == "__main__":
    unittest.main()
