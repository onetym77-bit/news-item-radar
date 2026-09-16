import unittest
from datetime import date, timedelta
from watch import parse_snapshot, compare, empty_state, render, shares, DISTRICTS

def fixture(reference="2026-09-11", total_override=None):
    as_of = date.fromisoformat(reference)
    days = [(as_of - timedelta(days=30-i)).strftime("%m.%d") for i in range(30)]
    daily = " ".join(f"{day}(10건)" for day in days)
    districts = " ".join(f"{name}(8건)" for name in DISTRICTS)
    total = 300 if total_override is None else total_override
    return (
        "<p>오늘 12 건 전일 10 건</p>"
        f"<p>{as_of.strftime('%Y.%m.%d')} 현재 기간 내 민원 건 수 : {total}건</p>"
        f"<p>민원현황 추이 {as_of.strftime('%Y.%m.%d')} 현재 {daily}</p>"
        f"<p>자치구별 {as_of.strftime('%Y.%m.%d')} 현재 {districts} 자치구별 대체 텍스트</p>"
        "<p>분야별 민원현황 홈페이지 : 50건 전화 : 50건 문자 : 50건 "
        "모바일앱 : 50건 국민신문고 : 50건 기타 : 50건</p>"
        "<p>분야별 민원현황 교통 : 100건 환경/안전 : 50건 "
        "복지/문화/경제 : 50건 주택/건설 : 50건 기타 : 50건</p>"
        "<p>처리기관별 민원현황 서울시 : 50건 자치구 : 200건 "
        "투자출연기관 : 30건 기타 : 20건 자동 로그아웃 안내</p>"
    )

class StatsWatchTests(unittest.TestCase):
    def test_complete_axes_and_integrity(self):
        snapshot = parse_snapshot(fixture())
        self.assertEqual(snapshot["rolling_total"], 300)
        self.assertEqual(len(snapshot["daily"]), 30)
        self.assertEqual(len(snapshot["districts"]), 25)
        self.assertEqual(sum(snapshot["districts"].values()), snapshot["agencies"]["자치구"])
        self.assertEqual(snapshot["units"]["count"], "complaint_submissions_not_people")

    def test_bad_total_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            parse_snapshot(fixture(total_override=301))

    def test_first_baseline_and_same_reference_have_no_question(self):
        snapshot = parse_snapshot(fixture())
        first = compare(empty_state(), snapshot, "2026-09-11T10:00:00+09:00")
        self.assertEqual(first["last_run"]["signals"], [])
        self.assertIn("첫 기준 관측", render(first))
        repeated = compare(first, snapshot, "2026-09-11T11:00:00+09:00")
        self.assertEqual(repeated["last_run"]["reference_date_status"], "UNCHANGED")
        self.assertEqual(len(repeated["snapshots"]), 1)
        self.assertEqual(repeated["last_run"]["signals"], [])

    def test_reference_backwards_is_rejected(self):
        first = compare(empty_state(), parse_snapshot(fixture("2026-09-11")), "a")
        with self.assertRaisesRegex(ValueError, "backwards"):
            compare(first, parse_snapshot(fixture("2026-09-10")), "b")

    def test_share_denominator_is_separate(self):
        self.assertAlmostEqual(shares({"A": 2, "B": 8})["A"], 20.0)

if __name__ == "__main__":
    unittest.main()
