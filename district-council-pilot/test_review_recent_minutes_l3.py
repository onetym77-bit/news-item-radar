import unittest
from datetime import date

import review_recent_minutes_l3 as module


def sources():
    return [{"id": str(i), "name": "구" + str(i), "hosts": ["example.org"]}
            for i in range(25)]


def l2_payload():
    return {"source_count": 25, "results": [
        {"source_id": str(i), "source_name": "구" + str(i),
         "status": "BODY_METADATA_MATCH", "provisional": False,
         "document_url": f"https://example.org/minutes/{i}",
         "meeting_date": f"2026-09-{27 - (i % 9):02d}", "body_sha256": "a" * 64}
        for i in range(25)]}


def fixed(*urls):
    return {"documents": [{"document_url": url} for url in urls]}


def history(*urls):
    return {"schema": 1, "reviewed_documents": [
        {"key": module.record_key(url), "source_id": "x",
         "meeting_date": "2026-09-20", "reviewed_at_kst": "2026-09-21T09:00:00+09:00"}
        for url in urls]}


def watch(*keys):
    return {"last_run": {"results": [
        {"status": "NEW_IN_VISIBLE_WINDOW",
         "candidates": [{"key": key} for key in keys]}
    ]}}


def semantic_answer(quote, verdict="REVIEW"):
    return {
        "verdict": verdict, "anchor_quote": quote,
        "observed_issue": "생활권 시설 이용 조건과 실제 주민 부담이 달라질 수 있다는 발언이다.",
        "citizen_stake_to_check": "주민이 가까운 시설을 이용하지 못해 이동과 돌봄 선택이 달라지는지 확인한다.",
        "editorial_hypothesis": "시설 감소가 특정 동네의 서비스 공백으로 이어질 가능성이 있다.",
        "test_question": "시설이 줄어든 동네 주민은 실제로 더 멀리 이동하거나 이용을 포기했는가?",
        "alternative_explanation": "인구와 이용 수요도 함께 줄어 남은 시설이 수요를 감당할 수 있다.",
        "first_check": "동별 시설 수와 정원, 대기자 자료를 주민 이용 경험과 대조한다.",
        "broadcast_path": "폐쇄된 시설과 운영 시설, 주민 이동 동선과 행정 자료를 비교한다.",
        "reason": "생활권별 서비스 선택의 변화를 현장과 자료로 가를 수 있다.",
    }


class RecentL3Tests(unittest.TestCase):
    def test_new_visible_document_precedes_bootstrap_and_limit(self):
        l2 = l2_payload()
        fresh_key = module.record_key(l2["results"][7]["document_url"])
        plan = module.select_plan(
            l2, watch(fresh_key), history(), fixed(), date(2026, 9, 28), 3)
        self.assertEqual(len(plan), 3)
        self.assertEqual(plan[0]["source_id"], "7")
        self.assertEqual(plan[0]["selection_reason"], "NEW_IN_VISIBLE_WINDOW")
        self.assertTrue(all(row["source_id"] != plan[0]["source_id"] for row in plan[1:]))

    def test_fixed_reviewed_future_and_provisional_are_excluded(self):
        l2 = l2_payload()
        l2["results"][0]["meeting_date"] = "2026-09-30"
        l2["results"][1]["provisional"] = True
        fixed_url = l2["results"][2]["document_url"]
        reviewed_url = l2["results"][3]["document_url"]
        plan = module.select_plan(
            l2, {}, history(reviewed_url), fixed(fixed_url), date(2026, 9, 28), 5)
        ids = {row["source_id"] for row in plan}
        self.assertFalse({"0", "1", "2", "3"}.intersection(ids))
        self.assertLessEqual(len(plan), 5)
        self.assertTrue(all(row["selection_reason"] == "LATEST_UNREVIEWED_BOOTSTRAP"
                            for row in plan))

    def test_no_eligible_document_is_not_no_signal_claim(self):
        l2 = l2_payload()
        for row in l2["results"]:
            row["status"] = "UNKNOWN_COLLECTION"
        plan = module.select_plan(l2, {}, history(), fixed(), date(2026, 9, 28), 5)
        payload, next_history = module.review_plan(
            plan, sources(), history(), model="test", offline=True,
            desk_assessor=lambda *args: self.fail("desk must not run"))
        self.assertEqual(payload["selected_count"], 0)
        self.assertEqual(payload["desk_status"], "NOT_RUN")
        self.assertIn("아이템이 없다는 뜻이 아니다", module.render(payload))
        self.assertEqual(next_history["reviewed_documents"], [])

    def test_review_and_desk_are_separate_and_raw_body_is_not_stored(self):
        phrase = "우리 동네에서 보육시설이 줄어 이용자가 멀리 이동하고 있습니다."
        plan = [{
            "key": module.record_key("https://example.org/minutes/new"),
            "source_id": "0", "source_name": "구0",
            "document_url": "https://example.org/minutes/new",
            "meeting_date": "2026-09-27", "body_sha256": "a" * 64,
            "selection_reason": "NEW_IN_VISIBLE_WINDOW",
        }]
        context = {"status": "BODY_READ", "body": "의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase], "request_status": 200}
        desk = {"reviews": [{
            "source_id": "0", "verdict": "VERIFY_FIRST",
            "citizen_path": "시설 이용 주민의 통원거리와 돌봄 선택으로 연결될 수 있다.",
            "broadcast_value": "시설 현장과 이용자 동선이 확인되면 방송 장면을 구성할 수 있다.",
            "missing_piece": "동별 정원과 대기자, 실제 장거리 통원 사례가 아직 없다.",
            "decisive_test": "시설 감소 지역의 정원과 주민 이동시간을 대조해 확인한다.",
            "reason": "문제 경로는 구체적이지만 실제 서비스 공백을 먼저 확인해야 한다.",
        }]}
        payload, next_history = module.review_plan(
            plan, sources(), history(), model="test", api_key="dummy",
            fetcher=lambda row, source: context,
            assessor=lambda *args: semantic_answer(phrase),
            desk_assessor=lambda *args: desk)
        self.assertEqual(payload["review_count"], 1)
        self.assertEqual(payload["verify_first_count"], 1)
        self.assertEqual(payload["desk_status"], "COMPLETE")
        self.assertNotIn(phrase, str(payload["results"][0].get("body", "")))
        self.assertNotIn("evidence_context", payload["results"][0])
        self.assertEqual(len(next_history["reviewed_documents"]), 1)

    def test_hold_keeps_cue_and_enters_history(self):
        phrase = "셔틀버스 예산을 줄이면 실제 노선이 달라질 수 있습니다."
        plan = [{
            "key": module.record_key("https://example.org/minutes/hold"),
            "source_id": "1", "source_name": "구1",
            "document_url": "https://example.org/minutes/hold",
            "meeting_date": "2026-09-26", "body_sha256": "a" * 64,
            "selection_reason": "LATEST_UNREVIEWED_BOOTSTRAP",
        }]
        context = {"status": "BODY_READ", "body": "의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase], "request_status": 200}
        answer = semantic_answer(phrase, "HOLD")
        payload, next_history = module.review_plan(
            plan, sources(), history(), model="test", api_key="dummy",
            fetcher=lambda row, source: context,
            assessor=lambda *args: answer,
            desk_assessor=lambda *args: self.fail("no review means no desk"))
        self.assertEqual(payload["desk_status"], "NOT_NEEDED")
        self.assertIn("held_cue", payload["results"][0])
        self.assertEqual(len(next_history["reviewed_documents"]), 1)

    def test_desk_error_does_not_advance_history(self):
        phrase = "우리 동네에서 보육시설이 줄어 이용자가 멀리 이동하고 있습니다."
        plan = [{
            "key": module.record_key("https://example.org/minutes/error"),
            "source_id": "0", "source_name": "구0",
            "document_url": "https://example.org/minutes/error",
            "meeting_date": "2026-09-27", "body_sha256": "a" * 64,
            "selection_reason": "NEW_IN_VISIBLE_WINDOW",
        }]
        context = {"status": "BODY_READ", "body": "의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase], "request_status": 200}
        payload, next_history = module.review_plan(
            plan, sources(), history(), model="test", api_key="dummy",
            fetcher=lambda row, source: context,
            assessor=lambda *args: semantic_answer(phrase),
            desk_assessor=lambda *args: {"reviews": []})
        self.assertEqual(payload["desk_status"], "ERROR")
        self.assertEqual(next_history["reviewed_documents"], [])


if __name__ == "__main__":
    unittest.main()
