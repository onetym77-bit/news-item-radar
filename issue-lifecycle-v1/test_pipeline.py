#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from unittest.mock import patch
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pipeline


class IssueLifecycleTests(unittest.TestCase):
    def test_missing_optional_seed_is_reported_and_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            available = Path(directory) / "available.json"
            missing = Path(directory) / "missing.json"
            available.write_text('{"source": "available"}', encoding="utf-8")

            payloads, loaded, absent = pipeline.load_seed_payloads([available, missing])

        self.assertEqual([{"source": "available"}], payloads)
        self.assertEqual([str(available)], loaded)
        self.assertEqual([str(missing)], absent)

    def test_all_seed_inputs_missing_is_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                pipeline.load_seed_payloads([Path(directory) / "missing.json"])

    def test_collects_city_and_district_signals(self):
        payloads = [{
            "stale_carryover": [{
                "source_id": "council_minutes",
                "source_name": "서울시의회 회의록",
                "speech_date": "2026-09-11",
                "url": "https://example.test/city",
                "context_subject": "시내버스 통상임금",
                "context_text": "서울시는 판결 뒤 실행계획을 마련해야 했으나 일정이 제시되지 않았다는 발언입니다. " * 2,
                "question": "판결 뒤 실행계획과 실제 지급 일정은 어떻게 달라졌는가?",
            }],
            "results": [{
                "source_id": "gangseo",
                "source_name": "강서구",
                "meeting_date": "2026-09-20",
                "document_url": "https://example.test/district",
                "verification_card": {
                    "observed_issue": "학교 주변 통학 안전시설이 계획 뒤에도 설치되지 않았다는 의원 발언",
                    "anchor_quote": "통학로 안전시설 설치가 아직 완료되지 않았습니다.",
                    "test_question": "계획된 시설 가운데 완료되지 않은 구간은 어디인가?",
                    "first_check": "설치대장과 현장 확인",
                },
            }],
        }]
        rows = pipeline.collect_seed_records(payloads, 5)
        self.assertEqual(2, len(rows))
        self.assertEqual({"council_minutes", "gangseo"}, {row["source_id"] for row in rows})

    def test_duplicate_seed_is_removed(self):
        row = {
            "source_id": "council_minutes",
            "source_name": "서울시의회 회의록",
            "speech_date": "2026-09-11",
            "url": "https://example.test/same",
            "text": "동일한 문제를 설명하는 충분히 긴 회의록 문장입니다. " * 5,
        }
        self.assertEqual(1, len(pipeline.collect_seed_records([[row, row]], 3)))

    def test_broad_keyword_is_rejected(self):
        value = {
            "issue_title": "돌봄 공백",
            "responsible_body": "서울시",
            "affected_group": "돌봄 이용자",
            "place_scope": "서울",
            "public_obligation": "서비스 제공",
            "failure_mode": "대기 장기화",
            "search_keywords": ["문제", "돌봄 대기"],
        }
        with self.assertRaises(ValueError):
            pipeline.validate_signature(value)

    def test_search_continues_after_one_source_fails(self):
        sources = [
            {"id": "good", "name": "정상 의회", "clik_assembly_id": "002001"},
            {"id": "bad", "name": "오류 의회", "clik_assembly_id": "002002"},
        ]
        signature = {"search_keywords": ["돌봄 공백", "지원 중단"]}

        def fake_fetch(_api_key, **params):
            if params["rasmblyId"] == "002002":
                raise ValueError("unexpected envelope")
            return {"LIST": []}

        with patch.object(pipeline, "fetch_payload", side_effect=fake_fetch):
            result = pipeline.search_api(
                "secret", sources, signature, date(2025, 1, 1), date(2026, 9, 29)
            )

        self.assertEqual(2, result["successful_requests"])
        self.assertEqual(2, len(result["errors"]))
        self.assertEqual([], result["rows"])
        self.assertEqual({"bad"}, {row["source_id"] for row in result["errors"]})

    def test_lifecycle_status_requires_elapsed_time(self):
        old = date(2025, 9, 1)
        recent = date(2026, 9, 10)
        self.assertEqual(
            "REPEATED_AFTER_9M",
            pipeline.lifecycle_status(old, recent, "SAME_UNRESOLVED"),
        )
        self.assertEqual(
            "REPEATED_WITHIN_9M",
            pipeline.lifecycle_status(date(2026, 5, 1), recent, "SAME_UNRESOLVED"),
        )

    def test_silence_is_not_unresolved(self):
        payload = {
            "seed_count": 1,
            "source_count": 26,
            "lookback_months": 18,
            "evidence_count": 0,
            "errors": [],
            "results": [{
                "source_name": "서울시의회",
                "document_url": "https://example.test/seed",
                "signature": {"issue_title": "시설 공백"},
                "matches": [],
            }],
        }
        rendered = pipeline.render(payload)
        self.assertIn("미해결로 간주하지 않음", rendered)
        self.assertNotIn("미해결 확인", rendered)

    def test_comparison_quote_must_exist(self):
        value = {
            "relation": "SAME_UNRESOLVED",
            "anchor_quote": "본문에 존재하지 않는 긴 인용문입니다.",
            "why_same": "같은 시설",
            "status_basis": "지속",
            "citizen_stake": "이용 공백",
            "next_check": "현장 확인",
        }
        with self.assertRaises(ValueError):
            pipeline.validate_comparison(value, "다른 본문")


if __name__ == "__main__":
    unittest.main()
