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

    def test_review_card_stays_verification_only(self):
        phrase = "신청하려면 현장에서 본인 부담금을 내야 한다고 들었습니다."
        context = {"status": "BODY_READ", "body": "○ 의원 김가람 " + phrase,
                   "parts": ["의원 김가람 " + phrase],
                   "current_sha256": "a" * 64, "title_date": "2026-09-14",
                   "request_status": 200}
        output = module.collect(sample(), sources(), model="test", api_key="dummy",
                                fetcher=lambda row, source: context,
                                assessor=lambda body, row, model, key: answer(phrase))
        self.assertEqual(output["review_count"], 7)
        self.assertEqual(output["briefing_output"], "NONE")
        self.assertFalse(output["automatic_ledger_write"])
        self.assertNotIn("신청하려면", str(output["results"][0].get("body", "")))


if __name__ == "__main__":
    unittest.main()
