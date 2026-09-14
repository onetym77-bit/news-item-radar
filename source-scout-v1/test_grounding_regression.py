import importlib.util
import sys
import tempfile
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
inject = load_module("source_inject_grounding_regression", "inject_feed_into_briefing.py")


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
        self.assertEqual(
            payload["grounding_contract"], ["귀속된 주장", "문제 근거 앵커"]
        )
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
            "freshness_status": "FRESH",
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

    def test_complaint_portal_instruction_is_rejected(self):
        result = self.signals(
            "120다산콜재단 전화, 문자, 챗봇 또는 스마트불편신고 앱에서 신청한 "
            "민원의 처리결과는 응답소 민원결과에서 클릭하여 확인하세요",
            {
                "id": "eungdapso", "name": "응답소", "local": True,
                "voice": True, "role": "DISCOVERY",
            },
        )
        self.assertEqual(result["content_class"], "PORTAL_INSTRUCTION")
        self.assertEqual(result["precheck_status"], "FAIL")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_scope_count_does_not_turn_concern_into_measured_fact(self):
        result = self.signals(
            "구청 전담인력이 별로 없어 우왕좌왕할 가능성이 많고 "
            "25개 자치구마다 기준이 달라 혼선과 갈등이 우려됩니다"
        )
        self.assertEqual(result["substantive_values"], [])
        self.assertEqual(result["content_class"], "CONCERN_OR_ATTRIBUTED_CLAIM")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_policy_forecast_is_held_until_observed(self):
        result = self.signals(
            "서울시는 세출 1,780억 원을 조정하고 세외수입 1,994억 원을 확보해 "
            "채무비율이 20.94%에서 19.06%로 낮아질 전망입니다"
        )
        self.assertEqual(result["content_class"], "POLICY_FORECAST")
        self.assertEqual(result["precheck_status"], "HOLD")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_unrelated_number_in_next_sentence_cannot_anchor_issue_mention(self):
        result = self.signals(
            "삼성역 철근 누락 사고입니다. 별도 추경 예산은 100억 원입니다"
        )
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_real_waiting_time_survives_nearby_speaking_time_cleanup(self):
        result = self.signals(
            "장애인콜택시 이용자는 대기시간 120분으로 불편을 겪습니다. "
            "남은 발언시간은 12분입니다"
        )
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")
        self.assertIn("120분", result["substantive_values"])
        self.assertNotIn("12분", result["substantive_values"])

    def test_reported_unpaid_interest_is_attributed_and_gets_specific_question(self):
        text = (
            "현재 미지급 통상임금이 약 2,900억 원이고 "
            "지연이자는 하루 약 1억 4,000만 원씩 늘어난다고 합니다"
        )
        result = self.signals(text)
        self.assertEqual(result["claim_status"], "ATTRIBUTED_CLAIM")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertIn("산정 근거", payload["question"])
        self.assertIn("최종 비용 부담자", payload["question"])

    def test_reported_climate_card_loss_gets_specific_question(self):
        text = (
            "기후동행카드 손실금 중 50%만 보전하고 나머지 50%는 공사에 전가했다는 "
            "얘기를 들었어요"
        )
        result = self.signals(text)
        self.assertEqual(result["claim_status"], "ATTRIBUTED_CLAIM")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertIn("부담 배분", payload["question"])
        self.assertIn("계약·협의", payload["question"])

    def test_sliding_context_overlap_is_deduplicated(self):
        left = {
            "text": "전세사기 피해가구 보증금 미반환 임차인 지원 지연 원자료 확인",
        }
        right = {
            "text": "보증금 미반환 임차인 지원 지연 원자료 확인 추가 검증",
        }
        self.assertTrue(scout.near_duplicate_context(left, right))

    def test_activity_dashboard_uses_baseline_lane_not_review_card(self):
        row = {
            "source_id": "eungdapso",
            "source_name": "서울시 응답소",
            "score": 4,
            "qualified": False,
            "grounding_status": "HOLD",
            "precheck_status": "HOLD",
            "content_class": "AGGREGATE_ACTIVITY_DASHBOARD",
            "evidence_anchor": "NONE",
            "text": "민원 현황판 오늘 4,714건 · 월별 민원접수 건수",
            "url": "https://eungdapso.seoul.go.kr/main.do",
        }

        class FakeModule:
            @staticmethod
            def run_source(source):
                metric = {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "http_ok": True, "status": 200, "status_detail": "OK",
                    "requests": 1, "failed_requests": 0, "extracted": 1,
                    "precheck_pass": 0, "grounded": 0, "qualified": 0,
                }
                return metric, [row]

        FakeModule.SOURCES = [{
            "id": "eungdapso", "name": "서울시 응답소",
            "role": "DISCOVERY", "local": True, "voice": True,
        }]
        built = feed.build_feed(FakeModule)
        self.assertEqual(len(built["activity_baselines"]), 1)
        self.assertEqual(built["auxiliary_discovery"], [])
        self.assertEqual(built["held_for_source_detail"], [])

    def test_decimal_measurement_stays_in_one_evidence_segment(self):
        result = self.signals("서울 침수 피해율은 3.5%로 증가했습니다")
        self.assertIn("3.5%", result["substantive_values"])
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")

    def test_partial_district_extent_remains_a_measurement(self):
        result = self.signals("서울 3개 자치구에서 침수 피해 100건이 발생했습니다")
        self.assertIn("3개", result["substantive_values"])
        self.assertIn("100건", result["substantive_values"])
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")

    def test_two_thirds_sliding_window_overlap_is_duplicate(self):
        left = {"text": "전세사기 보증금 피해 임차인 지원 지연 확인"}
        right = {"text": "보증금 피해 임차인 지원 지연 확인 대책"}
        self.assertTrue(scout.near_duplicate_context(left, right))

    def test_dataset_title_is_metadata_lead_not_verification_asset(self):
        result = self.signals(
            "복지 · 서울시 장애인 버스요금 환급지급 인원수 · 공공데이터",
            self.open_data,
            "LINK_LABEL",
        )
        self.assertTrue(result["verification_metadata_lead"])
        self.assertFalse(result["verification_usable"])

    def test_final_briefing_labels_baseline_and_metadata_lead(self):
        feed_payload = {
            "core_discovery": [],
            "auxiliary_discovery": [],
            "activity_baselines": [{
                "text": "민원 현황판 오늘 4,714건",
                "url": "https://eungdapso.seoul.go.kr/main.do",
            }],
            "verification_metadata_leads": [{
                "text": "서울시 장애인 버스요금 환급지급 인원수",
                "url": "https://data.seoul.go.kr/example",
            }],
            "verification_schema_leads": [{
                "text": "서울 대기오염 측정정보를 1시간평균으로 제공합니다",
                "url": "https://data.seoul.go.kr/schema",
            }],
            "verification_map": [],
        }
        rendered = inject.render(feed_payload, {})
        self.assertIn("활동량 기준선 — 후보 아님", rendered)
        self.assertIn("전일·전월 누적 비교 전", rendered)
        self.assertIn("데이터셋 후보 — 스키마·값 미확인", rendered)
        self.assertIn("데이터 구조 확인 — 실제 값 미수집", rendered)
        self.assertIn("검증 자산 사용 금지", rendered)

    def test_protest_end_is_not_service_interruption(self):
        result = self.signals(
            "12대 서울시의회 개원 후 지난 4년 8개월 동안 이어진 "
            "장애인 지하철 탑승 시위가 중단을 선언했습니다"
        )
        self.assertNotIn("12대", result["substantive_values"])
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_operational_service_interruption_remains_a_problem(self):
        result = self.signals("서울 지하철 운행이 3시간 중단돼 시민이 불편을 겪었습니다")
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")

    def test_same_climate_card_loss_topic_is_deduplicated(self):
        left = {
            "text": "기후동행카드 손실금 50%를 교통공사에 전가했고 운영 예산은 3,580억입니다",
        }
        right = {
            "text": "교통공사 부채를 드러내지 않도록 손실금을 전가했고 재정 40%를 확보했습니다",
        }
        self.assertTrue(scout.near_duplicate_context(left, right))

    def test_council_opinion_marker_keeps_claim_attributed(self):
        text = (
            "저는 이 사업이 빚잔치로 마감된다고 생각합니다. "
            "기후동행카드 손실금 50%를 교통공사에 전가했습니다"
        )
        result = self.signals(text)
        self.assertEqual(result["claim_status"], "ATTRIBUTED_CLAIM")

    def test_citywide_observed_extent_keeps_full_district_count(self):
        result = self.signals(
            "서울 25개 자치구 전체에서 침수 피해가 발생했다고 확인됐습니다"
        )
        self.assertIn("25개", result["substantive_values"])
        self.assertEqual(result["evidence_anchor"], "MEASURED_PROBLEM_SIGNAL")

    def test_schema_description_is_not_an_actual_verification_asset(self):
        result = self.signals(
            "서울 대기오염물질 측정정보를 1시간평균으로 보정해 매시 5분에 "
            "각 자치구 측정소에서 제공합니다",
            self.open_data,
            "PAGE_CHUNK",
        )
        self.assertTrue(result["verification_schema_lead"])
        self.assertFalse(result["verification_usable"])

    def test_data_row_with_observed_value_can_be_verification_asset(self):
        result = self.signals(
            "서울 자치구별 대기오염 측정값이 실제 값 37건으로 확인됐습니다",
            self.open_data,
            "DATA_ROW",
        )
        self.assertTrue(result["verification_usable"])
        self.assertFalse(result["verification_schema_lead"])

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


    def test_generic_increase_is_neutral_structure_not_problem(self):
        text = "서울 공공도서관 이용자가 30% 증가했습니다"
        score, reasons, _, result = scout.score_text(text, self.council)
        self.assertFalse(result["problem"])
        self.assertEqual(result["change_direction"], "UNCLASSIFIED_CHANGE")
        self.assertEqual(result["evidence_anchor"], "DECOMPOSABLE_STRUCTURE")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertEqual(payload["grounding_status"], "PASS")
        self.assertIn("증감", payload["question"])
        self.assertNotIn("문제 징후", payload["question"])
        self.assertNotIn("문제·변화", reasons)
        self.assertGreaterEqual(score, 6)

    def test_generic_decrease_is_not_automatically_harm(self):
        text = "서울 인구는 비교 기간에 5% 감소했습니다"
        result = self.signals(text)
        self.assertFalse(result["problem"])
        self.assertEqual(result["change_direction"], "UNCLASSIFIED_CHANGE")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertNotIn("문제 징후", payload["question"])

    def test_comparison_word_and_duration_do_not_turn_budget_plan_into_result(self):
        text = "3개월 페이백은 전년도부터 계획해 2026년 본예산에 반영할 예정입니다"
        result = self.signals(text)
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_bigdata_schema_description_is_held_not_grounded_as_result(self):
        bigdata = {
            "id": "seoul_bigdata",
            "name": "서울 빅데이터캠퍼스",
            "local": True,
            "voice": False,
            "role": "VERIFICATION",
        }
        text = "서울 생활이동 데이터는 자치구별 1시간 단위로 갱신됩니다"
        score, reasons, _, result = scout.score_text(text, bigdata)
        self.assertTrue(result["verification_schema_lead"])
        self.assertFalse(result["verification_usable"])
        payload = scout.build_question_payload(text, "seoul_bigdata", result)
        self.assertEqual(payload["grounding_status"], "HOLD")
        self.assertIn("실제 값 확보 전", payload["question"])
        self.assertIn("데이터 구조·갱신 설명", reasons)
        self.assertNotIn("실제 수치·관찰근거", reasons)
        self.assertGreater(score, 0)

    def test_citywide_observed_extent_is_preserved_in_both_word_orders(self):
        first = self.signals("서울 25개 자치구 전체에서 침수 피해가 발생했습니다")
        second = self.signals("침수 피해가 서울 25개 자치구 모두에서 발생했습니다")
        self.assertIn("25개", first["substantive_values"])
        self.assertIn("25개", second["substantive_values"])

    def test_core_selection_dedupes_same_issue_across_different_urls(self):
        rows = [
            {
                "score": 10,
                "text": "서울 통상임금 미지급 2,900억 원과 하루 지연이자 1.4억 원이 발생했다",
                "url": "https://example.test/minutes/1",
            },
            {
                "score": 9,
                "text": "서울 통상임금 미지급 2,953억 원, 지연이자는 하루 1.4억 원이라는 지적",
                "url": "https://example.test/minutes/2",
            },
            {
                "score": 8,
                "text": "서울 전세사기 피해 1조 원이 자치구별로 집계됐다",
                "url": "https://example.test/minutes/3",
            },
        ]
        selected = feed.unique_top(
            rows,
            3,
            near_duplicate=scout.near_duplicate_context,
        )
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["url"], "https://example.test/minutes/1")
        self.assertEqual(selected[1]["url"], "https://example.test/minutes/3")


    def test_static_statistical_table_emits_multiple_real_data_rows(self):
        html = """
        <table>
          <tr><th>자치구</th><th>피해건수(건)</th></tr>
          <tr><td>강남구</td><td>37</td></tr>
          <tr><td>관악구</td><td>52</td></tr>
        </table>
        """
        parser = scout.parse_html(html)
        rows = scout.extract_records(
            parser,
            "https://data.seoul.go.kr/example",
            self.open_data,
            include_windows=False,
        )
        data_rows = [row for row in rows if row["record_kind"] == "DATA_ROW"]
        self.assertEqual(len(data_rows), 2)
        self.assertTrue(all(row["verification_usable"] for row in data_rows))
        self.assertTrue(all(row["grounding_status"] == "PASS" for row in data_rows))
        self.assertIn("피해건수(건): 37", data_rows[0]["text"] + data_rows[1]["text"])

    def test_table_header_without_body_emits_no_data_row(self):
        parser = scout.parse_html(
            "<table><tr><th>자치구</th><th>피해건수(건)</th></tr></table>"
        )
        self.assertEqual(scout.static_verification_rows(parser), [])

    def test_file_metadata_table_is_not_promoted_to_data_rows(self):
        parser = scout.parse_html(
            "<table><tr><th>구분</th><th>파일명</th><th>용량</th>"
            "<th>수정일</th><th>내려받기</th></tr>"
            "<tr><td>원본</td><td>x.csv</td><td>35.8</td>"
            "<td>2026-09-14</td><td>다운로드</td></tr></table>"
        )
        self.assertEqual(scout.static_verification_rows(parser), [])

    def test_mixed_key_value_metadata_table_is_not_data_row(self):
        parser = scout.parse_html(
            "<table><tr><th>공개일자</th><td>2026-09-14</td>"
            "<th>갱신일</th><td>매일</td></tr></table>"
        )
        self.assertEqual(scout.static_verification_rows(parser), [])

    def test_fake_data_row_label_cannot_promote_file_size(self):
        result = self.signals(
            "파일명: x.csv · 용량(MB): 35.8",
            self.open_data,
            "DATA_ROW",
        )
        self.assertFalse(result["verification_usable"])

    def test_run_source_keeps_two_real_rows_from_same_url(self):
        html = (
            "<table><tr><th>자치구</th><th>피해건수(건)</th></tr>"
            "<tr><td>강남구</td><td>37</td></tr>"
            "<tr><td>관악구</td><td>52</td></tr></table>"
        )
        original_fetch = scout.fetch
        scout.fetch = lambda url, timeout=22: scout.FetchResult(
            url=url,
            ok=True,
            status=200,
            elapsed_ms=1,
            byte_count=len(html.encode("utf-8")),
            text=html,
        )
        source = {
            **self.open_data,
            "url": "https://data.seoul.go.kr/example",
            "follow": "",
            "max_follow": 0,
            "cadence": "daily",
        }
        try:
            metric, rows = scout.run_source(source)
        finally:
            scout.fetch = original_fetch
        data_rows = [row for row in rows if row["record_kind"] == "DATA_ROW"]
        self.assertEqual(len(data_rows), 2)
        self.assertEqual(metric["verification_usable"], 2)

    def test_budget_adjustment_word_is_not_observed_change(self):
        text = (
            "교육 예산안 총규모는 12조 8,665억 원이며 총규모 변동 없이 "
            "사업별 증감 조정을 거쳐 2026년 본예산에 반영할 예정입니다"
        )
        result = self.signals(text)
        self.assertNotEqual(result["change_direction"], "UNCLASSIFIED_CHANGE")
        self.assertEqual(result["evidence_anchor"], "NONE")

    def test_attributed_change_question_keeps_claim_status_visible(self):
        text = "협회 추산 서울 공공도서관 이용자가 30% 증가했습니다"
        result = self.signals(text)
        self.assertEqual(result["claim_status"], "ATTRIBUTED_CLAIM")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertIn("증감 주장", payload["question"])
        self.assertNotIn("확인된 증감", payload["question"])


    def test_time_axis_schema_is_not_citizen_loss(self):
        _, reasons, _, result = scout.score_text(
            "서울 대기오염 측정정보는 1시간평균과 시간대별 값으로 제공합니다",
            self.open_data,
        )
        self.assertFalse(result["loss"])
        self.assertNotIn("시민 손실", reasons)

    def test_safety_consideration_in_budget_is_not_citizen_loss(self):
        _, reasons, _, result = scout.score_text(
            "서울 교육 예산은 학생의 안전 등을 고려해 100억 원을 편성할 예정입니다",
            self.council,
        )
        self.assertFalse(result["loss"])
        self.assertNotIn("시민 손실", reasons)


    def test_measured_waiting_time_remains_citizen_loss(self):
        _, reasons, _, result = scout.score_text(
            "서울 시민이 진료 전에 평균 3시간 대기했습니다",
            self.council,
        )
        self.assertTrue(result["problem"])
        self.assertTrue(result["loss"])
        self.assertIn("시민 손실", reasons)


    def test_off_session_both_source_can_enter_daily_review_cards(self):
        row = {
            "source_id": "seoul_research",
            "source_name": "서울연구원",
            "score": 8,
            "qualified": True,
            "grounding_status": "PASS",
            "precheck_status": "PASS",
            "content_class": "REPORTABLE_TEXT",
            "verification_usable": False,
            "verification_metadata_lead": False,
            "verification_schema_lead": False,
            "evidence_anchor": "DECOMPOSABLE_STRUCTURE",
            "claim_status": "OBSERVED_OR_PUBLISHED",
            "question_basis": "서울 자치구별 돌봄 공백 120건이 집계됐습니다",
            "text": "서울 자치구별 돌봄 공백 120건이 집계됐습니다",
            "question": "어느 자치구와 대상에 집중됐는가?",
            "verification_axes": ["자치구", "대상"],
            "freshness_status": "FRESH",
            "url": "https://example.test/research/1",
        }

        class FakeModule:
            SOURCES = [{
                "id": "seoul_research",
                "name": "서울연구원",
                "role": "BOTH",
            }]

            @staticmethod
            def run_source(source):
                metric = {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "status": 200, "requests": 1, "extracted": 1,
                    "precheck_pass": 1, "grounded": 1, "qualified": 1,
                }
                return metric, [row]

            @staticmethod
            def near_duplicate_context(left, right):
                return False

        built = feed.build_feed(FakeModule)
        self.assertEqual(built["core_discovery"], [])
        self.assertEqual(len(built["auxiliary_discovery"]), 1)
        self.assertEqual(
            built["auxiliary_discovery"][0]["source_id"],
            "seoul_research",
        )


    def test_injected_auxiliary_card_shows_its_actual_source(self):
        payload = {
            "core_discovery": [],
            "auxiliary_discovery": [{
                "source_id": "seoul_research",
                "source_name": "서울연구원 정책·연구 자료",
                "text": "서울 돌봄 공백 120건",
                "evidence_anchor": "MEASURED_PROBLEM_SIGNAL",
                "question": "어디에 집중됐는가?",
                "url": "https://example.test/research",
            }],
            "activity_baselines": [],
            "verification_metadata_leads": [],
            "verification_schema_leads": [],
            "verification_map": [],
        }
        rendered = inject.render(payload, {})
        self.assertIn("### 보완 발굴원", rendered)
        self.assertIn("출처: 서울연구원 정책·연구 자료", rendered)
        self.assertNotIn("보조 발굴원 — 서울시 응답소", rendered)


    def test_generic_axis_and_total_table_is_not_a_data_row(self):
        parser = scout.parse_html(
            "<table><tr><th>자치구</th><th>합계</th></tr>"
            "<tr><td>강남구</td><td>37</td></tr></table>"
        )
        self.assertEqual(scout.static_verification_rows(parser), [])

    def test_unattributed_council_number_stays_attributed(self):
        text = "서울 전세사기 피해 11,664가구가 발생했습니다"
        result = self.signals(text)
        self.assertEqual(result["claim_status"], "ATTRIBUTED_CLAIM")
        payload = scout.build_question_payload(text, "council_minutes", result)
        self.assertIn("제시된 피해 규모", payload["question"])
        self.assertIn("원자료로 재현", payload["question"])

    def test_official_council_citation_can_be_published_fact(self):
        text = "서울시 공식 집계에 따르면 서울 전세사기 피해 11,664가구가 발생했습니다"
        result = self.signals(text)
        self.assertEqual(result["claim_status"], "OBSERVED_OR_PUBLISHED")

    def test_freshness_policy_boundaries(self):
        today = scout.date(2026, 9, 14)
        event = {"cadence": "event_driven"}
        self.assertEqual(
            scout.freshness_metadata(event, "2026-08-31", today=today)["freshness_status"],
            "FRESH",
        )
        self.assertEqual(
            scout.freshness_metadata(event, "2026-08-30", today=today)["freshness_status"],
            "STALE_CARRYOVER",
        )
        self.assertEqual(
            scout.freshness_metadata(event, "2026-08-16", today=today)["freshness_status"],
            "ARCHIVED_STALE",
        )
        monthly = {"cadence": "monthly"}
        self.assertEqual(
            scout.freshness_metadata(monthly, "2026-07-31", today=today)["freshness_status"],
            "FRESH",
        )
        self.assertEqual(
            scout.freshness_metadata(monthly, "2026-07-30", today=today)["freshness_status"],
            "STALE_CARRYOVER",
        )

    def test_month_only_date_uses_end_of_reporting_month(self):
        original_today = scout.TODAY
        scout.TODAY = scout.date(2026, 9, 14)
        try:
            self.assertEqual(scout.latest_date_from(["2026.7월 지역별 체불 현황"]), "2026-07-31")
            self.assertEqual(scout.latest_date_from(["'26.7월 지역별 체불 현황"]), "2026-07-31")
        finally:
            scout.TODAY = original_today



    def test_labor_wide_region_table_emits_seoul_vs_national_fact(self):
        html = (
            "<h3>'26.7월 지역별(17개 시도) 체불 현황</h3>"
            "<table><tr><th>전체</th><th>서울</th><th>부산</th><th>대구</th>"
            "<th>인천</th></tr><tr><td>10,814</td><td>2,186</td><td>648</td>"
            "<td>386</td><td>516</td></tr></table>"
        )
        parser = scout.parse_html(html)
        rows = scout.labor_region_rows(parser)
        self.assertEqual(len(rows), 1)
        self.assertIn("지역: 서울", rows[0])
        self.assertIn("체불액(억 원): 2,186", rows[0])
        self.assertIn("전국 체불액(억 원): 10,814", rows[0])
        self.assertIn("기준월: 2026-07", rows[0])
        result = self.signals(rows[0], self.labor, "DATA_ROW")
        payload = scout.build_question_payload(rows[0], "labor_arrears", result)
        self.assertEqual(payload["grounding_status"], "PASS")
        self.assertIn("임금총액·근로자 비중", payload["question"])
        self.assertIn("자치구·업종·사업장 규모", payload["question"])

    def test_labor_actual_table_row_becomes_fresh_localization_lead(self):
        html = (
            "<table><tr><th>구분</th><th>체불 금액(억 원)</th>"
            "<th>체불 피해노동자 수(명)</th></tr>"
            "<tr><td>'26.7월</td><td>10,814</td><td>128,048</td></tr></table>"
        )
        parser = scout.parse_html(html)
        rows = scout.extract_records(
            parser,
            "https://labor.moel.go.kr/arrstat/sttcStusList.do",
            {**self.labor, "cadence": "monthly"},
            include_windows=False,
        )
        data_rows = [row for row in rows if row["record_kind"] == "DATA_ROW"]
        self.assertEqual(len(data_rows), 1)
        self.assertTrue(data_rows[0]["localization_lead"])

    def test_source_retry_can_recover_without_hiding_first_failure(self):
        html = "<html><body>2026-09-14 수집 정상</body></html>"
        attempts = []
        original_fetch = scout.fetch

        def fake_fetch(url, timeout=22):
            attempts.append(timeout)
            if len(attempts) == 1:
                return scout.FetchResult(url, False, 0, 1, 0, "", "TimeoutError")
            return scout.FetchResult(url, True, 200, 1, len(html), html)

        scout.fetch = fake_fetch
        source = {
            "id": "seoul_research",
            "name": "서울연구원",
            "url": "https://example.test/source",
            "role": "BOTH",
            "local": True,
            "voice": False,
            "follow": "",
            "max_follow": 0,
            "cadence": "monthly",
            "timeout": 45,
            "retry": 1,
        }
        try:
            metric, _ = scout.run_source(source)
        finally:
            scout.fetch = original_fetch
        self.assertTrue(metric["http_ok"])
        self.assertEqual(metric["requests"], 2)
        self.assertEqual(metric["failed_requests"], 1)
        self.assertEqual(attempts, [45, 45])

    def test_feed_separates_fresh_stale_and_unknown_candidates(self):
        base = {
            "source_id": "council_minutes",
            "source_name": "서울시의회 회의록",
            "score": 9,
            "qualified": True,
            "localization_lead": False,
            "grounding_status": "PASS",
            "precheck_status": "PASS",
            "content_class": "REPORTABLE_TEXT",
            "verification_usable": False,
            "verification_metadata_lead": False,
            "verification_schema_lead": False,
            "evidence_anchor": "MEASURED_PROBLEM_SIGNAL",
            "claim_status": "ATTRIBUTED_CLAIM",
            "question": "원자료로 재현되는가?",
            "verification_axes": ["자치구"],
        }
        rows = [
            {**base, "text": "서울 피해 37건 발생", "question_basis": "서울 피해 37건 발생",
             "url": "https://example.test/fresh", "freshness_status": "FRESH",
             "source_date": "2026-09-13", "freshness_days": 1, "freshness_window_days": 14},
            {**base, "text": "서울 피해 52건 발생", "question_basis": "서울 피해 52건 발생",
             "url": "https://example.test/stale", "freshness_status": "STALE_CARRYOVER",
             "source_date": "2026-08-25", "freshness_days": 20, "freshness_window_days": 14},
            {**base, "text": "서울 피해 61건 발생", "question_basis": "서울 피해 61건 발생",
             "url": "https://example.test/unknown", "freshness_status": "FRESHNESS_UNKNOWN",
             "source_date": "", "freshness_days": None, "freshness_window_days": 14},
        ]

        class FakeModule:
            SOURCES = [{"id": "council_minutes", "name": "서울시의회 회의록", "role": "BOTH"}]
            FRESHNESS_POLICY_DAYS = {"event_driven": (14, 28)}

            @staticmethod
            def run_source(source):
                metric = {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "status": 200, "requests": 1, "extracted": 3,
                    "precheck_pass": 3, "grounded": 3, "qualified": 3,
                }
                return metric, rows

            @staticmethod
            def near_duplicate_context(left, right):
                return False

        built = feed.build_feed(FakeModule)
        self.assertEqual(len(built["core_discovery"]), 1)
        self.assertEqual(built["core_discovery"][0]["url"], "https://example.test/fresh")
        self.assertEqual(len(built["stale_carryover"]), 1)
        self.assertEqual(len(built["freshness_holds"]), 1)
        self.assertEqual(built["funnel"]["selected_discovery"], 1)

        repeated = feed.build_feed(
            FakeModule, {feed.source_revision_for_row(rows[0])}
        )
        self.assertEqual(repeated["core_discovery"], [])
        self.assertEqual(len(repeated["rediscovered_carryover"]), 1)
        self.assertEqual(repeated["funnel"]["selected_discovery"], 0)

    def test_national_lead_enters_localization_lane_not_editorial_card(self):
        row = {
            "source_id": "labor_arrears", "source_name": "고용노동부 임금체불 통계",
            "score": 8, "qualified": False, "localization_lead": True,
            "grounding_status": "PASS", "precheck_status": "PASS",
            "content_class": "REPORTABLE_TEXT", "verification_usable": False,
            "verification_metadata_lead": False, "verification_schema_lead": False,
            "evidence_anchor": "MEASURED_PROBLEM_SIGNAL", "claim_status": "OBSERVED_OR_PUBLISHED",
            "question_basis": "전국 임금체불액 1조 원", "text": "전국 임금체불액 1조 원",
            "question": "기존 질문", "verification_axes": ["지역"], "url": "https://example.test/labor",
            "freshness_status": "FRESH", "source_date": "2026-08-31",
        }

        class FakeModule:
            SOURCES = [{"id": "labor_arrears", "name": "고용노동부", "role": "BOTH"}]

            @staticmethod
            def run_source(source):
                return {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "status": 200, "requests": 1, "extracted": 1,
                    "precheck_pass": 1, "grounded": 1, "qualified": 0,
                }, [row]

        built = feed.build_feed(FakeModule)
        self.assertEqual(len(built["localization_discovery"]), 1)
        self.assertEqual(built["core_discovery"], [])
        self.assertEqual(built["auxiliary_discovery"], [])
        self.assertIn("서울에서도 확인", built["localization_discovery"][0]["question"])

    def test_final_briefing_exposes_source_failure_and_stale_exclusion(self):
        payload = {
            "core_discovery": [],
            "auxiliary_discovery": [],
            "localization_discovery": [],
            "stale_carryover": [{
                "text": "오래된 서울 피해 37건",
                "question_basis": "오래된 서울 피해 37건",
                "source_date": "2026-08-20",
                "freshness_days": 25,
            }],
            "freshness_holds": [],
            "metrics": [{
                "id": "consumer_agency",
                "name": "한국소비자원 피해·분쟁 자료",
                "http_ok": False,
                "status_detail": "FETCH_FAILED",
                "error": "certificate verify failed",
            }],
            "activity_baselines": [],
            "verification_metadata_leads": [],
            "verification_schema_leads": [],
            "verification_map": [],
        }
        rendered = inject.render(payload, {})
        self.assertIn("소스 연결·본문 상태", rendered)
        self.assertIn("certificate verify failed", rendered)
        self.assertIn("STALE_CARRYOVER — 오늘 후보 제외", rendered)
        self.assertIn("오늘 카드·재활성화·S0 제안 제외", rendered)


    def test_current_month_period_is_clamped_to_today(self):
        original_today = scout.TODAY
        scout.TODAY = scout.date(2026, 9, 14)
        try:
            self.assertEqual(
                scout.latest_date_from(["'26.9월 지역별 체불 현황"]),
                "2026-09-14",
            )
            self.assertEqual(
                scout.latest_period_label(["'26.9월 지역별 체불 현황"]),
                "2026-09",
            )
        finally:
            scout.TODAY = original_today

    def test_document_date_is_separate_from_cited_reference_period(self):
        html = (
            '<meta property="article:published_time" content="2026-09-14T08:00:00+09:00">'
            "<p>서울에서 2024-01-31 기준 피해 37건이 발생했습니다.</p>"
        )
        original_fetch = scout.fetch

        def fake_fetch(url, timeout=22):
            return scout.FetchResult(url, True, 200, 1, len(html), html)

        scout.fetch = fake_fetch
        source = {
            **self.council,
            "url": "https://example.test/minutes",
            "follow": "",
            "max_follow": 0,
            "cadence": "event_driven",
        }
        try:
            _, rows = scout.run_source(source)
        finally:
            scout.fetch = original_fetch
        row = next(item for item in rows if "피해 37건" in item["text"])
        self.assertEqual(row["document_date"], "2026-09-14")
        self.assertEqual(row["reference_period"], "2024-01-31")
        self.assertEqual(row["source_date"], "2026-09-14")
        self.assertEqual(row["freshness_basis"], "document_date")
        self.assertEqual(row["freshness_status"], "FRESH")

    def test_national_mentions_do_not_masquerade_as_seoul_observations(self):
        self.assertFalse(scout.direct_seoul_scope("수도권 피해 1,000건이 발생했습니다"))
        self.assertFalse(
            scout.direct_seoul_scope("서울 등 전국에서 피해 1,000건이 발생했습니다")
        )
        self.assertFalse(
            scout.direct_seoul_scope("전국 피해 100건, 서울에서 설명회 개최")
        )
        self.assertTrue(
            scout.direct_seoul_scope("지역: 서울 · 체불액(억 원): 2,186")
        )
        _, _, seoul_scope, _ = scout.score_text(
            "전국에서 체불 피해 10,814억 원이 발생했습니다",
            {**self.research, "scope_requires_content": True},
        )
        self.assertFalse(seoul_scope)

    def test_revision_uses_full_text_but_ignores_date_only_changes(self):
        common = "서울 피해 " + ("가" * 600)
        first = {
            "source_id": "council_minutes",
            "url": "https://example.test/item",
            "text": common + " A",
            "source_date": "2026-09-13",
        }
        changed_after_500 = {**first, "text": common + " B"}
        date_only = {**first, "source_date": "2026-09-14"}
        self.assertNotEqual(
            feed.source_revision_for_row(first),
            feed.source_revision_for_row(changed_after_500),
        )
        self.assertEqual(
            feed.source_revision_for_row(first),
            feed.source_revision_for_row(date_only),
        )

    def test_missing_freshness_fails_closed_into_date_hold(self):
        row = {
            "source_id": "council_minutes",
            "source_name": "서울시의회 회의록",
            "score": 9,
            "qualified": True,
            "localization_lead": False,
            "grounding_status": "PASS",
            "precheck_status": "PASS",
            "content_class": "REPORTABLE_TEXT",
            "verification_usable": False,
            "verification_metadata_lead": False,
            "verification_schema_lead": False,
            "evidence_anchor": "MEASURED_PROBLEM_SIGNAL",
            "claim_status": "ATTRIBUTED_CLAIM",
            "question_basis": "서울 피해 37건",
            "text": "서울 피해 37건",
            "question": "원자료로 재현되는가?",
            "verification_axes": ["자치구"],
            "url": "https://example.test/missing-date",
        }

        class FakeModule:
            SOURCES = [{"id": "council_minutes", "name": "서울시의회", "role": "BOTH"}]
            FRESHNESS_POLICY_DAYS = {"event_driven": (14, 28)}

            @staticmethod
            def run_source(source):
                return {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "status": 200, "requests": 1, "extracted": 1,
                    "precheck_pass": 1, "grounded": 1, "qualified": 1,
                }, [row]

        built = feed.build_feed(FakeModule)
        self.assertEqual(built["core_discovery"], [])
        self.assertEqual(len(built["freshness_holds"]), 1)

    def test_localization_revision_is_remembered_and_then_rediscovered(self):
        row = {
            "source_id": "labor_arrears",
            "source_name": "고용노동부 임금체불 통계",
            "score": 8,
            "qualified": False,
            "localization_lead": True,
            "grounding_status": "PASS",
            "precheck_status": "PASS",
            "precheck_reason": "",
            "content_class": "REPORTABLE_TEXT",
            "verification_usable": False,
            "verification_metadata_lead": False,
            "verification_schema_lead": False,
            "evidence_anchor": "MEASURED_PROBLEM_SIGNAL",
            "claim_status": "OBSERVED_OR_PUBLISHED",
            "question_basis": "전국 임금체불액 1조 원",
            "text": "전국 임금체불액 1조 원",
            "question": "기존 질문",
            "verification_axes": ["지역"],
            "url": "https://example.test/labor",
            "freshness_status": "FRESH",
            "source_date": "2026-08-31",
            "freshness_days": 14,
            "freshness_window_days": 45,
            "cadence": "monthly",
        }

        class FakeModule:
            SOURCES = [{"id": "labor_arrears", "name": "고용노동부", "role": "BOTH"}]
            FRESHNESS_POLICY_DAYS = {"monthly": (45, 90)}

            @staticmethod
            def run_source(source):
                return {
                    "id": source["id"], "name": source["name"], "role": source["role"],
                    "status": 200, "requests": 1, "extracted": 1,
                    "precheck_pass": 1, "grounded": 1, "qualified": 0,
                }, [row]

        original_queue = feed.QUEUE
        with tempfile.TemporaryDirectory() as tmp:
            feed.QUEUE = Path(tmp) / "queue.csv"
            try:
                first = feed.build_feed(FakeModule)
                self.assertEqual(len(first["localization_discovery"]), 1)
                feed.update_review_queue(first)
                saved = feed.read_review_queue()
                self.assertEqual(saved[0]["auto_active_today"], "false")
                prior = set()
                for saved_row in saved:
                    prior.update(feed.revision_history_values(saved_row))
                second = feed.build_feed(FakeModule, prior)
            finally:
                feed.QUEUE = original_queue
        self.assertEqual(second["localization_discovery"], [])
        self.assertEqual(len(second["rediscovered_carryover"]), 1)


if __name__ == "__main__":
    unittest.main()
