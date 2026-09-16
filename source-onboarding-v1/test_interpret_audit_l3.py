import unittest

from collect_l1_batch import record
from interpret_audit_l3 import (
    MAX_DETAIL_RECORDS,
    build_card,
    collect_l3,
    extract_dispositions,
    extract_finding_count,
    find_pdf_attachment,
    join_report_pages,
    summary_window,
    validate_l3_output,
)
from thin_source_contract import FORBIDDEN_KEYS, load_registry, walk_keys


REPORT_TEXT = """목차
Ⅰ. 감사실시 개요
Ⅱ. 감사결과 처분요구 내역 및 조치현황
Ⅲ. 감사결과 처분요구서
\f
Ⅰ. 감사실시 개요
감사 배경과 목적
\f
Ⅱ. 감사결과 처분요구 내역 및 조치현황
처분요구사항 일람표: 14건 [시정 3, 주의 8, 통보 3]
연번 처분요구 제목 대상기관 처분유형
1 특정제품 선정심사위원회 운영 부적정 주의
2 제조·구매 설치 계약 부적정 시정 통보
3 기술진단 용역 계약 부적정 주의
4 변경계약을 통한 사실상의 수의계약 체결 주의
9 민원 처리 기한 미준수 주의
10 자금·여유금의 운용 개선 통보
\f
Ⅲ. 감사결과 처분요구서
이 뒤의 전체 보고서 문장은 저장하면 안 됩니다.
"""

LISTING_HTML = """
<html><body>
<h3><a href="/gov/archives/580883">서울물재생시설공단 기관운영 감사 결과 공개문</a></h3>
<p>등록일 : 2026-09-15</p>
</body></html>
"""

DETAIL_HTML = """
<html><body>
<h2>서울물재생시설공단 기관운영 감사 결과 공개문</h2>
<div>담당부서 공공감사담당관</div>
<div>문의 02-2133-1591</div>
<div>수정일 2026-09-15</div>
<p>감사개요</p>
<a href="/gov/files/2026/09/report.pdf">붙임 감사결과 공개문</a>
<div>추천하기0</div>
</body></html>
"""


def diagnostics(content: str = "") -> dict:
    return {
        "error_code": None,
        "http_status": 200,
        "content_sha256": "a" * 64,
        "extracted_text_sha256": "b" * 64,
        "response_bytes": len(content.encode("utf-8")),
    }


class AuditL3Tests(unittest.TestCase):
    def setUp(self):
        self.registry = load_registry()
        self.source = next(
            row for row in self.registry["sources"] if row["source_id"] == "seoul_audit_results"
        )
        self.observed_at = "2026-09-16T19:00:00+09:00"
        self.listing_record = record(
            "580883",
            "서울물재생시설공단 기관운영 감사 결과 공개문",
            "https://news.seoul.go.kr/gov/archives/580883",
            "2026-09-15",
            "VERIFIED",
            self.observed_at,
        )

    def test_pdf_page_join_uses_real_form_feed_boundary(self):
        joined = join_report_pages(["first page", "second page"])
        self.assertEqual(joined.split("\f"), ["first page", "second page"])
        self.assertNotIn("\\f", joined)

    def test_report_summary_extracts_count_and_dispositions(self):
        window, confirmed = summary_window(REPORT_TEXT)
        self.assertTrue(confirmed)
        self.assertEqual(extract_finding_count(window), 14)
        present, counts = extract_dispositions(window)
        self.assertIn("시정", present)
        self.assertIn("주의", present)
        self.assertEqual(counts["시정"], 3)
        self.assertEqual(counts["주의"], 8)
        self.assertEqual(counts["통보"], 3)


    def test_contents_only_does_not_create_a_question(self):
        toc_only = """목차
Ⅱ. 감사결과 처분요구 내역 및 조치현황
Ⅲ. 감사결과 처분요구서
\f
감사 배경과 목적만 있음
\f
감사 일정만 있음
"""
        card = build_card(
            self.listing_record,
            "https://news.seoul.go.kr/gov/files/2026/09/report.pdf",
            diagnostics(toc_only),
            toc_only,
        )
        self.assertEqual(card["question_status"], "HOLD")
        self.assertFalse(card["summary_table_confirmed"])

    def test_external_or_non_pdf_attachment_is_not_accepted(self):
        unsafe = DETAIL_HTML.replace(
            "/gov/files/2026/09/report.pdf",
            "https://example.com/report.pdf",
        )
        self.assertIsNone(find_pdf_attachment(unsafe, self.listing_record["detail_url"]))
        non_pdf = DETAIL_HTML.replace("report.pdf", "report.hwp")
        self.assertIsNone(find_pdf_attachment(non_pdf, self.listing_record["detail_url"]))

    def test_strong_summary_creates_verification_only_question(self):
        card = build_card(
            self.listing_record,
            "https://news.seoul.go.kr/gov/files/2026/09/report.pdf",
            diagnostics(REPORT_TEXT),
            REPORT_TEXT,
        )
        self.assertEqual(card["question_status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(card["evidence_anchor"], "PROBLEM_SIGNAL")
        self.assertEqual(card["official_finding_count"], 14)
        self.assertIn("계약·조달", card["verification_question"])
        self.assertEqual(len(card["competing_hypotheses"]), 2)
        self.assertNotIn("이 뒤의 전체 보고서 문장", str(card))

    def test_missing_findings_summary_is_held(self):
        card = build_card(
            self.listing_record,
            "https://news.seoul.go.kr/gov/files/2026/09/report.pdf",
            diagnostics("감사 목적과 일정만 있음"),
            "감사 목적과 일정만 있음",
        )
        self.assertEqual(card["question_status"], "HOLD")
        self.assertEqual(card["evidence_anchor"], "UNRESOLVED")
        self.assertIsNone(card["verification_question"])

    def test_collection_is_bounded_and_persists_no_raw_report(self):
        listing = "<html><body>" + "".join(
            f'<h3><a href="/gov/archives/{580880 + i}">기관 {i} 감사 결과 공개문</a></h3>'
            f'<p>등록일 : 2026-09-{15 - i:02d}</p>'
            for i in range(5)
        ) + "</body></html>"

        def html_fetcher(url):
            if "/archives/category/" in url:
                return "SUCCESS", listing, diagnostics(listing)
            page = DETAIL_HTML.replace(
                "서울물재생시설공단 기관운영 감사 결과 공개문",
                f"기관 {int(url.rsplit('/', 1)[-1]) - 580880} 감사 결과 공개문",
            )
            return "SUCCESS", page, diagnostics(page)

        payload = collect_l3(
            self.source,
            self.observed_at,
            html_fetcher=html_fetcher,
            pdf_fetcher=lambda _url: ("SUCCESS", b"%PDF-1.4 fixture", diagnostics()),
            pdf_extractor=lambda _data: ("SUCCESS", REPORT_TEXT, diagnostics(REPORT_TEXT)),
        )
        self.assertEqual(len(payload["cards"]), MAX_DETAIL_RECORDS)
        self.assertEqual(payload["diagnostics"]["raw_reports_persisted"], 0)
        serialized = str(payload)
        self.assertNotIn("02-2133-1591", serialized)
        self.assertNotIn("이 뒤의 전체 보고서 문장", serialized)
        self.assertFalse(FORBIDDEN_KEYS & set(walk_keys(payload)))

    def test_l3_output_validates_and_cannot_feed_briefing_or_ledger(self):
        payload = collect_l3(
            self.source,
            self.observed_at,
            html_fetcher=lambda url: (
                ("SUCCESS", LISTING_HTML, diagnostics(LISTING_HTML))
                if "/archives/category/" in url
                else ("SUCCESS", DETAIL_HTML, diagnostics(DETAIL_HTML))
            ),
            pdf_fetcher=lambda _url: ("SUCCESS", b"%PDF-1.4 fixture", diagnostics()),
            pdf_extractor=lambda _data: ("SUCCESS", REPORT_TEXT, diagnostics(REPORT_TEXT)),
        )
        self.assertEqual(validate_l3_output(payload, self.registry), [])
        self.assertEqual(payload["briefing_output"], "NONE")
        self.assertFalse(payload["automatic_ledger_write"])
        self.assertEqual(payload["question_output"], "VERIFICATION_ONLY")


if __name__ == "__main__":
    unittest.main()
