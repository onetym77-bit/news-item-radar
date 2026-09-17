import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from audit_l4_shadow import (
    MAX_DETAIL_RECORDS,
    discover_records,
    evaluate,
    initial_state,
    read_reviews,
    render_summary,
    select_unseen,
    validate_state,
)
from collect_l1_batch import record


NOW = datetime(2026, 9, 16, 10, 45, tzinfo=ZoneInfo("Asia/Seoul"))
SOURCE = {
    "source_id": "seoul_audit_results",
    "official_url": "https://news.seoul.go.kr/gov/archives/category/inspection-news_c1/inspection-maintask_c1/admin_story_inspection-n1",
}


def card(record_id: str, ready: bool = True) -> dict:
    return {
        "source_record_id": record_id,
        "title": f"서울시 감사 결과 {record_id}",
        "detail_url": f"https://news.seoul.go.kr/gov/archives/{record_id}",
        "published_at": "2026-09-01",
        "question_status": "READY_FOR_HUMAN_REVIEW" if ready else "HOLD",
        "raw_report_text_persisted": False,
        "verification_question": "이 지적은 현장 운영을 바꿨나?" if ready else None,
        "competing_hypotheses": ["구조적 반복", "단발 오류"] if ready else [],
        "discriminating_test": "조치 전후 기록 대조" if ready else None,
        "discard_condition": "변화가 확인되지 않으면 폐기" if ready else None,
    }


def state_with_records(count: int = 12, days: int = 7) -> dict:
    state = initial_state(NOW)
    for index in range(count):
        record_id = str(580001 + index)
        state["records"].append({
            "source_record_id": record_id,
            "first_seen_kst": "2026-09-16",
            "cohort": "HISTORICAL_BACKFILL",
            "card": card(record_id),
            "challenge_flags": [],
        })
    for index in range(days):
        state["runs"].append({
            "run_date_kst": (date(2026, 9, 16) + timedelta(days=index)).isoformat(),
            "run_id": str(index),
            "listing_status": "SUCCESS",
            "listing_diagnostics": {},
            "selected_ids": [],
            "diagnostics": {"detail_requested": 3, "pdf_extracted": 3},
        })
    return state


def top_scores() -> dict:
    return {
        "verdict": "START_REPORTING",
        "document_value": "VALUABLE",
        "angle_selection": "RIGHT_ANGLE",
        "scores": {
            "grounding": 2, "scope": 2, "citizen_impact": 2,
            "specificity": 2, "competing_hypotheses": 2, "testability": 2,
        },
        "critical_error": "NONE",
    }


class AuditL4ShadowTests(unittest.TestCase):
    def test_unseen_selection_prefers_recent_then_backfill(self):
        rows = [
            record("1", "감사 결과 1", "https://news.seoul.go.kr/gov/archives/1", "2026-04-10", "VERIFIED", NOW.isoformat()),
            record("2", "감사 결과 2", "https://news.seoul.go.kr/gov/archives/2", "2026-09-15", "VERIFIED", NOW.isoformat()),
            record("3", "감사 결과 3", "https://news.seoul.go.kr/gov/archives/3", "2026-09-14", "VERIFIED", NOW.isoformat()),
        ]
        chosen = select_unseen(rows, {"3"}, NOW.date())
        self.assertEqual([row["source_record_id"] for row in chosen], ["2", "1"])
        self.assertLessEqual(len(chosen), MAX_DETAIL_RECORDS)

    def test_failed_first_page_is_partial_not_zero_if_second_succeeds(self):
        html = '<a href="/gov/archives/580883">서울시 감사 결과 공개문</a> 등록일 : 2026-09-15'
        def fetcher(url):
            if "/page/2" not in url:
                return "FAILED", None, {"error_code": "TIMEOUT"}
            return "SUCCESS", html, {"error_code": None}
        records, diagnostics = discover_records(SOURCE, NOW.isoformat(), NOW.date(), fetcher)
        self.assertEqual(len(records), 1)
        self.assertEqual(diagnostics["listing_pages_successful"], 1)
        self.assertEqual(diagnostics["listing_errors"], ["PAGE_1_TIMEOUT"])

    def test_total_listing_failure_is_error_not_no_items(self):
        def fetcher(_url):
            return "FAILED", None, {"error_code": "NETWORK_ERROR"}
        with self.assertRaisesRegex(RuntimeError, "all official audit listing pages failed"):
            discover_records(SOURCE, NOW.isoformat(), NOW.date(), fetcher)

    def test_seven_days_and_twelve_documents_do_not_override_human_review(self):
        state = state_with_records()
        result = evaluate(state, {})
        self.assertEqual(result["outcome"], "AWAITING_HUMAN_REVIEW")
        self.assertFalse(result["automatic_promotion"])

    def test_complete_human_reviews_only_make_editorial_decision_eligible(self):
        state = state_with_records()
        reviews = {item["source_record_id"]: top_scores() for item in state["records"]}
        result = evaluate(state, reviews)
        self.assertEqual(result["outcome"], "ELIGIBLE_FOR_EDITORIAL_L4_DECISION")
        self.assertFalse(result["automatic_promotion"])

    def test_critical_error_blocks_quality_gate(self):
        state = state_with_records()
        reviews = {item["source_record_id"]: top_scores() for item in state["records"]}
        reviews["580001"]["critical_error"] = "SCOPE_AS_FACT"
        self.assertEqual(evaluate(state, reviews)["outcome"], "QUALITY_GATES_NOT_MET")

    def test_repeated_missed_stronger_findings_block_quality_gate(self):
        state = state_with_records()
        reviews = {item["source_record_id"]: top_scores() for item in state["records"]}
        reviews["580001"]["angle_selection"] = "MISSED_STRONGER_FINDING"
        reviews["580002"]["angle_selection"] = "MISSED_STRONGER_FINDING"
        result = evaluate(state, reviews)
        self.assertEqual(result["metrics"]["missed_stronger_findings"], 2)
        self.assertLess(result["metrics"]["angle_selection_accuracy_pct"], 90)
        self.assertEqual(result["outcome"], "QUALITY_GATES_NOT_MET")

    def test_summary_shows_recent_questions_without_detailed_evidence(self):
        state = state_with_records(3, 2)
        state["runs"][-1]["selected_ids"] = ["580003"]
        state["records"][2]["card"]["verification_question"] = (
            "농업기술센터 감사 감사에서 이 지적은 현장 운영을 바꿨나? "
            "근거 자료를 길게 나열한다."
        )
        state["records"][2]["card"]["discriminating_test"] = "상세 검증 절차 비공개"
        state["records"][2]["challenge_flags"] = ["HUMAN_CHECK_ACTUAL_CITIZEN_EFFECT"]
        reviews = {"580001": top_scores()}
        result = evaluate(state, reviews)

        summary = render_summary(state, result, reviews)

        self.assertIn("이번 실행: 새 문서 1건 · 질문 초안 1건", summary)
        self.assertIn(
            "핵심 질문: 농업기술센터 감사에서 이 지적은 현장 운영을 바꿨나?",
            summary,
        )
        self.assertNotIn("감사 감사에서", summary)
        self.assertIn("이전 문서의 사람 판정", summary)
        self.assertIn("서울시 감사 결과 580001", summary)
        self.assertNotIn("서울시 감사 결과 580002", summary)
        self.assertNotIn("근거 자료를 길게 나열한다", summary)
        self.assertNotIn("상세 검증 절차 비공개", summary)
        self.assertNotIn("HUMAN_CHECK_ACTUAL_CITIZEN_EFFECT", summary)
        self.assertNotIn("PDF 추출 성공률", summary)

    def test_summary_does_not_confuse_held_document_with_candidate(self):
        state = state_with_records(1, 1)
        state["records"][0]["card"] = card("580001", ready=False)
        state["runs"][0]["selected_ids"] = ["580001"]
        result = evaluate(state, {})

        summary = render_summary(state, result, {})

        self.assertIn("질문 초안 0건 · 보류 1건", summary)
        self.assertIn("이번에 보류한 문서", summary)
        self.assertIn("감사 지적 목록 확인 실패", summary)
        self.assertNotIn("핵심 질문:", summary)
        state["records"][0]["card"]["documented_issue_in_table"] = True
        summary = render_summary(state, result, {})
        self.assertIn("지적은 확인했지만 기획 질문 기준 미달", summary)

        reviews = {
            "580001": {
                "verdict": "MISSED_VALUE",
                "document_value": "VALUABLE",
                "angle_selection": "MISSED_STRONGER_FINDING",
                "scores": {},
                "critical_error": "NONE",
            }
        }
        summary = render_summary(state, result, reviews)
        self.assertIn("가치 있는 지적 재탐색 · 더 강한 지적 재선택 필요", summary)
        self.assertNotIn("지적은 확인했지만 기획 질문 기준 미달", summary)

    def test_state_rejects_raw_report_and_external_url(self):
        state = state_with_records(1, 1)
        state["records"][0]["card"]["report_text"] = "raw audit text"
        self.assertTrue(validate_state(state))
        del state["records"][0]["card"]["report_text"]
        state["records"][0]["card"]["detail_url"] = "https://example.com/audit"
        self.assertTrue(validate_state(state))

    def test_review_file_requires_human_scores_and_holds_have_no_score(self):
        state = state_with_records(1, 1)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reviews.csv"
            path.write_text(
                "source_record_id,verdict,document_value,angle_selection,grounding,scope,citizen_impact,specificity,competing_hypotheses,testability,critical_error\n"
                "580001,START_REPORTING,VALUABLE,RIGHT_ANGLE,2,2,2,2,2,2,NONE\n",
                encoding="utf-8",
            )
            reviews = read_reviews(path, state["records"])
            self.assertEqual(reviews["580001"]["scores"]["grounding"], 2)
            path.write_text(
                "source_record_id,verdict,document_value,angle_selection,grounding,scope,citizen_impact,specificity,competing_hypotheses,testability,critical_error\n"
                "580001,START_REPORTING,VALUABLE,RIGHT_ANGLE,2,,,,,,NONE\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "missing or invalid"):
                read_reviews(path, state["records"])


if __name__ == "__main__":
    unittest.main()
