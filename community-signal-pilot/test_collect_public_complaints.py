import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("collect_public_complaints.py")
SPEC = importlib.util.spec_from_file_location("public_complaints", MODULE_PATH)
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


LIST_HTML = """
<html><body><table>
<tr><th>번호</th><th>분야</th><th>제목</th><th>신청일시</th><th>공개일시</th></tr>
<tr>
<td>146</td><td>S002001</td>
<td><a href="/exp/pub/complaint_pub_vie.do?rceptNo=978CB82577BBD432E8C607181A807D33">도로 시설 점검 요청</a></td>
<td>2026-07-31</td><td>2026-08-19</td><td>1,489</td>
</tr>
<tr>
<td>145</td><td>S002000</td>
<td><a href="#" onclick="fnView('B8A06A73CB0F8CECBCE6D7872D3B7C16')">장애인 이동 서비스 문의</a></td>
<td>2026.07.30</td><td>2026.08.19</td><td>791</td>
</tr>
</table></body></html>
"""

DETAIL_HTML = """
<html><body>
<h1>도로 시설 점검 요청</h1>
<div>민원 내용: 도로 단차와 파손으로 안전이 위험하고 반복해서 불편합니다.
연락처 02-1234-5678, 주소 세종대로 110.</div>
<div>답변 내용: 현재 특별안전점검을 실시 중이며 필요한 보수와 조치를 검토하겠습니다.</div>
<div>자동 로그아웃 안내</div>
</body></html>
"""


class PublicComplaintTests(unittest.TestCase):
    def test_parse_list_supports_direct_and_script_links(self):
        rows = module.parse_list(LIST_HTML, 20)
        self.assertEqual(2, len(rows))
        self.assertEqual("도로 시설 점검 요청", rows[0]["title"])
        self.assertEqual("2026-07-31", rows[0]["applied_date"])
        self.assertEqual("2026-08-19", rows[0]["published_date"])
        self.assertEqual("S002001", rows[0]["category_code"])
        self.assertIn("rceptNo=978CB82577BBD432E8C607181A807D33", rows[0]["source_url"])
        self.assertNotIn("978CB82577BBD432E8C607181A807D33", rows[0]["case_id"])

    def test_sanitize_removes_direct_identifiers(self):
        value = module.sanitize("전화 02-1234-5678 이메일 a@b.com 세종대로 110 900101-1234567")
        self.assertNotIn("02-1234-5678", value)
        self.assertNotIn("a@b.com", value)
        self.assertNotIn("세종대로 110", value)
        self.assertNotIn("900101-1234567", value)

    def test_derive_signals_keeps_claims_unverified(self):
        signals = module.derive_signals(
            "도로 단차와 파손으로 안전이 위험합니다.",
            "점검 후 보수 조치를 검토합니다.",
            "EXPLICIT_QUESTION_AND_ANSWER",
        )
        self.assertEqual("SAFETY_OR_MAINTENANCE", signals["signal_type"])
        self.assertEqual("SHADOW_REVIEW", signals["review_status"])
        self.assertEqual("UNVERIFIED_CITIZEN_STATEMENT", signals["claim_status"])
        self.assertFalse(signals["article_candidate"])
        self.assertEqual("NOT_GENERATED_AT_L2", signals["editorial_question"])

    def test_answer_only_page_cannot_create_citizen_signal(self):
        sections = module.split_explicit_sections(
            "장애인콜택시 이용관련 문의 답변 내용 "
            "운행시간이 제한되어 대기와 이용 불편이 있을 수 있습니다."
        )
        signals = module.derive_signals(
            sections["citizen_text"],
            sections["official_text"],
            sections["status"],
        )
        self.assertEqual("ANSWER_ONLY", sections["status"])
        self.assertEqual([], signals["citizen_problem_markers"])
        self.assertEqual("CONTEXT_UNRESOLVED", signals["review_status"])
        self.assertFalse(signals["citizen_section_available"])

    def test_observe_persists_only_derived_markers(self):
        def fetcher(url):
            if url == module.LIST_URL:
                return LIST_HTML, "a" * 64
            return DETAIL_HTML, "b" * 64

        result = module.observe(fetcher=fetcher, scan_limit=2, detail_limit=1)
        self.assertEqual(1, result["diagnostics"]["detail_success_count"])
        serialized = str(result)
        self.assertNotIn("02-1234-5678", serialized)
        self.assertNotIn("세종대로 110", serialized)
        self.assertNotIn("민원 내용", serialized)
        self.assertFalse(result["policy"]["questions_generated"])
        self.assertFalse(result["policy"]["automatic_promotion"])
        self.assertEqual("EXPLICIT_QUESTION_AND_ANSWER", result["records"][0]["section_status"])
        self.assertTrue(result["records"][0]["citizen_section_available"])

    def test_rejects_empty_list(self):
        with self.assertRaises(ValueError):
            module.parse_list("<html><body>없음</body></html>", 20)


if __name__ == "__main__":
    unittest.main()
