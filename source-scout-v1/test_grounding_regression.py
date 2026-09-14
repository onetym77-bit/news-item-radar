import importlib.util
import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


scout = load_module("source_scout_grounding_regression", "scout_sources.py")
feed = load_module("source_feed_grounding_regression", "collect_daily_feed.py")


class GroundingRegressionTests(unittest.TestCase):
    def setUp(self):
        self.council = {
            "id": "council_minutes",
            "name": "서울시의회 회의록",
            "local": True,
            "voice": False,
            "role": "BOTH",
        }
        self.research = {
            "id": "seoul_research",
            "name": "서울연구원",
            "local": True,
            "voice": False,
            "role": "BOTH",
        }
        self.labor = {
            "id": "labor_arrears",
            "name": "임금체불",
            "local": False,
            "voice": False,
            "role": "BOTH",
        }
        self.open_data = {
            "id": "seoul_open_data",
            "name": "열린데이터",
            "local": True,
            "voice": False,
            "role": "VERIFICATION",
        }

    def signals(self, text, source=None, kind="PAGE_CHUNK"):
        return scout.score_text(text, source or self.council, kind)[3]

    def test_generic_speech_is_rejected(self):
        result = self.signals(
            "서울의 교육격차를 줄이고 안전한 학교를 만들기 위해 최선을 다하겠습니다"
        )
        self.assertEqual(result["precheck_status"], "FAIL")
        self.assertEqual(result["content_class"], "SPEECH_PROMISE")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_concern_only_is_held(self):
        result = self.signals(
            "학생인권조례 폐지는 교육 격차와 갈등을 초래할 수 있어 우려됩니다"
        )
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["content_class"], "CONCERN_OR_ATTRIBUTED_CLAIM")

    def test_procedure_numbers_are_not_measurements(self):
        result = self.signals(
            "제4항과 제41조에 따라 11대 의회 상임위원을 선임하고 전자투표로 표결합니다"
        )
        self.assertEqual(result["precheck_status"], "FAIL")
        self.assertEqual(result["content_class"], "PARLIAMENTARY_PROCEDURE")
        self.assertEqual(result["substantive_values"], [])
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_navigation_is_rejected_for_verification(self):
        result = self.signals(
            "본문 바로가기 메뉴 로그인 회원가입 분야 선택 파일내려받기 전체 설명보기",
            self.open_data,
            "CONTEXT_WINDOW",
        )
        self.assertEqual(result["content_class"], "NAVIGATION")
        self.assertFalse(result["verification_usable"])

    def test_research_title_without_body_is_held(self):
        result = self.signals("집합건물 분쟁실태와 지원방안", self.research, "LINK_LABEL")
        self.assertEqual(result["content_class"], "DOCUMENT_TITLE_ONLY")
        self.assertEqual(result["precheck_status"], "HOLD")

    def test_table_heading_without_values_is_held(self):
        result = self.signals("2026.7월 지역별 체불 현황", self.labor, "PAGE_CHUNK")
        self.assertEqual(result["content_class"], "TABLE_SCHEMA_WITHOUT_VALUE")
        self.assertEqual(result["precheck_status"], "HOLD")

    def test_contact_footer_is_rejected(self):
        result = self.signals(
            "서울특별시청 (04524) 서울특별시 중구 세종대로 110 · 문의 및 전화민원 신청: 02)120",
            {
                "id": "eungdapso", "name": "응답소", "local": True,
                "voice": True, "role": "DISCOVERY",
            },
            "CONTEXT_WINDOW",
        )
        self.assertEqual(result["content_class"], "CONTACT_BOILERPLATE")
        self.assertEqual(result["precheck_status"], "FAIL")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_budget_input_without_observed_outcome_is_held(self):
        result = self.signals(
            "서울시는 1조 4,570억 원 추경을 편성해 교통비 부담을 낮추고 피해지원 재원을 투입했습니다"
        )
        self.assertEqual(result["content_class"], "POLICY_ANNOUNCEMENT")
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_data_portal_display_notice_is_rejected(self):
        result = self.signals(
            "※ 가장 최근에 개방된 100개 데이터만 표시됩니다.",
            self.open_data,
            "PAGE_CHUNK",
        )
        self.assertEqual(result["content_class"], "PLATFORM_NOTICE")
        self.assertFalse(result["verification_usable"])

    def test_no_space_complaint_footer_is_rejected(self):
        result = self.signals(
            "다 - 듣겠습니다 · 서울시 불편사항 응답소에 얘기해주세요. · 민원처리안내",
            {
                "id": "eungdapso", "name": "응답소", "local": True,
                "voice": True, "role": "DISCOVERY",
            },
            "CONTEXT_WINDOW",
        )
        self.assertEqual(result["content_class"], "CONTACT_BOILERPLATE")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_complaint_request_title_without_experience_is_not_direct(self):
        result = self.signals(
            '귀하의 민원내용은 "도로시설물 단차 점검 및 보수·보강 요청"에 관한 것입니다',
            {
                "id": "eungdapso", "name": "응답소", "local": True,
                "voice": True, "role": "DISCOVERY",
            },
        )
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_phone_only_complaint_footer_is_rejected(self):
        result = self.signals(
            "02)2133-7860 · 민원처리 안내: 민원담당관 · 02)2133-7935",
            {
                "id": "eungdapso", "name": "응답소", "local": True,
                "voice": True, "role": "DISCOVERY",
            },
        )
        self.assertEqual(result["content_class"], "CONTACT_BOILERPLATE")

    def test_education_budget_promise_is_not_outcome(self):
        result = self.signals(
            "교육복지를 강화하겠습니다. 3세 보육비 지원 확대에 111억 원을 편성하여 학부모 부담을 덜겠습니다"
        )
        self.assertEqual(result["content_class"], "POLICY_ANNOUNCEMENT")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_labor_table_structure_with_region_count_is_held(self):
        result = self.signals(
            "구분, 전체, 서울, 부산으로 구성된 26.7월 지역별(17개 시도) 체불 현황의 첫번째 테이블",
            self.labor,
        )
        self.assertEqual(result["content_class"], "TABLE_SCHEMA_WITHOUT_VALUE")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_isolated_verification_number_is_not_a_dataset_asset(self):
        result = self.signals("ㅇ 운영주체 : 시립쪽방상담소(5개소)", self.open_data)
        self.assertFalse(result["verification_usable"])

    def test_hypothetical_policy_example_is_held(self):
        result = self.signals(
            "똑같이 100명이 이용한다고 했을 때 K-패스 서울시 부담률은 60%, 다른 카드는 100%입니다"
        )
        self.assertEqual(result["content_class"], "HYPOTHETICAL_EXAMPLE")
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_positive_change_uses_neutral_decomposition_question(self):
        text = "서울 출생아 수는 2024년 4월 이후 26개월 연속 증가세를 보이고 있습니다"
        result = self.signals(text)
        self.assertEqual(result["change_direction"], "POSITIVE")
        self.assertEqual(result["evidence_anchor"], "DECOMPOSABLE_STRUCTURE")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertNotIn("문제 징후", payload["question"])
        self.assertIn("증가·회복", payload["question"])

    def test_event_with_measured_harm_is_not_hard_excluded(self):
        text = "서울 축제 압사사고 12건 발생 자치구별 안전인력 격차"
        parser = scout.parse_html(f"<p>{text}</p>")
        rows = scout.extract_records(
            parser,
            "https://ms.smc.seoul.kr/record/example",
            self.council,
            include_windows=False,
        )
        self.assertTrue(rows)
        self.assertTrue(rows[0]["qualified"])

    def test_foreign_card_total_is_decomposable(self):
        result = self.signals("서울 외국인 카드소비 총액 1조 원 자치구별·업종별 현황")
        self.assertEqual(result["precheck_status"], "PASS")
        self.assertEqual(result["evidence_anchor"], "DECOMPOSABLE_STRUCTURE")
        self.assertIn("1조 원", result["substantive_values"])

    def test_ud_taxi_question_does_not_invent_scene(self):
        text = (
            "서울 UD택시는 12대만 06~15시 운행해 요청과 매칭될 확률이 낮아 "
            "이용이 제한된다는 지적"
        )
        _, _, _, result = scout.score_text(text, self.council)
        self.assertNotEqual(result["evidence_anchor"], "NONE")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_status"], "PASS")
        self.assertNotIn("병원", payload["question"])
        self.assertNotIn("미배차", payload["question"])

    def test_ud_name_alone_cannot_trigger_supply_question(self):
        text = "서울 UD택시 사고 3건 발생"
        result = self.signals(text)
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_contract"], ["문제 근거 앵커"])
        self.assertNotIn("공급량", payload["question"])
        self.assertNotIn("요청량", payload["question"])

    def test_bus_claim_keeps_attribution_and_neutral_question(self):
        text = (
            "서울 시내버스 소송 부담을 협회는 5,266억 원에서 1조 216억 원으로 추산했고 "
            "연간 적자지원은 8,915억 원이다"
        )
        _, _, _, result = scout.score_text(text, self.council)
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")
        self.assertEqual(result["claim_status"], "ATTRIBUTED_CLAIM")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_status"], "PASS")
        self.assertNotIn("관리 공백", payload["question"])

    def test_council_issue_mention_with_only_speaking_time_is_held(self):
        result = self.signals(
            "삼성역 철근 누락 사고 이야기하겠습니다. 남은 시간이 12분입니다. "
            "4년 동안 40분씩 1 대 1로 시정질문을 했습니다."
        )
        self.assertEqual(result["content_class"], "ISSUE_MENTION_ONLY")
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_complaint_volume_dashboard_is_not_a_problem_candidate(self):
        result = self.signals(
            "(2026. 09. 14 현재) 민원 현황판 오늘 4,714건, "
            "4월 234,504건, 5월 238,771건, 6월 243,815건 · 월별 민원접수 건수",
            {
                "id": "eungdapso", "name": "응답소", "local": True,
                "voice": True, "role": "DISCOVERY",
            },
            "CONTEXT_WINDOW",
        )
        self.assertEqual(result["content_class"], "AGGREGATE_ACTIVITY_DASHBOARD")
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_harm_increase_cannot_be_labeled_positive(self):
        text = "서울 임금체불은 100건으로 급증하며 증가세를 보였습니다"
        result = self.signals(text)
        self.assertEqual(result["change_direction"], "NEGATIVE")
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertNotIn("증가·회복", payload["question"])

    def test_distinct_issues_on_one_minutes_url_survive_overlap_dedup(self):
        common = {
            "qualified": True,
            "precheck_status": "PASS",
            "grounding_status": "PASS",
            "score": 8,
            "url": "https://ms.smc.seoul.kr/record/one",
        }
        rows = [
            {**common, "text": "전세사기 피해 100가구, 보증금 피해액 200억 원"},
            {**common, "text": "전세사기 피해 100가구, 보증금 피해액 200억 원이 서울에서 확인됐다"},
            {**common, "text": "시내버스 소송 부담 500억 원, 운송사별 보조금 검증 필요"},
        ]
        selected = scout.select_distinct_council_records(
            rows, "https://ms.smc.seoul.kr/kr/assembly/main.do"
        )
        self.assertEqual(len(selected), 2)
        self.assertTrue(any("전세사기" in row["text"] for row in selected))
        self.assertTrue(any("시내버스" in row["text"] for row in selected))

    def test_feed_keeps_distinct_core_issues_with_same_url(self):
        base = {
            "source_id": "council_minutes",
            "source_name": "서울시의회 회의록",
            "score": 8,
            "qualified": True,
            "grounding_status": "PASS",
            "precheck_status": "PASS",
            "evidence_anchor": "MEASURED_PROBLEM_SIGNAL",
            "url": "https://ms.smc.seoul.kr/record/one",
        }
        rows = [
            {**base, "text": "전세사기 피해 100가구", "question": "어디에 집중됐나?"},
            {**base, "text": "시내버스 소송 부담 500억 원", "question": "누가 부담하나?"},
        ]

        class FakeModule:
            @staticmethod
            def run_source(source):
                metric = {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "http_ok": True, "status": 200, "status_detail": "OK",
                    "requests": 1, "failed_requests": 0, "extracted": 2,
                    "precheck_pass": 2, "grounded": 2, "qualified": 2,
                }
                return metric, rows

        FakeModule.SOURCES = [self.council]
        built = feed.build_feed(FakeModule)
        self.assertEqual(len(built["core_discovery"]), 2)

    def test_verification_source_is_not_recommended_without_usable_asset(self):
        metric = {
            "role": "VERIFICATION",
            "status_detail": "OK",
            "http_ok": True,
            "failed_requests": 0,
            "requests": 1,
            "extracted": 10,
            "verification_usable": 0,
            "qualified": 0,
            "cadence": "continuous",
            "localization_leads": 0,
            "strong": 0,
        }
        self.assertNotEqual(scout.recommendation(metric), "검증 데이터 지도에 편입")

    def test_high_score_navigation_cannot_reenter_verification_map(self):
        fake_record = {
            "source_id": "seoul_open_data",
            "source_name": "열린데이터",
            "score": 99,
            "qualified": True,
            "verification_usable": False,
            "grounding_status": "PASS",
            "text": "메뉴 문구",
            "url": "https://example.invalid",
            "question": "검증?",
        }

        class FakeModule:
            @staticmethod
            def run_source(source):
                metric = {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "http_ok": True, "status": 200, "status_detail": "DEGRADED_NO_DATASET_TEXT",
                    "requests": 1, "failed_requests": 0, "extracted": 1,
                    "precheck_pass": 0, "grounded": 1, "qualified": 1,
                }
                return metric, [fake_record]

        FakeModule.SOURCES = [self.open_data]
        built = feed.build_feed(FakeModule)
        self.assertEqual(built["verification_map"], [])

    def test_question_numbers_are_subset_of_source_numbers(self):
        text = "서울 외국인 카드소비 총액 1조 원 자치구별 현황"
        result = self.signals(text)
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
