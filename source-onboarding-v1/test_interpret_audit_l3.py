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
    select_primary_finding,
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

    def test_scope_words_alone_cannot_promote_rights_question(self):
        scope_only = """목차
Ⅱ. 감사결과 처분요구 내역 및 조치현황
\f
Ⅱ. 감사결과 처분요구 내역 및 조치현황
아동 보호·인권·안전·학대 예방을 감사 중점으로 함
처분요구사항 일람표: 3건 [주의 3]
1 인사 절차 운영 부적정 주의
"""
        card = build_card(
            self.listing_record,
            "https://news.seoul.go.kr/gov/files/2026/09/report.pdf",
            diagnostics(scope_only),
            scope_only,
        )
        self.assertNotEqual(card["evidence_anchor"], "PROBLEM_SIGNAL")
        self.assertEqual(card["question_status"], "HOLD")

    def test_stronger_finding_outranks_first_rights_finding(self):
        mixed = """목차
Ⅱ. 감사 지적사항 목록
\f
감사 개요 및 범위
\f
Ⅱ. 감사 지적사항 목록
감사결과 총괄 조치(안)
감사결과 일람표
1 아동 인권침해 진정함 관리 미흡 통보
2 입소아동 외출·외박에 대한 보호 및 공적 관리체계 강화 필요 주의 통보
3 고위험군 아동 의료·심리치료 체계 개선 필요 통보
4 공사 계약 부적정 주의
\f
처분요구서
\f
고위험군 아동 의료·심리치료 체계 개선 필요
지정 의료기관의 이용과 입원이 지연되고 지속 사례관리가 필요함
"""
        card = build_card(
            self.listing_record,
            "https://news.seoul.go.kr/gov/files/2026/09/report.pdf",
            diagnostics(mixed),
            mixed,
        )
        self.assertEqual(card["question_status"], "READY_FOR_HUMAN_REVIEW")
        self.assertIn("고위험군 아동 의료·심리치료", card["selected_finding_title"])
        self.assertIn("즉시 입원", card["verification_question"])
        self.assertIn("지정병원", card["discriminating_test"])

    def test_finding_selection_is_not_first_row_bias(self):
        issue_text = """아동 인권침해 진정함 관리 미흡
입소아동 외출·외박에 대한 보호 및 공적 관리체계 강화 필요
고위험군 아동 의료·심리치료 체계 개선 필요"""
        selected, score, count = select_primary_finding(issue_text)
        self.assertEqual(count, 3)
        self.assertGreater(score, 0)
        self.assertIn("고위험군", selected)

    def test_wrapped_agriculture_audit_selects_actual_school_check_gap(self):
        report = """목차
Ⅰ. 감사실시 개요
Ⅱ. 감사 지적사항 목록
\f
Ⅰ. 감사실시 개요
\f
Ⅱ. 감사 지적사항 목록
감사결과 일람표
연번 감사 분야 감   사   성   과 (대상기관) 부 과 금 액 조치(안)
1 시 설 물
안전 관리
농지·개발제한구역 내 시설물 관리 부적정 - 시정·통보
2 화재예방 강화를 위한 소방관리체계 확립 및 화기관리 철저 - 주의·통보
3 청년농업인 영농정착지원사업 대상자 선정 업무 소홀 - 주의·통보
4 유치원·학교 파견강사 성범죄 경력 확인 절차 개선 필요 - 통보
\f
Ⅲ. 감사결과 요약
"""
        listing = dict(self.listing_record)
        listing["title"] = "서울특별시 농업기술센터 기관운영 감사"
        card = build_card(
            listing,
            "https://news.seoul.go.kr/gov/files/2026/06/report.pdf",
            diagnostics(report),
            report,
        )
        self.assertEqual(card["question_status"], "READY_FOR_HUMAN_REVIEW")
        self.assertIn("성범죄 경력", card["selected_finding_title"])
        self.assertIn("누가 채용 전에 확인했나", card["verification_question"])
        self.assertNotIn("권리·안전 지적", card["verification_question"])
        self.assertNotIn("피해 아동", card["verification_question"])

    def test_design_audit_table_is_not_falsely_held(self):
        report = """목차
Ⅰ. 감사실시 개요
Ⅱ. 감사결과 처분요구 내역
\f
Ⅰ. 감사실시 개요
\f
Ⅱ. 감사결과 처분요구 내역
처분요구사항 일람표: 29건 [시정 1, 주의 12, 통보 16]
연번 지적내용 대상기관 처분종류 이행여부
1 DDP 루프탑 투어 동선 확장공사 등 부적정 서울디자인재단
주의(기관경고) 이행 완료
2 DDP 노출콘크리트 보수공사 부적정 서울디자인재단
주의 이행 완료
13 지각․조퇴․외출 및 유연근무 운영 개선 필요 서울디자인재단 통보 이행 중
\f
Ⅲ. 감사결과 처분요구서
"""
        listing = dict(self.listing_record)
        listing["title"] = "서울디자인재단 종합감사 결과"
        card = build_card(
            listing,
            "https://news.seoul.go.kr/gov/files/2026/06/report.pdf",
            diagnostics(report),
            report,
        )
        self.assertTrue(card["summary_table_confirmed"])
        self.assertTrue(card["documented_issue_in_table"])
        self.assertEqual(card["official_finding_count"], 29)
        self.assertIn("DDP 루프탑", card["selected_finding_title"])
        self.assertNotIn("유연근무", card["selected_finding_title"])
        self.assertNotEqual(
            card.get("hold_reason"),
            "감사 지적 일람표 또는 개별 지적을 확인하지 못함",
        )

    def test_fashion_hub_actual_table_header_is_not_falsely_held(self):
        # Mirrors the first four pages of the 108-page published audit.
        report = """(공개용)
서울패션허브 관리·운영 실태 특정감사 결과
\f
목차
Ⅰ. 감사개요
Ⅱ. 감사결과 처분요구 내역
\f
Ⅰ. 감사개요
4. 감사성과 총괄
\f
Ⅱ. 감사결과 처분요구 내역
□ 처분요구사항 일람표
ㅇ 총 24건(시정 1, 주의 16, 통보 7)
연번 감사분야 지적내용 처분종류
1 민간위탁금 정산 관련 부가가치세 상당액 미반납 시정
2 민간위탁금 예산편성 검토 의무 소홀 주의
3 예산 이월 승인절차 및 정산보고 관리 소홀 주의
6 수의계약 체결 부적정 주의
11 인플루언서 활용 사업 추진 관련 부적정 주의
12 의류제조기업 협력 플랫폼 구축 사업 부적정 주의
\f
Ⅲ. 감사결과 처분요구서
"""
        listing = dict(self.listing_record)
        listing["title"] = "서울패션허브 관리·운영 실태 특정감사 결과 공개문"
        card = build_card(
            listing,
            "https://news.seoul.go.kr/gov/files/2026/08/report.pdf",
            diagnostics(report),
            report,
        )
        self.assertTrue(card["summary_table_confirmed"])
        self.assertTrue(card["documented_issue_in_table"])
        self.assertEqual(card["official_finding_count"], 24)
        self.assertGreater(card["finding_candidate_count"], 1)
        self.assertNotEqual(
            card.get("hold_reason"),
            "감사 지적 일람표 또는 개별 지적을 확인하지 못함",
        )

    def test_sh_travel_audit_records_finding_even_when_question_held(self):
        report = """목차
Ⅰ. 감사실시 개요
Ⅱ. 감사결과 처분요구 내역
\f
Ⅰ. 감사실시 개요
\f
Ⅱ. 감사결과 처분요구 내역
처분요구사항 일람표: 1건 [시정 1]
연번 지적내용 대상기관 처분종류 이행여부
1 공무국외출장 여비 산정 및 심사 등 부적정 서울주택도시개발공사 시정 이행 중
\f
Ⅲ. 감사결과 처분요구서
"""
        listing = dict(self.listing_record)
        listing["title"] = "서울주택도시개발공사 특정감사 결과"
        card = build_card(
            listing,
            "https://news.seoul.go.kr/gov/files/2026/07/report.pdf",
            diagnostics(report),
            report,
        )
        self.assertTrue(card["summary_table_confirmed"])
        self.assertTrue(card["documented_issue_in_table"])
        self.assertIn("여비 산정", card["selected_finding_title"])
        self.assertNotEqual(
            card.get("hold_reason"),
            "감사 지적 일람표 또는 개별 지적을 확인하지 못함",
        )

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
