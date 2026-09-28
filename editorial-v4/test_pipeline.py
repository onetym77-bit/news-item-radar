import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("editorial_pipeline", Path(__file__).with_name("pipeline.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

BASE = {"id": "one", "family": "서울시의회", "source": "서울시의회 회의록",
        "headline": "새 사업의 접근성", "url": "https://example.org/1",
        "evidence_text": "이 사업을 새로 시작하면서 대상별 접근 방식이 달라졌습니다.",
        "date": "2026-09-22", "claim_status": "의원 발언·미검증"}
GOOD = {"id": "one", "verdict": "PROPOSE", "issue_key": "접근 방식",
        "title": "새 사업의 이용 경로는 누구에게 열리는가",
        "subject": "대상에 따라 서로 다른 접근 경로가 있는 서울 신규 사업",
        "why_now": "새 사업이 시작돼 이용 경로를 선택해야 하는 시점이다",
        "citizen_question": "지원 대상마다 어디서 신청하고 무엇을 포기해야 하는가?",
        "uncommon_question": "같은 자격인데 신청 경로에 따라 실제 이용 가능성이 달라지는가?",
        "first_check": "공식 접수 기준과 접수·탈락 사례를 나란히 확인한다",
        "counterhypothesis": "경로는 달라도 실제 이용 자격과 처리 속도는 같을 수 있다",
        "scene_path": "신청 현장, 담당자, 두 경로의 이용자를 취재한다",
        "anchor_quote": "이 사업을 새로 시작하면서 대상별 접근 방식이 달라졌습니다.",
        "reason": "신청 방식의 차이가 이용 기회를 바꿀 수 있는지 확인할 가치가 있다"}


class PipelineTests(unittest.TestCase):
    def test_ungrounded_quote_is_held(self):
        bad = {**GOOD, "anchor_quote": "원문에 없는 피해가 확인됐다"}
        proposals, holds = module.assess_result([BASE], {"assessments": [bad]})
        self.assertEqual(proposals, [])
        self.assertEqual(holds[0]["reason"], "원문 인용 불일치")

    def test_generic_question_is_held(self):
        bad = {**GOOD, "citizen_question": "시민에게 어떤 영향이 있는가?"}
        proposals, _ = module.assess_result([BASE], {"assessments": [bad]})
        self.assertEqual(proposals, [])

    def test_single_source_and_issue_dedup(self):
        second = {**BASE, "id": "two", "url": "https://example.org/2"}
        other = {**GOOD, "id": "two", "title": "두 번째 다른 기획 제목이 있는가"}
        proposals, holds = module.assess_result([BASE, second], {"assessments": [GOOD, other]})
        self.assertEqual(len(proposals), 1)
        self.assertEqual(holds[0]["reason"], "같은 소스 계열 또는 사안 중복")

    def test_missing_assessment_fails_contract(self):
        with self.assertRaisesRegex(ValueError, "ID 누락"):
            module.assess_result([BASE], {"assessments": []})

    def test_duplicate_or_unknown_assessment_id_fails_contract(self):
        with self.assertRaisesRegex(ValueError, "ID 중복"):
            module.assess_result([BASE], {"assessments": [GOOD, GOOD]})
        with self.assertRaisesRegex(ValueError, "알 수 없는 ID"):
            module.assess_result([BASE], {"assessments": [{**GOOD, "id": "unknown"}]})

    def test_model_calls_bind_exact_ids_in_structured_schema(self):
        second = {**BASE, "id": "two", "url": "https://example.org/2"}
        with patch.object(module, "call_structured", return_value={"assessments": []}) as call:
            module.model_assess([BASE, second], [], "test-model", "test-key")
        data, schema = call.call_args.args[3], call.call_args.args[4]
        self.assertEqual(data["required_ids"], ["one", "two"])
        rows = schema["properties"]["assessments"]
        self.assertEqual(rows["items"]["properties"]["id"]["enum"], ["one", "two"])
        self.assertNotIn("enum", module.SCHEMA["properties"]["assessments"]["items"]["properties"]["id"])

        proposals = [GOOD, {**GOOD, "id": "two"}]
        with patch.object(module, "call_structured", return_value={"reviews": []}) as call:
            module.model_review([BASE, second], proposals, "test-model", "test-key")
        data, schema = call.call_args.args[3], call.call_args.args[4]
        self.assertEqual(data["required_ids"], ["one", "two"])
        rows = schema["properties"]["reviews"]
        self.assertEqual(rows["items"]["properties"]["id"]["enum"], ["one", "two"])

    def test_run_retries_incomplete_assessment_once(self):
        record = {
            **BASE,
            "context": "신규 사업의 신청 경로에 따라 시민의 실제 선택과 처리 순서가 달라지는지 확인합니다.",
            "issue_hint": "새 사업의 접근성",
        }
        review = {"reviews": [{
            "id": "one", "verdict": "KEEP",
            "editorial_risk": "신청 경로 차이가 실제 이용 결과와 무관할 수 있다",
            "decisive_test": "접수 기준과 실제 처리 기록을 같은 기간으로 대조한다",
            "reason": "서로 다른 설명을 가를 자료와 현장 취재 경로가 구체적이다",
        }]}
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(module, "source_inputs", return_value=([record], [])), \
                patch.object(module, "load_shadow_review_queues",
                             return_value={"items": [], "queues": [], "pending": 0}), \
                patch.object(module, "known_leads", return_value=[]), \
                patch.object(module, "reviewed_ids", return_value=set()), \
                patch.object(module, "model_assess",
                             side_effect=[{"assessments": []}, {"assessments": [GOOD]}]) as assess, \
                patch.object(module, "model_review", return_value=review), \
                patch.dict(module.os.environ, {"OPENAI_API_KEY": "test"}):
            result = module.run("test", output_path=Path(folder) / "latest.json")
        self.assertEqual(assess.call_count, 2)
        self.assertEqual(result["assessment_retries"], 1)
        self.assertEqual(result["model_calls"], 3)
        self.assertEqual(len(result["proposals"]), 1)

    def test_run_fails_after_second_incomplete_assessment(self):
        record = {
            **BASE,
            "context": "신규 사업의 신청 경로에 따라 시민의 실제 선택과 처리 순서가 달라지는지 확인합니다.",
            "issue_hint": "새 사업의 접근성",
        }
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(module, "source_inputs", return_value=([record], [])), \
                patch.object(module, "load_shadow_review_queues",
                             return_value={"items": [], "queues": [], "pending": 0}), \
                patch.object(module, "known_leads", return_value=[]), \
                patch.object(module, "reviewed_ids", return_value=set()), \
                patch.object(module, "model_assess",
                             side_effect=[{"assessments": []}, {"assessments": []}]) as assess, \
                patch.dict(module.os.environ, {"OPENAI_API_KEY": "test"}):
            with self.assertRaisesRegex(ValueError, "ID 누락"):
                module.run("test", output_path=Path(folder) / "latest.json")
        self.assertEqual(assess.call_count, 2)

    def test_prior_lead_requires_anchor_not_only_shared_url(self):
        lead = {"source_url": BASE["url"], "title": "수어통역센터 재정",
                "anchor_text": "수어통역센터는 자체수입이 발생해도"}
        self.assertEqual(module.excluded(BASE, [lead], set()), "")
        matched = {**BASE, "evidence_text": lead["anchor_text"] + " 서비스에 영향을 준다"}
        self.assertEqual(module.excluded(matched, [lead], set()), "기존 취재 착수 사안")

    def test_reviewed_id_is_skipped(self):
        self.assertEqual(module.excluded(BASE, [], {"one"}), "사람 판정 완료·보류")

    def test_recent_eligible_input_precedes_old_and_reviewed(self):
        rows = [
            {**BASE, "id": "old", "date": "2026-08-01"},
            {**BASE, "id": "reviewed", "date": "2026-09-21"},
            {**BASE, "id": "new", "date": "2026-09-20"},
        ]
        eligible = [row for row in rows if not module.excluded(row, [], {"reviewed"})]
        self.assertEqual([row["id"] for row in module.prioritize_inputs(eligible)], ["new", "old"])

    def test_future_document_date_is_not_current_evidence(self):
        from datetime import date
        self.assertTrue(module.future_dated({**BASE, "date": "2026-09-23"}, date(2026, 9, 22)))
        self.assertFalse(module.future_dated({**BASE, "date": "2026-09-22"}, date(2026, 9, 22)))
        self.assertFalse(module.future_dated({**BASE, "date": ""}, date(2026, 9, 22)))

    def test_independent_review_can_hold_without_filler(self):
        proposal = {**GOOD, "source": BASE["source"]}
        review = {"reviews": [{"id": "one", "verdict": "HOLD",
                              "editorial_risk": "문제의 존재를 확인하지 못했다",
                              "decisive_test": "실제 이용자를 먼저 찾아 확인한다",
                              "reason": "발언을 되풀이할 뿐 새로운 취재 질문이 없다"}]}
        kept, held = module.apply_second_review([proposal], review)
        self.assertEqual(kept, [])
        self.assertEqual(held[0]["verdict"], "HOLD")

    def test_independent_review_preserves_provisional_status(self):
        proposal = {**GOOD, "source": BASE["source"]}
        review = {"reviews": [{"id": "one", "verdict": "KEEP",
                              "editorial_risk": "사업 설명이 실제 이용 경로와 다를 수 있다",
                              "decisive_test": "두 경로 이용자와 접수 기준을 대조한다",
                              "reason": "선택의 차이를 취재할 수 있지만 사실은 미확인이다"}]}
        kept, held = module.apply_second_review([proposal], review)
        self.assertEqual(held, [])
        self.assertEqual(kept[0]["coverage_status"], "기존 보도 각도 별도 대조 필요")

    def test_independent_review_requires_exact_ids(self):
        with self.assertRaisesRegex(ValueError, "ID 불일치"):
            module.apply_second_review([{**GOOD, "source": BASE["source"]}], {"reviews": []})

    def test_district_shadow_accepts_only_reviewed_l3_cards(self):
        payload = {
            "schema": 1, "mode": "SEMANTIC_SHADOW", "source_count": 25,
            "results": [{
                "source_name": "서초구",
                "document_url": "https://example.org/district/1",
                "meeting_date": "2026-09-14",
                "semantic_status": "REVIEW",
                "verification_card": {
                    "anchor_quote": "장애인 활동지원 추가 지원 예산의 집행 잔액이 반복되고 있습니다.",
                    "observed_issue": "추가 지원 예산이 편성됐지만 집행 잔액이 반복되는 원인을 확인해야 합니다.",
                    "editorial_hypothesis": "활동지원 수요와 서비스 연결 사이에 공백이 있는가",
                    "citizen_stake_to_check": "지원 대기와 실제 서비스 이용 가능성",
                    "test_question": "잔액은 수요 부족인가 제공기관 연결 실패인가?",
                    "alternative_explanation": "일시적인 신청 감소나 정산 시점 차이일 수 있다",
                },
                "editorial_review": {"verdict": "VERIFY_FIRST"},
            }],
        }
        records, gaps = module.source_inputs(payload, only_district=True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["family"], "25개 자치구의회")
        self.assertEqual(records[0]["source"], "서초구의회 회의록")
        self.assertEqual(records[0]["source_stage"], "L3 그림자 검토")
        self.assertFalse(records[0]["production_eligible"])
        self.assertFalse(any(x["source"] == "25개 자치구의회" for x in gaps))

    def test_district_shadow_rejects_unreviewed_or_low_priority_cards(self):
        base = {
            "schema": 1, "mode": "SEMANTIC_SHADOW", "source_count": 25,
            "results": [{
                "source_name": "서초구",
                "document_url": "https://example.org/district/1",
                "meeting_date": "2026-09-14",
                "semantic_status": "REVIEW",
                "verification_card": {
                    "anchor_quote": "장애인 활동지원 추가 지원 예산의 집행 잔액이 반복되고 있습니다.",
                    "observed_issue": "추가 지원 예산이 편성됐지만 집행 잔액이 반복되는 원인을 확인해야 합니다.",
                },
                "editorial_review": {"verdict": "LOW_PRIORITY"},
            }],
        }
        records, gaps = module.source_inputs(base, only_district=True)
        self.assertEqual(records, [])
        self.assertTrue(any(x["source"] == "25개 자치구의회" for x in gaps))
        base["mode"] = "CONTEXT_ONLY"
        base["results"][0]["editorial_review"]["verdict"] = "PURSUE"
        records, _ = module.source_inputs(base, only_district=True)
        self.assertEqual(records, [])

    def test_district_shadow_never_becomes_final_proposal(self):
        production = {**GOOD, "source": "서울시의회 회의록",
                      "production_eligible": True}
        district = {**GOOD, "id": "district", "source": "서초구의회 회의록",
                    "family": "25개 자치구의회",
                    "source_stage": "L3 그림자 검토",
                    "production_eligible": False}
        final, shadow = module.partition_reviewed_proposals([production, district])
        self.assertEqual([x["id"] for x in final], ["one"])
        self.assertEqual([x["id"] for x in shadow], ["district"])
        self.assertEqual(shadow[0]["status"], "검증 전용·최종 후보 아님")
        self.assertEqual(shadow[0]["briefing_output"], "NONE")
        self.assertFalse(shadow[0]["production_eligible"])

    def test_live_district_run_writes_shadow_only(self):
        payload = {
            "schema": 1, "mode": "SEMANTIC_SHADOW", "source_count": 25,
            "results": [{
                "source_name": "서초구",
                "document_url": "https://example.org/district/live",
                "meeting_date": "2026-09-14",
                "semantic_status": "REVIEW",
                "verification_card": {
                    "anchor_quote": "장애인 활동지원 추가 지원 예산의 집행 잔액이 반복되고 있습니다.",
                    "observed_issue": "추가 지원 예산이 편성됐지만 집행 잔액이 반복되는 원인을 확인해야 합니다.",
                    "editorial_hypothesis": "활동지원 수요와 서비스 연결 사이에 공백이 있는가",
                },
                "editorial_review": {"verdict": "PURSUE"},
            }],
        }

        def assess(records, *_):
            return {"assessments": [{**GOOD, "id": records[0]["id"],
                                     "anchor_quote": records[0]["evidence_text"]}]}

        def review(_, proposals, *__):
            return {"reviews": [{
                "id": proposals[0]["id"], "verdict": "KEEP",
                "editorial_risk": "예산 잔액이 서비스 공백과 무관한 정산 시점 차이일 수 있다",
                "decisive_test": "집행 내역과 대기자·제공기관 연결 기록을 같은 기간으로 대조한다",
                "reason": "사실을 확정하지 않고 두 설명을 가를 취재 경로가 구체적이다",
            }]}

        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "shadow.json"
            with patch.object(module, "known_leads", return_value=[]), \
                    patch.object(module, "reviewed_ids", return_value=set()), \
                    patch.object(module, "model_assess", side_effect=assess), \
                    patch.object(module, "model_review", side_effect=review), \
                    patch.dict(module.os.environ, {"OPENAI_API_KEY": "test"}):
                result = module.run("test", district_shadow=payload,
                                    only_district=True, output_path=output)
        self.assertEqual(result["status"], "SHADOW_REVIEW_READY")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(result["proposals"], [])
        self.assertEqual(len(result["shadow_reviews"]), 1)
        self.assertFalse(result["shadow_reviews"][0]["production_eligible"])

    def test_citizen_shadow_accepts_only_redacted_direct_experience(self):
        payload = {
            "schema": 2,
            "records": [{
                "proposal_id": "17",
                "title": "우리 동네 주민센터 방문 불편",
                "posted_date": "2026-09-27",
                "source_url": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=17",
                "statement_type": "SELF_REPORTED_EXPERIENCE",
                "claim_status": "UNVERIFIED",
                "evidence_anchor": {
                    "status": "CLASSIFICATION_SUPPORT_ONLY",
                    "excerpt": "저는 주민센터를 세 번 방문했지만 안내가 달라 다시 돌아와야 했고 시간이 많이 들었습니다.",
                    "not_proof_of_event": True,
                },
                "context_candidates": {
                    "place_terms_from_title": ["주민센터"],
                    "time_terms_from_body": ["최근"],
                },
            }],
        }
        records, gaps = module.source_inputs(citizen_shadow=payload, only_citizen=True)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["family"], "시민제안")
        self.assertEqual(records[0]["source_stage"], "시민제안 L3 그림자 검토")
        self.assertFalse(records[0]["production_eligible"])
        self.assertIn("주민센터", records[0]["context"])
        self.assertEqual(gaps, [])

    def test_citizen_shadow_rejects_idea_hearsay_and_unbounded_anchor(self):
        base = {
            "proposal_id": "17",
            "title": "공원 시설 개선",
            "posted_date": "2026-09-27",
            "source_url": "https://idea.seoul.go.kr/front/freeSuggest/view.do?sn=17",
            "claim_status": "UNVERIFIED",
            "evidence_anchor": {
                "status": "CLASSIFICATION_SUPPORT_ONLY",
                "excerpt": "저는 공원을 이용하면서 반복되는 불편을 실제로 겪었다고 적었습니다.",
                "not_proof_of_event": True,
            },
        }
        payload = {"schema": 2, "records": [
            {**base, "statement_type": "POLICY_IDEA"},
            {**base, "proposal_id": "18", "statement_type": "HEARSAY"},
            {**base, "proposal_id": "19", "statement_type": "SELF_REPORTED_EXPERIENCE",
             "evidence_anchor": {**base["evidence_anchor"], "not_proof_of_event": False}},
        ]}
        records, gaps = module.source_inputs(citizen_shadow=payload, only_citizen=True)
        self.assertEqual(records, [])
        self.assertEqual(gaps[0]["source"], "시민제안")

    def test_citizen_shadow_never_becomes_final_proposal(self):
        citizen = {**GOOD, "id": "citizen", "source": "상상대로 서울 시민제안",
                   "family": "시민제안", "source_stage": "시민제안 L3 그림자 검토",
                   "production_eligible": False}
        final, shadow = module.partition_reviewed_proposals([citizen])
        self.assertEqual(final, [])
        self.assertEqual([item["id"] for item in shadow], ["citizen"])
        self.assertEqual(shadow[0]["briefing_output"], "NONE")

    def test_sources_require_body_or_context(self):
        old_root = module.ROOT
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "interest-signal-pilot/output").mkdir(parents=True)
            (root / "source-scout-v1/output").mkdir(parents=True)
            (root / "source-onboarding-v1/output/audit-l4").mkdir(parents=True)
            (root / "interest-signal-pilot/output/review_queue_latest.json").write_text(json.dumps(
                {"items": [{"headline": "제목만", "source_context_status": "TITLE_ONLY"},
                           {"headline": "본문", "publisher_url": "https://example.org/news",
                            "source_context_status": "BODY_READ",
                            "content_assessment": {"anchor_quote": "본문에서 확인한 연속 구절입니다",
                                                   "what_happened": "구체적인 사건 서술",
                                                   "question_worth": "HIGH"}}]}), encoding="utf-8")
            (root / "source-scout-v1/output/daily_feed_latest.json").write_text(json.dumps(
                {"editorial_triage": [{"source_id": "council_minutes", "url": "https://example.org/council",
                                       "text": "새 사업에 관한 의원 발언의 구체적 원문이 충분히 길게 저장돼 있습니다. 실제 세부 내용은 주장 상태로만 취급합니다."}]}),
                encoding="utf-8")
            (root / "source-onboarding-v1/output/audit-l4/state_latest.json").write_text(
                json.dumps({"runs": [], "records": []}), encoding="utf-8")
            try:
                module.ROOT = root
                records, gaps = module.source_inputs()
                self.assertEqual({x["family"] for x in records}, {"뉴스", "서울시의회"})
                self.assertTrue(any(x["source"] == "25개 자치구의회" for x in gaps))
            finally:
                module.ROOT = old_root


    def test_council_stale_carryover_is_bounded_input(self):
        old_root = module.ROOT
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source-scout-v1/output").mkdir(parents=True)
            (root / "source-onboarding-v1/output/audit-l4").mkdir(parents=True)
            (root / "source-scout-v1/output/daily_feed_latest.json").write_text(
                json.dumps({
                    "editorial_triage": [],
                    "stale_carryover": [{
                        "source_id": "council_minutes",
                        "freshness_status": "STALE_CARRYOVER",
                        "url": "https://example.org/council/carry",
                        "source_date": "2026-09-11",
                        "text": "서울의 새 지원 사업은 신청 경로에 따라 이용 순서와 대기 방식이 달라질 수 있다는 의원 발언입니다. 같은 자격의 시민에게 다른 결과가 생기는지 확인해야 합니다.",
                        "context_subject": "새 지원 사업의 신청 경로",
                        "context_text": "같은 자격을 가진 시민도 신청 창구에 따라 처리 순서가 달라지는지 확인해야 합니다.",
                        "question": "접수 창구별 대기와 처리 결과가 실제로 다른가?",
                        "affected_group": "지원 신청 시민",
                    }],
                    "metrics": [{"id": "council_minutes", "stale_carryover": 1, "context_holds": 0}],
                }, ensure_ascii=False), encoding="utf-8")
            (root / "source-onboarding-v1/output/audit-l4/state_latest.json").write_text(
                json.dumps({"runs": [], "records": []}), encoding="utf-8")
            try:
                module.ROOT = root
                records, gaps = module.source_inputs()
            finally:
                module.ROOT = old_root
        council = [row for row in records if row["family"] == "서울시의회"]
        self.assertEqual(len(council), 1)
        self.assertEqual(council[0]["source_stage"], "신선도 유예·미판정")
        self.assertTrue(council[0]["production_eligible"])
        self.assertFalse(any(gap["source"] == "서울시의회" for gap in gaps))

    def test_audit_uses_only_human_verify_card_as_shadow_input(self):
        old_root = module.ROOT
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "source-scout-v1/output").mkdir(parents=True)
            audit_dir = root / "source-onboarding-v1/output/audit-l4"
            audit_dir.mkdir(parents=True)
            (root / "source-scout-v1/output/daily_feed_latest.json").write_text(
                json.dumps({"editorial_triage": [], "stale_carryover": [], "metrics": []}),
                encoding="utf-8")
            def audit_row(record_id, title):
                return {"source_record_id": record_id, "card": {
                    "question_status": "READY_FOR_HUMAN_REVIEW",
                    "source_frame": "공개 감사보고서에서 시민 서비스와 연결된 구체적인 절차 지적을 확인했습니다.",
                    "detail_url": "https://example.org/audit/" + record_id,
                    "published_at": "2026-09-15",
                    "title": title,
                    "editorial_addition": "감사 이후 실제 운영 변화와 반복 여부를 검증합니다.",
                    "public_interest_to_verify": "시민이 이용하는 서비스 절차",
                    "verification_question": "지적된 절차 공백이 실제 이용자의 선택을 제한했는가?",
                    "competing_hypotheses": ["실제 공백이 있었다", "대체 절차가 작동했다"],
                }}
            (audit_dir / "state_latest.json").write_text(json.dumps({
                "runs": [{"selected_ids": []}],
                "records": [audit_row("verify", "검증 카드"),
                            audit_row("start", "취재 착수 카드"),
                            audit_row("reject", "기각 카드")],
            }, ensure_ascii=False), encoding="utf-8")
            (root / "source-onboarding-v1/audit_l4_reviews.csv").write_text(
                "source_record_id,verdict\nverify,VERIFY\nstart,START_REPORTING\nreject,REJECT\n",
                encoding="utf-8")
            try:
                module.ROOT = root
                records, gaps = module.source_inputs()
            finally:
                module.ROOT = old_root
        audits = [row for row in records if row["family"] == "서울시 감사"]
        self.assertEqual(len(audits), 1)
        self.assertEqual(audits[0]["headline"], "검증 카드")
        self.assertEqual(audits[0]["source_stage"], "감사 L4 사람 검증 대기")
        self.assertFalse(audits[0]["production_eligible"])
        self.assertFalse(any(gap["source"] == "서울시 감사" for gap in gaps))

    def test_source_coverage_counts_generated_audit_shadow(self):
        audit = {**BASE, "id": "audit", "family": "서울시 감사",
                 "source": "서울시 감사 결과", "production_eligible": False}
        coverage = module.build_source_coverage(
            [audit], [audit], [audit], [], {"queues": []}, [],
            [{**audit, "status": "검증 전용·최종 후보 아님"}])
        by_source = {row["source"]: row for row in coverage}
        self.assertEqual(by_source["서울시 감사"]["pending_shadow"], 1)
        self.assertEqual(by_source["서울시 감사"]["state"], "그림자 사람 판정 대기")


if __name__ == "__main__":
    unittest.main()
