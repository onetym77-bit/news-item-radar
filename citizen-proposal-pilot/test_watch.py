import unittest

from watch import (
    LIST_URL, advance_history, classify_text, context_candidates, evidence_anchor,
    observe, parse_list, processed_proposal_ids, redact_anchor,
    relevant_detail_text, render, sanitize, title_position, validate_history,
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

    def test_seen_ids_are_skipped_before_detail_fetch(self):
        history = {
            "schema": 1,
            "processed": [{
                "proposal_id": "101",
                "first_processed_at_kst": "2026-09-28T13:26:54+09:00",
                "detail_sha256": None,
            }],
        }
        fetched = []
        def fake_fetch(url):
            fetched.append(url)
            if url == LIST_URL:
                return listing(), "list-hash"
            if "sn=101" in url:
                self.fail("processed proposal detail must not be fetched again")
            if "sn=102" in url:
                return "<p>양성화 소문 문의 시행한다는 소문을 들었습니다</p>", "b" * 64
            return "<p>새 장비 설치 제안 새 장비를 설치해주세요</p>", "c" * 64
        result = observe(fake_fetch, limit=3, history=history)
        self.assertEqual([row["proposal_id"] for row in result["records"]], ["102", "103"])
        self.assertEqual(result["listed_records"], 3)
        self.assertEqual(result["new_records"], 2)
        self.assertEqual(result["already_processed_records"], 1)
        self.assertFalse(any("sn=101" in url for url in fetched))

    def test_wider_scan_keeps_detail_fetch_bounded(self):
        fetched = []

        def fake_fetch(url):
            fetched.append(url)
            if url == LIST_URL:
                return listing(), "list-hash"
            if "sn=101" in url:
                return "<p>방문 발급의 불편 저는 방문이 불편했습니다</p>", "a" * 64
            self.fail("deferred proposal detail must not be fetched in this run")

        result = observe(fake_fetch, limit=3, process_limit=1)
        self.assertEqual([row["proposal_id"] for row in result["records"]], ["101"])
        self.assertEqual(result["listed_records"], 3)
        self.assertEqual(result["new_candidates_seen"], 3)
        self.assertEqual(result["new_records"], 1)
        self.assertEqual(result["deferred_new_records"], 2)
        self.assertEqual(result["process_limit"], 1)
        self.assertEqual(len(fetched), 2)

    def test_history_adds_only_id_digest_and_timestamp(self):
        history = {
            "schema": 1,
            "processed": [{
                "proposal_id": "101",
                "first_processed_at_kst": "2026-09-28T13:26:54+09:00",
                "detail_sha256": None,
            }],
        }
        updated = advance_history(
            history,
            [{"proposal_id": "102", "detail_sha256": "a" * 64,
              "title": "저장하면 안 되는 제목", "source_url": "https://example.test"}],
            "2026-09-28T14:00:00+09:00",
        )
        self.assertEqual(processed_proposal_ids(updated), {"101", "102"})
        row = next(item for item in updated["processed"] if item["proposal_id"] == "102")
        self.assertEqual(
            set(row),
            {"proposal_id", "first_processed_at_kst", "detail_sha256"},
        )
        self.assertNotIn("저장하면 안 되는 제목", str(updated))

    def test_invalid_history_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_history({
                "schema": 1,
                "processed": [
                    {"proposal_id": "101", "first_processed_at_kst": "x", "detail_sha256": None},
                    {"proposal_id": "101", "first_processed_at_kst": "y", "detail_sha256": None},
                ],
            })

    def test_experience_statement_is_still_unverified(self):
        card = classify_text("저는 회원증을 신청했지만 방문 때문에 시간이 부담됐습니다")
        self.assertEqual(card["statement_type"], "SELF_REPORTED_EXPERIENCE")
        self.assertEqual(card["claim_status"], "UNVERIFIED")
        self.assertEqual(card["article_gate"], "NOT_EVALUATED")

    def test_far_apart_first_person_and_friction_is_not_direct_experience(self):
        text = (
            "제가 서울의 전통 축제를 제안합니다. "
            + "전통문화 프로그램과 공연 구성을 설명합니다. " * 12
            + "행사장 이동 동선을 개선하면 좋겠습니다."
        )
        card = classify_text(text)
        self.assertEqual(card["statement_type"], "POLICY_IDEA")
        anchor = evidence_anchor(text, "SELF_REPORTED_EXPERIENCE", card["matched_basis"])
        self.assertIsNone(anchor["excerpt"])

    def test_hearsay_takes_priority_over_first_person(self):
        card = classify_text("제가 사무실에서 시행한다는 소문을 들었습니다. 불편합니다")
        self.assertEqual(card["statement_type"], "HEARSAY")

    def test_policy_idea_without_reported_event(self):
        self.assertEqual(classify_text("새 장비를 설치해주세요")["statement_type"],
                         "POLICY_IDEA")

    def test_direct_route_word_is_not_first_person_experience(self):
        card = classify_text("반포대로에서 김포공항으로 직접 진입하도록 신호 설치를 제안합니다")
        self.assertEqual(card["statement_type"], "POLICY_IDEA")

    def test_truncated_title_matches_only_stable_tokens(self):
        text = "[규제철폐제안] 모아타운 가로주택정비사업 빌라 한 동 과반"
        self.assertGreaterEqual(title_position(text, "[규제철폐제안] 모아타운 가로주택정비사업 「빌..."), 0)
        self.assertEqual(title_position(text, "[규제철폐제안] 다른 사업"), -1)

    def test_detail_must_match_own_title(self):
        self.assertIsNone(relevant_detail_text("<p>다른 제안만 있습니다</p>", "방문 발급"))
        text = relevant_detail_text(
            "<p>방문 발급</p><p>저는 신청했습니다.</p><p>관련 제안</p><p>소문</p>",
            "방문 발급",
        )
        self.assertNotIn("소문", text)

    def test_public_output_stores_only_bounded_redacted_anchor(self):
        def fake_fetch(url):
            if url == LIST_URL:
                return listing(), "list-hash"
            if "sn=101" in url:
                body = "방문 발급의 불편 저는 신청했지만 방문이 불편했습니다. 01012345678 "
                return f"<p>{body}{'전체본문비저장표식 ' * 80}</p>", "a"
            if "sn=102" in url:
                return "<p>양성화 소문 문의 시행한다는 소문을 들었습니다</p>", "b"
            return "<p>새 장비 설치 제안 새 장비를 설치해주세요</p>", "c"
        result = observe(fake_fetch, limit=3)
        output = render(result)
        first = result["records"][0]
        self.assertEqual(len(result["records"]), 3)
        self.assertNotIn("01012345678", str(result))
        self.assertNotRegex(first["evidence_anchor"]["excerpt"], r"\[[A-Z]*$")
        self.assertLessEqual(len(first["evidence_anchor"]["excerpt"]), 240)
        self.assertNotIn("detail_text", first.keys())
        self.assertEqual(first["problem_evidence_status"], "NOT_ESTABLISHED")
        self.assertEqual(result["article_gate"], "NOT_EVALUATED")

    def test_policy_idea_has_no_quote_anchor(self):
        basis = classify_text("설치해주세요")
        anchor = evidence_anchor("설치해주세요", basis["statement_type"], basis["matched_basis"])
        self.assertIsNone(anchor["excerpt"])

    def test_exact_address_and_identity_are_redacted(self):
        value = redact_anchor("제 이름은 홍길동이고 세종대로 110 101동 202호입니다")
        self.assertNotIn("홍길동", value)
        self.assertNotIn("110", value)
        self.assertNotIn("202", value)

    def test_context_terms_are_candidates_not_verified_facts(self):
        context = context_candidates("잠수교 주말 통행", "최근 주말마다 불편했습니다")
        self.assertIn("잠수교", context["place_terms_from_title"])
        self.assertIn("주말", context["time_terms_from_body"])
        self.assertEqual(context["status"], "UNVERIFIED_CONTEXT_CANDIDATES")
        self.assertEqual(context_candidates("역번호 증감", "")["place_terms_from_title"], [])
        self.assertEqual(context_candidates("자전거 대여소에 쓰레기통", "")["place_terms_from_title"], ["대여소"])

    def test_contact_masking(self):
        self.assertEqual(sanitize("a@example.com 01012345678"),
                         "[EMAIL] [PHONE]")

if __name__ == "__main__":
    unittest.main()
