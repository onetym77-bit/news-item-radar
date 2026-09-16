import unittest

from watch import (
    LIST_URL, classify_text, observe, parse_list, relevant_detail_text,
    render, sanitize,
)

def listing():
    return (
        '<a href="/front/freeSuggest/view.do?sn=101">방문 발급의 불편</a>'
        '<span>2026-09-15</span><span>처리상태 공감 투표중</span>'
        '<a href="/front/freeSuggest/view.do?sn=101">공감수 999</a>'
        '<a href="/front/freeSuggest/view.do?sn=102">양성화 소문 문의</a>'
        '<span>2026-09-14</span>'
        '<a href="/front/freeSuggest/view.do?sn=103">새 장비 설치 제안</a>'
        '<span>2026-09-13</span>'
    )

class CitizenProposalWatchTests(unittest.TestCase):
    def test_list_unique_ids_and_item_dates(self):
        rows = parse_list(listing())
        self.assertEqual([r["proposal_id"] for r in rows], ["101", "102", "103"])
        self.assertEqual([r["posted_date"] for r in rows],
                         ["2026-09-15", "2026-09-14", "2026-09-13"])
        self.assertNotIn("999", str(rows))

    def test_no_proposals_is_access_failure_not_zero_findings(self):
        with self.assertRaisesRegex(ValueError, "no proposal"):
            parse_list("<p>시민제안 목록</p>")

    def test_experience_statement_is_still_unverified(self):
        card = classify_text("저는 회원증을 신청했지만 방문 때문에 시간이 부담됐습니다")
        self.assertEqual(card["statement_type"], "SELF_REPORTED_EXPERIENCE")
        self.assertEqual(card["claim_status"], "UNVERIFIED")
        self.assertEqual(card["article_gate"], "NOT_EVALUATED")

    def test_hearsay_takes_priority_over_first_person(self):
        card = classify_text("제가 사무실에서 시행한다는 소문을 들었습니다. 불편합니다")
        self.assertEqual(card["statement_type"], "HEARSAY")

    def test_policy_idea_without_reported_event(self):
        self.assertEqual(classify_text("새 장비를 설치해주세요")["statement_type"],
                         "POLICY_IDEA")

    def test_detail_must_match_own_title(self):
        self.assertIsNone(relevant_detail_text("<p>다른 제안만 있습니다</p>", "방문 발급"))
        text = relevant_detail_text(
            "<p>방문 발급</p><p>저는 신청했습니다.</p><p>관련 제안</p><p>소문</p>",
            "방문 발급",
        )
        self.assertNotIn("소문", text)

    def test_public_output_does_not_store_name_or_full_body(self):
        def fake_fetch(url):
            if url == LIST_URL:
                return listing(), "list-hash"
            if "sn=101" in url:
                return "<p>방문 발급의 불편 저는 신청했지만 방문이 불편했습니다. 01012345678</p>", "a"
            if "sn=102" in url:
                return "<p>양성화 소문 문의 시행한다는 소문을 들었습니다</p>", "b"
            return "<p>새 장비 설치 제안 새 장비를 설치해주세요</p>", "c"
        result = observe(fake_fetch, limit=3)
        output = render(result)
        self.assertEqual(len(result["records"]), 3)
        self.assertNotIn("01012345678", str(result))
        self.assertNotIn("신청했지만", str(result))
        self.assertNotIn("신청했지만", output)
        self.assertEqual(result["article_gate"], "NOT_EVALUATED")

    def test_contact_masking(self):
        self.assertEqual(sanitize("a@example.com 01012345678"),
                         "[EMAIL] [PHONE]")

if __name__ == "__main__":
    unittest.main()
