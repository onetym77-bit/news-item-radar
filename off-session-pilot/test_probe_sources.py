import unittest
from probe_sources import Page, inspect, same_host, sanitize
class ProbeTests(unittest.TestCase):
    def test_linked_entries_are_ordered_and_deduplicated(self):
        html = '<a href="/front/freeSuggest/view.do?sn=1">첫 제안</a>' * 2
        html += '<a href="/front/freeSuggest/view.do?sn=2">두 번째</a>'
        self.assertEqual([a["text"] for a in inspect(html,"P_LIST")["first_three_linked_entries"]],["첫 제안","두 번째"])
    def test_vote_and_empty_ids_cannot_become_proposals(self):
        html='<a href="/front/freeSuggest/view.do?sn=1#x">첫 제안</a><a href="/front/freeSuggest/view.do?sn=1">공감수 193</a><a href="/front/freeSuggest/view.do?sn=">처리상태 공감 투표중</a><a href="/front/freeSuggest/view.do?sn=2">두 번째</a>'
        self.assertEqual([a["text"] for a in inspect(html,"P_LIST")["first_three_linked_entries"]],["첫 제안","두 번째"])
    def test_related_proposals_on_detail_are_not_current_listing(self):
        html='<a href="/front/freeSuggest/view.do?sn=3">과거 관련 제안</a>'
        self.assertEqual(inspect(html,"P3")["first_three_linked_entries"],[])
    def test_script_cannot_supply_source_text(self):
        r=inspect('<title>통계</title><script>교통 999건</script><p>교통 123건</p>')
        self.assertEqual(r["stat_values"]["교통"],123)
    def test_accessible_chart_values_are_read(self):
        self.assertEqual(inspect('<img alt="자치구 221,943건">')["stat_values"]["자치구"],221943)
    def test_no_full_record_success_inferred_from_title(self):
        self.assertEqual(inspect('<title>시민제안</title>')["full_record_parse"],"NOT_IMPLEMENTED")
    def test_only_same_official_https_redirects_allowed(self):
        self.assertTrue(same_host("https://example.gov/b","https://example.gov/a"))
        for u in ("http://example.gov/b","https://other.gov/b","https://user:pass@example.gov/b"):
            self.assertFalse(same_host(u,"https://example.gov/a"))
    def test_contact_values_redacted(self):
        self.assertEqual(sanitize("a@example.com 010-1234-5678"),"[EMAIL] [PHONE]")
    def test_common_contact_formats_redacted(self):
        for value in ("01012345678", "010.1234.5678", "+82-10-1234-5678", "02-123-4567"):
            self.assertEqual(sanitize(value),"[PHONE]")
    def test_korean_contact_prefixes_redacted(self):
        self.assertEqual(sanitize("연락처01012345678 문의010-1234-5678"),"연락처[PHONE] 문의[PHONE]")
    def test_session_tokens_redacted(self):
        self.assertEqual(sanitize(";jsessionid=abc-12; DMCSESSION=token_34"),
                         ";jsessionid=[REDACTED]; DMCSESSION=[REDACTED]")
    def test_title_redacted_and_bounded(self):
        result=inspect("<title>01012345678 "+("가"*400)+"</title>")
        self.assertTrue(result["title"].startswith("[PHONE]"))
        self.assertLessEqual(len(result["title"]),300)
    def test_contacts_redacted_before_excerpt_boundary(self):
        result=inspect("<p>다자녀 "+("가"*440)+" 01012345678 abc@example.com</p>")
        text=result["diagnostic_excerpts"][0]["text"]
        self.assertNotIn("010",text)
        self.assertNotIn("abc@",text)
    def test_markup_does_not_count_as_a_new_question(self):
        self.assertEqual(inspect("<p>민원</p>")["article_gate"],"NOT_EVALUATED")
if __name__=="__main__":
    unittest.main()
