import unittest
from collect_pilot import Page, select_rows, transcript, day, review_windows
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
    def test_invalid_date_is_not_fabricated(self):
        self.assertEqual(day("2026.02.31"),"")
    def test_speech_date_not_selected_from_footer(self):
        rows,_=select_rows(Page('<footer>오늘 2026.09.14</footer><table><tr><td>제300회 본회의 2026.09.07</td><td><a href="/record/main?uid=1">보기</a></td></tr></table>'),"https://example.gov/late",SRC)
        self.assertEqual(rows[0]["meeting_date"],"2026-09-07")
if __name__=="__main__":
    unittest.main()
