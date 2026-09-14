import unittest
from collect_pilot import Page, select_rows, transcript, day, review_windows, identity_conflict, discover_list, window_change, canonical
SRC={"hosts":["example.gov"]}
class PilotRegression(unittest.TestCase):
    def test_selection_keeps_unresolved_newest_row(self):
        html='<table><tr><td>1 제10대 제300회 본회의 2026.09.07</td><td><a href="#">본문</a></td></tr><tr><td>2 제10대 제299회 본회의 2026.08.10</td><td><a href="/record/main?uid=2">본문</a></td></tr></table>'
        rows,total=select_rows(Page(html),"https://example.gov/late",SRC,1)
        self.assertEqual(total,2)
        self.assertEqual(rows[0]["meeting_date"],"2026-09-07")
        self.assertEqual(rows[0]["url"],"")
    def test_http_ok_error_is_not_transcript(self):
        body,parts=transcript(Page('<html>개의 행을 찾을 수 없습니다</html>'))
        self.assertFalse(body)
    def test_loading_notice_does_not_hide_real_speech(self):
        body,parts=transcript(Page('<p>회의록을 불러오는 중입니다</p><p>○위원 김가나 '+('교통비 지원의 실제 효과를 확인하고자 합니다. '*15)+'</p><p>○과장 이다라 자료를 검토하겠습니다.</p>'))
        self.assertTrue(body)
        self.assertEqual(len(parts),2)
    def test_no_new_number_required_for_question_seed(self):
        parts=['위원 김가나 '+('돌봄 시설 접근이 불편한 주민의 이용 시간을 확인해야 합니다. '*8)]
        self.assertEqual(len(review_windows(parts)),1)
    def test_seongdong_data_uid(self):
        src={"hosts":["example.gov"],"uid_path":"/record/main"}
        rows,_=select_rows(Page('<table><tr><td>제293회 본회의 2026.08.28</td><td><a href="#" data-uid="8712">본문</a></td></tr></table>'),"https://example.gov/late",src)
        self.assertEqual(rows[0]["url"],"https://example.gov/record/main?uid=8712")
    def test_missing_date_keeps_newest_slot(self):
        html='<table><tr><td>1 제300회 본회의 날짜미확인</td><td><a href="/record/main?uid=3">본문</a></td></tr><tr><td>2 제299회 본회의 2026.08.10</td><td><a href="/record/main?uid=2">본문</a></td></tr></table>'
        rows,_=select_rows(Page(html),"https://example.gov/late",SRC,1)
        self.assertEqual(rows[0]["url"],"https://example.gov/record/main?uid=3")
        self.assertEqual(rows[0]["meeting_date"],"")
    def test_extraordinary_session_is_not_provisional_text(self):
        html='<table><tr><td>제300회 임시회 본회의 2026.09.07</td><td><a href="/record/main?uid=3">본문</a></td></tr></table>'
        rows,_=select_rows(Page(html),"https://example.gov/late",SRC)
        self.assertFalse(rows[0]["provisional"])
    def test_long_speech_keeps_the_actual_signal(self):
        parts=['위원 김가나 '+('존경하는 주민 여러분께 먼저 인사를 드립니다. '*45)+'돌봄 시설이 부족하고 이용 대기 시간은 증가했습니다. 구민 부담이 커집니다.']
        result=review_windows(parts)
        self.assertIn("대기 시간",result[0]["passage"])
        self.assertGreater(result[0]["character_offset"],650)
    def test_related_minutes_are_not_transcript_frames(self):
        page=Page('<a href="/record/main?uid=2">관련 회의록</a><iframe src="/record/main?uid=1"></iframe>')
        self.assertEqual(page.frames,["/record/main?uid=1"])
    def test_chair_procedural_time_is_not_a_service_signal(self):
        parts=['위원장 남해석 보건소장 수고하셨습니다. 다음은 질의답변 시간을 갖도록 하겠습니다. 질의답변은 원활한 회의진행을 위하여 5분 이내로 해 주시고, 질의시간이 부족할 경우에는 충분히 보충 질의시간을 드리도록 하겠습니다. 질의하실 위원은 질의하여 주시기 바랍니다.']
        self.assertEqual(review_windows(parts),[])
    def test_attendance_and_profiles_cannot_become_speeches(self):
        html='<p>○5분자유발언 메뉴</p><p>COPYRIGHT 2026</p><p>○위원 김가나 '+('교통 지원 현황을 확인하겠습니다. '*15)+'</p><p>○과장 이다라 확인 후 답변하겠습니다.</p><p>○출석관계공무원 돌봄시설 국장 COPYright 의원프로필 '+('돌봄 부족 대기 100명 '*50)+'</p>'
        body,parts=transcript(Page(html))
        self.assertEqual(len(parts),2)
        self.assertNotIn("의원프로필",body)
        self.assertNotIn("출석관계공무원",body)
    def test_title_session_conflict_is_not_a_matching_record(self):
        self.assertTrue(identity_conflict("제10대 제336회", "제7대 제235회 회의록"))
        self.assertFalse(identity_conflict("제10대 제336회", "제10대 제336회 회의록"))
    def test_dense_generic_topics_cannot_hide_late_problem(self):
        parts=['위원 김가나 '+('시설 돌봄 교통 안전 주거를 말씀드립니다. '*45)+'돌봄 대기 증가로 주민 부담이 커지고 있습니다.']
        self.assertIn("대기 증가",review_windows(parts)[0]["passage"])
    def test_invalid_date_is_not_fabricated(self):
        self.assertEqual(day("2026.02.31"),"")
    def test_speech_date_not_selected_from_footer(self):
        rows,_=select_rows(Page('<footer>오늘 2026.09.14</footer><table><tr><td>제300회 본회의 2026.09.07</td><td><a href="/record/main?uid=1">보기</a></td></tr></table>'),"https://example.gov/late",SRC)
        self.assertEqual(rows[0]["meeting_date"],"2026-09-07")
class ConnectionRegression(unittest.TestCase):
    def test_verified_popup_field_order_and_temporary_version(self):
        from collect_pilot import detail_from
        source={"hosts":["example.gov"],"popup_adapter":True}
        call="fn_popup_page('323','1','0','1','정례회','본회의','1',1);"
        self.assertEqual(detail_from([("onclick",call)],"https://example.gov/late",source),"https://example.gov/meeting/confer/popup.do?ntime=323&contype=1&subtype=0&num=1&istemp=1")
    def test_popup_appendix_is_not_minutes(self):
        from collect_pilot import detail_from
        source={"hosts":["example.gov"],"popup_adapter":True}
        call="fn_popup_page('323','1','0','1','정례회','본회의','1',3);"
        self.assertEqual(detail_from([("onclick",call)],"https://example.gov/late",source),"")
    def test_anonymous_session_suffix_not_logged(self):
        from collect_pilot import clean_diagnostic
        self.assertEqual(clean_diagnostic("/popup.do;jsessionid=ABC123"),"/popup.do;jsessionid=[REDACTED]")

    def test_clerk_ceremony_is_a_valid_transcript_not_a_fetch_failure(self):
        html='<p>○의사담당 강가나 '+('지금부터 임시회 개회식을 시작하겠습니다. '*12)+'</p><p>○의장 김가나 '+('동료 의원 여러분께 감사드립니다. '*12)+'</p><p>○의사담당 강가나 폐식을 선언합니다.</p>'
        body,parts=transcript(Page(html))
        self.assertTrue(body)
        self.assertEqual(len(parts),3)
    def test_path_based_record_identity(self):
        from collect_pilot import detail_from
        source={"hosts":["example.gov"],"detail_pattern":r"/council/viewer/minutes/[0-9]+\.do","path_identity":True,"id_params":[]}
        self.assertEqual(detail_from([("href","/council/viewer/minutes/2946.do")],"https://example.gov",source),"https://example.gov/council/viewer/minutes/2946.do")

    def test_registry_has_all_25_unique_districts(self):
        import json
        from pathlib import Path
        sources=json.loads((Path(__file__).parent/"sources_25.json").read_text(encoding="utf-8"))
        self.assertEqual(len(sources),25)
        self.assertEqual(len({s["id"] for s in sources}),25)
        self.assertEqual({s["name"] for s in sources},set("종로구 중구 용산구 성동구 광진구 동대문구 중랑구 성북구 강북구 도봉구 노원구 은평구 서대문구 마포구 양천구 강서구 구로구 금천구 영등포구 동작구 관악구 서초구 강남구 송파구 강동구".split()))

    def test_official_recent_menu_discovery(self):
        page=Page('<a href="/kr/minutes/late.do"><span>최근회의록</span></a>')
        self.assertEqual(discover_list(page,"https://example.gov/",SRC),"https://example.gov/kr/minutes/late.do")
    def test_discovery_does_not_leave_official_host(self):
        page=Page('<a href="https://other.invalid/late">최근회의록</a>')
        self.assertEqual(discover_list(page,"https://example.gov/",SRC),"")
    def test_first_observation_is_not_no_new(self):
        current={"listing_ok":True,"expected":1,"selected":[{"url":"https://example.gov/record/main?uid=1"}]}
        self.assertEqual(window_change(current,None),"BASELINE")
    def test_fetch_failure_is_not_no_new(self):
        current={"listing_ok":False,"expected":1,"selected":[]}
        self.assertEqual(window_change(current,{}),"UNKNOWN_COLLECTION")
    def test_same_visible_window_with_alias_is_not_new(self):
        current={"listing_ok":True,"expected":1,"selected":[{"url":"https://example.gov/record/main?uid=1"}]}
        prior={**current,"selected":[{"url":"https://www.example.gov/record/main?uid=1"}]}
        self.assertEqual(window_change(current,prior),"NO_NEW_IN_VISIBLE_WINDOW")
    def test_new_record_is_new_in_visible_window(self):
        current={"listing_ok":True,"expected":1,"selected":[{"url":"https://example.gov/record/main?uid=2"}]}
        prior={**current,"selected":[{"url":"https://example.gov/record/main?uid=1"}]}
        self.assertEqual(window_change(current,prior),"NEW_IN_VISIBLE_WINDOW")
    def test_sampling_change_is_new_baseline(self):
        current={"listing_ok":True,"expected":1,"selected":[{"url":"https://example.gov/record/main?uid=1"}]}
        self.assertEqual(window_change(current,{**current,"expected":2}),"BASELINE_WINDOW_CHANGED")
    def test_partial_prior_list_is_not_new_publication(self):
        current={"listing_ok":True,"expected":2,"selected":[{"url":"https://example.gov/record/main?uid=1"},{"url":"https://example.gov/record/main?uid=2"}]}
        prior={**current,"selected":current["selected"][:1]}
        self.assertEqual(window_change(current,prior),"BASELINE_AFTER_FAILURE")
    def test_configured_legacy_identity_preserved(self):
        self.assertEqual(canonical("https://example.gov/popup.do?contype=1&ntime=318&num=1&subtype=0&noise=x",{"id_params":["contype","ntime","num","subtype"]}),"https://example.gov/popup.do?contype=1&ntime=318&num=1&subtype=0")

if __name__=="__main__":
    unittest.main()
