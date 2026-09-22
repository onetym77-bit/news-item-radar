import unittest
from datetime import date

import interpret_l3_context as module


def sources():
    return [{"id": str(i), "name": "구" + str(i), "hosts": ["example.org"]} for i in range(25)]


def sample():
    return {"basis_run_id": 1, "documents": [
        {"source_id": str(i), "source_name": "구" + str(i),
         "document_url": "https://example.org/minutes/" + str(i),
         "meeting_date": "2026-09-14", "body_sha256": "a" * 64}
        for i in range(7)]}


def answer(quote):
    return {"verdict": "REVIEW", "anchor_quote": quote,
            "observed_issue": "서비스 신청 과정에서 비용을 누가 부담하는지 두 의견이 충돌했다.",
            "citizen_stake_to_check": "이용을 포기하거나 비용을 떠안는 주민이 있는지 확인한다.",
            "editorial_hypothesis": "이용료 기준이 자치구에 따라 달라 이용 선택이 바뀔 수 있다.",
            "test_question": "신청 기준이 같은 두 지역의 이용자가 왜 서로 다른 부담을 지는가?",
            "alternative_explanation": "이용자의 소득과 서비스 종류가 달라 비교 자체가 성립하지 않을 수 있다.",
            "first_check": "두 자치구의 신청서와 실제 납부액, 이용자 인터뷰를 대조한다.",
            "broadcast_path": "신청 현장, 두 주민의 선택, 운영기관 설명과 원자료를 대조한다.",
            "reason": "신청 기준과 실제 부담의 갈림길을 현장에서 확인할 수 있다."}


class L3ContextTests(unittest.TestCase):
    def test_fixed_sample_rejects_wrong_denominator(self):
        doc = sample()
        doc["documents"].pop()
        with self.assertRaisesRegex(ValueError, "seven"):
            module.validate_sample(doc, sources())

    def test_quote_must_be_contiguous_in_a_speech_turn(self):
        body = "○ 의원 김가람 신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."
        parts = ["의원 김가람 신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."]
        a = answer("신청하려면 현장에서 본인 부담금을 내야 한다고")
        status, card = module.validate_assessment(a, body, parts)
        self.assertEqual(status, "REVIEW")
        self.assertEqual(card["turn_index"], 0)
        a["anchor_quote"] = "문맥에 없는 말을 덧붙였습니다"
        self.assertEqual(module.validate_assessment(a, body, parts)[0], "INVALID_QUOTE")

    def test_generic_question_is_not_a_review_card(self):
        body = "○ 의원 김가람 신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."
        parts = ["의원 김가람 신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."]
        a = answer("신청하려면 현장에서 본인 부담금을 내야 한다고")
        a["test_question"] = "시민에게 어떤 영향이 있는지 확인해 볼 수 있을까?"
        self.assertEqual(module.validate_assessment(a, body, parts)[0], "GENERIC_QUESTION")

    def test_no_signal_does_not_create_card(self):
        a = {key: "" for key in module.SCHEMA["required"]}
        a["verdict"] = "NO_SIGNAL"
        self.assertEqual(module.validate_assessment(a, "", [])[0], "NO_SIGNAL")

    def test_offline_collect_never_calls_model_or_stores_body(self):
        phrase = "신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."
        context = {"status": "BODY_READ", "body": "○ 의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase],
                   "current_sha256": "b" * 64, "title_date": "2026-09-14",
                   "request_status": 200}
        def fetcher(row, source):
            return context
        def assessor(*args):
            raise AssertionError("model must not run offline")
        output = module.collect(sample(), sources(), model="test", offline=True,
                                fetcher=fetcher, assessor=assessor)
        self.assertEqual(len(output["results"]), 7)
        self.assertEqual(output["review_count"], 0)
        self.assertTrue(all(row["body_changed"] for row in output["results"]))
        self.assertNotIn(phrase, str(output))

    def test_changed_fixed_body_skips_semantic_call(self):
        row = sample()["documents"][0]
        class FakeClient:
            def __init__(self, source):
                self.logs = [{"status": 200}]
            def get(self, url):
                return type('PageFixture', (), {'title': ['2026-09-14']})()
        old_client, old_transcript = module.Client, module.transcript
        try:
            module.Client = FakeClient
            module.transcript = lambda page: ("○ 의원 김가람 새 본문 내용입니다. " * 20, ["의원 김가람 새 본문 내용입니다. " * 20])
            context = module.fetch_context(row, sources()[0])
        finally:
            module.Client, module.transcript = old_client, old_transcript
        self.assertEqual(context["status"], "BODY_CHANGED")
        result = module.collect(sample(), sources(), model="test", api_key="dummy",
                                fetcher=lambda row, source: context,
                                assessor=lambda *args: self.fail("changed body must not reach model"))
        self.assertTrue(all(item["semantic_status"] == "NOT_RUN" for item in result["results"]))

    def test_hold_reason_is_retained_without_card(self):
        phrase = "신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."
        context = {"status": "BODY_READ", "body": "○ 의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase], "current_sha256": "a" * 64,
                   "title_date": "2026-09-14", "request_status": 200}
        a = {key: "" for key in module.SCHEMA["required"]}
        a["verdict"], a["reason"] = "HOLD", "발언은 있지만 실제 부담 대상과 의사결정 맥락이 드러나지 않는다."
        result = module.collect(sample(), sources(), model="test", api_key="dummy",
                                fetcher=lambda row, source: context,
                                assessor=lambda *args: a)
        self.assertEqual(result["review_count"], 0)
        self.assertIn("부담 대상", result["results"][0]["semantic_reason"])
        self.assertNotIn("verification_card", result["results"][0])

    def test_review_card_stays_verification_only(self):
        phrase = "신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."
        context = {"status": "BODY_READ", "body": "○ 의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase],
                   "current_sha256": "a" * 64, "title_date": "2026-09-14",
                   "request_status": 200}
        output = module.collect(sample(), sources(), model="test", api_key="dummy",
                                fetcher=lambda row, source: context,
                                assessor=lambda body, row, model, key: answer(phrase),
                                desk_assessor=lambda inputs, model, key: {"reviews": [
                                    {"source_id": item["source_id"], "verdict": "LOW_PRIORITY",
                                     "citizen_path": "주민의 직접 부담 경로는 아직 확인되지 않았다.",
                                     "broadcast_value": "현장과 당사자 장면이 아직 부족해 방송 구성은 약하다.",
                                     "missing_piece": "실제 서비스를 이용한 주민의 경험과 비용 자료가 필요하다.",
                                     "decisive_test": "이용자 납부 내역과 실제 선택 변화가 있는지 확인한다.",
                                     "reason": "검증 질문은 성립하지만 현재는 시민 생활 변화가 약하다."}
                                    for item in inputs]}))
        self.assertEqual(output["review_count"], 7)
        self.assertEqual(output["pursue_count"], 0)
        self.assertEqual(output["desk_status"], "COMPLETE")
        self.assertEqual(output["results"][0]["editorial_review"]["verdict"], "LOW_PRIORITY")
        self.assertEqual(output["briefing_output"], "NONE")
        self.assertFalse(output["automatic_ledger_write"])
        self.assertNotIn("신청하려면", str(output["results"][0].get("body", "")))

    def test_hold_grounded_cue_preserves_next_check(self):
        phrase = "공공 셔틀버스의 운영비가 삭감되어 노선 조정이 필요한지 살펴봐야 합니다."
        a = answer(phrase)
        a["verdict"] = "HOLD"
        a["first_check"] = "노선별 운행 계획과 실제 감차 여부를 시청 자료로 확인한다."
        status, cue = module.validate_assessment(a, "○ 의원 " + phrase, ["의원 " + phrase])
        self.assertEqual(status, "HOLD")
        self.assertEqual(cue["anchor_quote"], phrase)
        self.assertIn("운행 계획", cue["first_check"])
        self.assertNotIn("broadcast_path", cue)

    def test_desk_rejects_missing_or_duplicate_source(self):
        review = {"source_id": "0", "verdict": "PURSUE",
                  "citizen_path": "실제 버스 이용자의 대체 수단이 줄어들 가능성이 있다.",
                  "broadcast_value": "버스 정류장과 이용자 선택을 화면에 담을 수 있다.",
                  "missing_piece": "운행 감축 계획과 실제 이용자 수가 확인되지 않았다.",
                  "decisive_test": "예산 조정 전후의 시간표와 운행 횟수를 대조한다.",
                  "reason": "시민 이동권의 갈림길을 검증할 수 있다."}
        with self.assertRaisesRegex(ValueError, "IDs mismatch"):
            module.validate_desk_response({"reviews": [review, review]}, ["0", "1"])
        with self.assertRaisesRegex(ValueError, "field mismatch"):
            module.validate_desk_response({"reviews": [{**review, "unknown": "x"}]}, ["0"])

    def test_desk_failure_does_not_promote_verification_card(self):
        phrase = "신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."
        context = {"status": "BODY_READ", "body": "○ 의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase], "current_sha256": "a" * 64,
                   "title_date": "2026-09-14", "request_status": 200}
        output = module.collect(sample(), sources(), model="test", api_key="dummy",
                                fetcher=lambda row, source: context,
                                assessor=lambda body, row, model, key: answer(phrase),
                                desk_assessor=lambda *args: {"reviews": []})
        self.assertEqual(output["desk_status"], "ERROR")
        self.assertEqual(output["pursue_count"], 0)
        self.assertTrue(all("editorial_review" not in row for row in output["results"]))
        self.assertIn("방송 가치 평가에 실패했다", module.render(output))

    def test_offline_does_not_run_desk(self):
        context = {"status": "BODY_READ", "body": "본문", "parts": ["본문"],
                   "current_sha256": "a" * 64, "title_date": "2026-09-14",
                   "request_status": 200}
        output = module.collect(sample(), sources(), model="test", offline=True,
                                fetcher=lambda row, source: context,
                                desk_assessor=lambda *args: self.fail("desk must not run offline"))
        self.assertEqual(output["desk_status"], "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
