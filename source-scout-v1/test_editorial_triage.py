import importlib.util
import json
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


collector = load_module("editorial_triage_collector_test", "collect_daily_feed.py")
injector = load_module("editorial_triage_injector_test", "inject_feed_into_briefing.py")


class EditorialTriageTests(unittest.TestCase):
    def row(self):
        return {
            "source_id": "council_minutes",
            "context_status": "HOLD",
            "precheck_status": "PASS",
            "freshness_status": "FRESH",
            "context_missing_fields": ["수치 기준기간"],
            "seoul_scope": True,
            "source_date": "2026-09-11",
            "speaker": "의원",
            "context_subject": "국회대로 공사 지연",
            "affected_group": "인근 주민과 상인",
            "url": "https://example.test/record",
            "score": 8,
            "signals": {"problem": True, "loss": True},
            "text": "공사 지연으로 주민 불편이 이어졌습니다.",
            "context_text": "",
            "speech_date": "2026-09-11",
        }

    def test_period_only_hold_is_eligible_for_editorial_review(self):
        reason = collector.context_hold_editorial_triage_reason(self.row())
        self.assertIn("수치 기준기간만 미확인", reason)
        self.assertIn("불편", reason)

    def test_missing_issue_or_seoul_scope_fails_closed(self):
        self.assertEqual(
            collector.context_hold_editorial_triage_reason({
                **self.row(), "context_missing_fields": ["정확한 사안", "수치 기준기간"]
            }), ""
        )
        self.assertEqual(
            collector.context_hold_editorial_triage_reason({
                **self.row(), "seoul_scope": False
            }), ""
        )

    def test_generic_rhetoric_without_direct_harm_fails_closed(self):
        self.assertEqual(
            collector.context_hold_editorial_triage_reason({
                **self.row(), "text": "사업의 계획을 설명했습니다.",
                "context_text": "", "context_subject": "정책 사업",
            }), ""
        )

    def test_all_three_human_selected_cases_are_recovered_from_fixture(self):
        feed_path = HERE / "output" / "daily_feed_latest.json"
        selected_path = HERE / "editorial-decisions" / "selected_reporting_leads.json"
        if not feed_path.is_file():
            self.skipTest("daily feed fixture not present")
        feed = json.loads(feed_path.read_text(encoding="utf-8"))
        leads = json.loads(selected_path.read_text(encoding="utf-8"))["leads"]
        selected_rows = [
            row for row in feed.get("context_holds", [])
            if collector.context_hold_editorial_triage_reason(row)
        ]
        for lead in leads:
            self.assertTrue(
                any(
                    row.get("source_id") == lead["source_id"]
                    and row.get("url") == lead["source_url"]
                    and lead["anchor_text"] in (
                        row.get("text", "") + " " + row.get("context_text", "")
                    )
                    for row in selected_rows
                ),
                lead["id"],
            )

    def test_hold_remains_outside_question_and_article_gates(self):
        row = {
            **self.row(),
            "lane": "EDITORIAL_TRIAGE_HOLD",
            "triage_reason": "사안·서울 범위·영향 대상 확인, 기준기간 미확인",
            "question": "질문 생성 전 — 편집 검토",
            "grounding_status": "HOLD",
            "qualified": False,
        }
        rendered = injector.render({"editorial_triage": [row]}, {}, [])
        triage_section = rendered.split("## C-실험.", 1)[0]
        self.assertIn("자동 선별 · 문맥 HOLD 편집 검토", triage_section)
        self.assertIn("질문 PASS·S0·기사 후보로 자동 승격하지 않는다", triage_section)
        self.assertIn("아직 확인할 것: 수치 기준기간", triage_section)


if __name__ == "__main__":
    unittest.main()
