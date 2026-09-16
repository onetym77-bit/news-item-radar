import unittest

from watch import (
    change_record, collect, compare, empty_state, id_key, parse_extension,
    progress_record, render, verification_question,
)

AT1 = "2026-09-15T10:00:00+09:00"
AT2 = "2026-09-16T10:00:00+09:00"

def event(category, project_id, record_key, title="사업 A", day="2026-09-15"):
    result = {
        "key": id_key(category, project_id, record_key),
        "category": category,
        "pjt_cd": project_id,
        "record_key": record_key,
        "title": title,
        "registration_date": day,
        "source_url": "https://cis.seoul.go.kr/official",
    }
    if category == "EXTENSION":
        result["extension_days"] = 20
    return result

def observed(records=(), progress=()):
    return {
        "events": {x["key"]: x for x in records},
        "progress": {x["key"]: x for x in progress},
        "sample_counts": {
            "EXTENSION": 1, "DESIGN": 1, "PENALTY": 1, "PROGRESS": 1,
        },
    }

class WatchTests(unittest.TestCase):
    def test_extension_days_are_not_summed(self):
        fields = parse_extension(
            "변경전 준공예정 : 2026-09-08 변경후 준공예정일 : "
            "2026-09-28 연장일수 : 20일"
        )
        self.assertEqual(fields["extension_days"], 20)
        self.assertEqual(fields["before_completion"], "2026-09-08")
        self.assertEqual(fields["after_completion"], "2026-09-28")

    def test_first_baseline_not_claimed_as_temporal_change(self):
        first = compare(empty_state(), observed([
            event("EXTENSION", "6232026073185", "22048|1"),
        ]), AT1)
        self.assertTrue(first["last_run"]["first_baseline"])
        self.assertIn("이전 값이 없어", render(first))
        self.assertEqual(first["last_run"]["article_gate"], "NOT_EVALUATED")

    def test_first_baseline_suppresses_change_questions(self):
        first = compare(empty_state(), observed([
            event("PENALTY", "1112021020598", "1221", day="2026-08-20"),
            event("PENALTY", "1112021020598", "1222", day="2026-08-18"),
        ]), AT1)
        self.assertEqual(first["last_run"]["signals"], [])
        self.assertIn("기준과 비교해 생긴 질문: 0건", render(first))

    def test_penalty_question_requires_observable_impact(self):
        question = verification_question({"kind": "MULTIPLE_PENALTIES"})
        self.assertIn("어느 업체", question)
        self.assertIn("확인 가능한 영향", question)

    def test_same_record_second_day_is_not_new(self):
        record = event("EXTENSION", "6232026073185", "22048|1")
        first = compare(empty_state(), observed([record]), AT1)
        second = compare(first, observed([record]), AT2)
        self.assertEqual(second["last_run"]["new_record_keys"], [])
        self.assertEqual(second["events"][record["key"]]["last_seen_kst"], AT2)

    def test_existing_record_refreshes_fields_without_new_signal(self):
        original = event("PENALTY", "1112021020598", "1221",
                         title="영동대로 공사", day="2026-08-20")
        original["penalty_context"] = "잘못 섞인 첫 행"
        first = compare(empty_state(), observed([original]), AT1)
        corrected = dict(original, registration_date="2026-08-18",
                         penalty_context="시공 B의 올바른 행")
        second = compare(first, observed([corrected]), AT2)
        saved = second["events"][corrected["key"]]
        self.assertEqual(saved["penalty_context"], "시공 B의 올바른 행")
        self.assertEqual(saved["registration_date"], "2026-08-18")
        self.assertEqual(saved["first_seen_kst"], AT1)
        self.assertEqual(saved["last_seen_kst"], AT2)
        self.assertEqual(second["last_run"]["new_record_keys"], [])
        self.assertEqual(second["last_run"]["signals"], [])

    def test_repeat_extension_and_design_are_questions_only(self):
        old = compare(empty_state(), observed([
            event("EXTENSION", "6232026073185", "22048|1"),
            event("DESIGN", "6232026073185", "21970|1"),
        ]), AT1)
        next_state = compare(old, observed([
            event("EXTENSION", "6232026073185", "22049|2"),
            event("DESIGN", "6232026073185", "21971|2"),
        ]), AT2)
        kinds = {x["kind"] for x in next_state["last_run"]["signals"]}
        self.assertIn("REPEAT_EXTENSION", kinds)
        self.assertIn("REPEAT_DESIGN", kinds)
        self.assertTrue(all(x["article_gate"] == "NOT_EVALUATED"
                            for x in next_state["last_run"]["signals"]))

    def test_multiple_penalties_make_one_verification_question(self):
        prior = compare(empty_state(), observed([]), AT1)
        current = compare(prior, observed([
            event("PENALTY", "1112021020598", "1221", "영동대로 공사"),
            event("PENALTY", "1112021020598", "1222", "영동대로 공사"),
            event("PENALTY", "1112021020598", "1223", "영동대로 공사"),
        ]), AT2)
        signals = [x for x in current["last_run"]["signals"]
                   if x["kind"] == "MULTIPLE_PENALTIES"]
        self.assertEqual(len(signals), 1)
        self.assertIn("중복 게시인지 확인", signals[0]["observation"])
        self.assertEqual(signals[0]["article_gate"], "NOT_EVALUATED")

    def test_penalty_with_change_not_causal_claim(self):
        old = compare(empty_state(), observed([
            event("DESIGN", "1112021020598", "21970|1"),
        ]), AT1)
        current = compare(old, observed([
            event("PENALTY", "1112021020598", "1223"),
        ]), AT2)
        signal = current["last_run"]["signals"][0]
        self.assertEqual(signal["kind"], "PENALTY_WITH_CHANGE")
        self.assertIn("인과관계", signal["observation"])

    def test_progress_gap_uses_title_only_within_progress(self):
        card = ("■ 거여 119안전센터 건립공사 사업기간 : "
                "2025-11-19 ~ 2028-03-12 계 획 : 17 % 실 적 : 15.5 %")
        record = progress_record(card)
        self.assertIsNone(record["pjt_cd"])
        self.assertEqual(record["gap_pp"], -1.5)
        previous = dict(record, gap_pp=0)
        old = compare(empty_state(), observed(progress=[previous]), AT1)
        current = compare(old, observed(progress=[record]), AT2)
        signal = current["last_run"]["signals"][0]
        self.assertEqual(signal["kind"], "PROGRESS_GAP_WIDENED")
        self.assertIsNone(signal["pjt_cd"])

    def test_source_failure_cannot_be_zero_signal(self):
        def broken(url):
            raise TimeoutError("official host timed out")
        with self.assertRaisesRegex(RuntimeError, "SOURCE_ACCESS_FAILED"):
            collect(fetch=broken)

    def test_change_key_and_missing_date_rejected_in_collection_model(self):
        item = {
            "title": "공사",
            "link": {
                "first_arg_project_candidate": "6232026073185",
                "quoted_args": ["6232026073185", "공사", "강남구", "22048|1"],
            },
            "registration_date": "2026-09-15",
            "row_excerpt": "연장일수 : 20일",
        }
        record = change_record("EXTENSION", item)
        self.assertEqual(record["pjt_cd"], "6232026073185")
        self.assertEqual(record["record_key"], "22048|1")
        with self.assertRaises(ValueError):
            id_key("DESIGN", "bad", "21970|1")

if __name__ == "__main__":
    unittest.main()
