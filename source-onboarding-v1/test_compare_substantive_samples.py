import csv
import tempfile
import types
import unittest
from pathlib import Path

from compare_substantive_samples import (
    SAMPLE_SIZE,
    attach_reviews,
    audit_cards,
    citizen_body_text,
    citizen_cards,
    read_reviews,
    source_metrics,
    validate_payload,
    write_review_queue,
)


class SubstantiveComparisonTests(unittest.TestCase):
    def setUp(self):
        self.audit_source = {
            "source_id": "seoul_audit_results",
            "official_url": "https://news.seoul.go.kr/gov/archives/category/inspection",
        }
        self.citizen_source = {
            "source_id": "citizen_proposals",
            "official_url": "https://idea.seoul.go.kr/front/allSuggest/list.do",
        }
        self.module = types.SimpleNamespace(
            redact_anchor=lambda value: value.replace("010-1234-5678", "[PHONE]"),
            parse_list=lambda _html, limit: [
                {
                    "proposal_id": str(100 + i),
                    "title": f"제안 {i}",
                    "source_url": f"https://idea.seoul.go.kr/front/freeSuggest/view.do?sn={100 + i}",
                    "posted_date": "2026-09-17",
                }
                for i in range(5)
            ][:limit],
            relevant_detail_text=lambda _html, title: f"{title} 이용 불편을 겪었습니다 010-1234-5678",
            classify_text=lambda _text: {
                "statement_type": "SELF_REPORTED_EXPERIENCE",
                "matched_basis": {
                    "first_person_terms": [],
                    "friction_terms": ["불편"],
                    "hearsay_terms": [],
                    "idea_terms": [],
                },
            },
            evidence_anchor=lambda text, category, basis: {
                "excerpt": text, "status": "CLASSIFICATION_SUPPORT_ONLY",
            },
        )

    def test_audit_uses_real_pdf_finding_not_listing_title(self):
        def collector(_source, _at):
            return {
                "cards": [{
                    "source_record_id": "580883",
                    "title": "감사 결과 공개문",
                    "detail_url": "https://news.seoul.go.kr/gov/archives/580883",
                    "published_at": "2026-09-15",
                    "selected_finding_title": "복지시설 급여 지급 부적정",
                    "review_finding_titles": [
                        "복지시설 급여 지급 부적정",
                        "위기 아동 보호 공백 개선 필요",
                    ],
                    "documented_issue_in_table": True,
                }],
                "diagnostics": {"pdf_extracted": 1},
            }
        cards, diagnostics = audit_cards(
            self.audit_source, "2026-09-17T18:00:00+09:00",
            collector=collector, citizen_module=self.module,
        )
        self.assertEqual(cards[0]["body_status"], "READABLE_FINDING")
        self.assertEqual(cards[0]["review_excerpt"], "복지시설 급여 지급 부적정")
        self.assertEqual(
            cards[0]["review_finding_options"],
            ["복지시설 급여 지급 부적정", "위기 아동 보호 공백 개선 필요"],
        )
        self.assertEqual(cards[0]["evidence_status"], "OFFICIAL_DOCUMENTED_FINDING")
        self.assertEqual(diagnostics["pdf_extracted"], 1)

    def test_citizen_reads_only_three_and_redacts_excerpt(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return "<html>공식 화면</html>", "hash"

        cards, diagnostics = citizen_cards(
            self.citizen_source, "2026-09-17T18:00:00+09:00",
            module=self.module, fetcher=fetcher,
        )
        self.assertEqual(len(cards), SAMPLE_SIZE)
        self.assertEqual(len(calls), SAMPLE_SIZE + 1)
        self.assertEqual(diagnostics["detail_readable"], SAMPLE_SIZE)
        self.assertNotIn("010-1234-5678", str(cards))
        self.assertTrue(all(card["evidence_status"] == "UNVERIFIED_CLAIM" for card in cards))

    def test_citizen_body_excludes_page_controls_and_byline(self):
        page = (
            "이동 약자 제안 스크랩 공유 X에 공유 첨부파일 1.jpg "
            "네이버 박 * * 2026.09.16. 시민의견 : 0 지역분류 - "
            "정책분류 기타 지하철 좌석 이용 과정에서 이동 곤란성이 "
            "반영되지 않아 불편하다는 제안입니다."
        )
        body = citizen_body_text(page)
        self.assertIn("지하철 좌석 이용 과정", body)
        self.assertNotIn("스크랩 공유", body)
        self.assertNotIn("박 * *", body)
        self.assertIsNone(citizen_body_text("제안 스크랩 공유 작성자 정보만 있음"))

    def test_review_queue_roundtrip_with_extra_columns_and_blank_rows(self):
        cards, _ = citizen_cards(
            self.citizen_source, "2026-09-17T18:00:00+09:00",
            module=self.module, fetcher=lambda _url: ("<html></html>", "hash"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "queue.csv"
            write_review_queue(cards, path)
            self.assertEqual(read_reviews(path, cards), {})
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames)
                rows = list(reader)
            rows[0]["label"] = "VERIFY"
            rows[0]["reviewed_on"] = "2026-09-17"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            reviews = read_reviews(path, cards)
            self.assertEqual(reviews[("citizen_proposals", "100")]["label"], "VERIFY")

    def test_no_automatic_label_and_no_article_output(self):
        cards, _ = citizen_cards(
            self.citizen_source, "2026-09-17T18:00:00+09:00",
            module=self.module, fetcher=lambda _url: ("<html></html>", "hash"),
        )
        attach_reviews(cards, {})
        metrics = source_metrics(cards, "citizen_proposals")
        self.assertIsNone(metrics["useful_signal_rate"])
        self.assertEqual(metrics["editorial_result"], "HUMAN_REVIEW_REQUIRED")
        payload = {
            "cards": cards,
            "question_output": "NONE",
            "briefing_output": "NONE",
            "automatic_ledger_write": False,
        }
        self.assertEqual(validate_payload(payload), [])
        payload["cards"][0]["full_body"] = "private text"
        self.assertTrue(validate_payload(payload))


if __name__ == "__main__":
    unittest.main()
