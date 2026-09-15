#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "shadow_contracts",
    HERE / "contracts.py",
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load contracts.py")
contracts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contracts)


def valid_payload() -> dict:
    return {
        "schema_version": "candidate-assessment-v1",
        "agent_role": "EDITOR",
        "snapshot_id": "a" * 64,
        "candidate_id": "council-bus-wage",
        "issue_title": "서울 시내버스 통상임금 부담",
        "issue_summary": "시내버스 통상임금 관련 비용 부담의 귀속을 확인한다.",
        "evidence_refs": [
            {
                "quote_id": "q1",
                "ref_id": "source-1",
                "source_id": "council_minutes",
                "url": "https://example.test/minutes/1",
                "exact_text": "현재 미지급 통상임금이 약 2,900억 원이라고 합니다.",
                "claim_status": "ATTRIBUTED_CLAIM",
            }
        ],
        "citizen_stake": {
            "affected_group": "버스 노동자·운수업체·서울시민",
            "loss_type": "MONEY",
            "consequence": "결정 지연 비용의 부담 주체가 달라질 수 있다.",
        },
        "structural_mechanism": "준공영제와 임금 정산 구조가 비용 귀속을 결정한다.",
        "editorial_tension": "결정을 미룰수록 비용이 줄지 않고 늘어날 수 있다는 주장이다.",
        "confirmed_facts": [],
        "unverified_claims": [
            {
                "text": "미지급액이 약 2,900억 원이라는 의원 발언",
                "source_ref_ids": ["q1"],
            }
        ],
        "competing_hypotheses": [
            {
                "name": "서울시 부담 확대",
                "explanation": "준공영제 정산 구조로 재정 부담이 커진다.",
                "discriminating_evidence": "운수업체별 정산 규정과 판결 적용 범위",
            },
            {
                "name": "운수업체 개별 부담",
                "explanation": "임금채무가 업체별 노사관계에 귀속된다.",
                "discriminating_evidence": "업체별 소송 당사자와 지급 책임",
            },
        ],
        "verification_plan": [
            {
                "action": "판결문과 서울시 정산 기준을 대조한다.",
                "source_family": "PUBLIC",
                "pass_signal": "금액 산정 범위와 부담 주체가 재현된다.",
            }
        ],
        "kill_criteria": ["제시 금액이 중복 계산됐거나 서울시와 무관하면 폐기한다."],
        "scores": {
            "tension_surprise": 2,
            "citizen_loss_rights": 2,
            "distribution_exclusion": 1,
            "competing_hypotheses": 1,
            "accountability_change": 1,
            "falsification_decision_line": 1,
        },
        "score_total": 8,
        "grounding_level": "G1_ATTRIBUTED_CLAIM",
        "verdict": "PASS",
        "recommended_lane": "VERIFY_TODAY",
        "scope_warning": "서울 전체 임금시장 수치가 아니다.",
        "reasoning_summary": "사안은 무겁지만 금액과 부담 주체를 독립 자료로 확인해야 한다.",
    }


class ContractTests(unittest.TestCase):
    def test_valid_assessment_passes(self):
        payload = valid_payload()
        self.assertIs(
            contracts.validate_assessment(
                payload,
                expected_snapshot_id="a" * 64,
            ),
            payload,
        )

    def test_multiple_quotes_from_one_source_are_distinct(self):
        payload = valid_payload()
        payload["evidence_refs"].append(
            {
                "quote_id": "q2",
                "ref_id": "source-1",
                "source_id": "council_minutes",
                "url": "https://example.test/minutes/1",
                "exact_text": "예산안 제출일과 수요조사 착수일을 비교해야 합니다.",
                "claim_status": "ATTRIBUTED_CLAIM",
            }
        )
        payload["confirmed_facts"] = [
            {
                "text": "예산안과 수요조사 시점을 비교해야 한다는 발언",
                "source_ref_ids": ["q2"],
            }
        ]
        self.assertIs(contracts.validate_assessment(payload), payload)

    def test_duplicate_quote_id_is_rejected(self):
        payload = valid_payload()
        duplicate = copy.deepcopy(payload["evidence_refs"][0])
        duplicate["exact_text"] = "다른 문장"
        payload["evidence_refs"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "duplicate quote_id"):
            contracts.validate_assessment(payload)

    def test_score_total_mismatch_is_rejected(self):
        payload = valid_payload()
        payload["score_total"] = 9
        with self.assertRaisesRegex(ValueError, "score_total"):
            contracts.validate_assessment(payload)

    def test_low_quality_cannot_claim_pass(self):
        payload = valid_payload()
        payload["scores"]["citizen_loss_rights"] = 0
        payload["score_total"] = 6
        with self.assertRaisesRegex(ValueError, "8/12"):
            contracts.validate_assessment(payload)

    def test_unknown_evidence_reference_is_rejected(self):
        payload = valid_payload()
        payload["unverified_claims"][0]["source_ref_ids"] = ["missing"]
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            contracts.validate_assessment(payload)

    def test_editorial_proposal_requires_independent_corroboration(self):
        payload = valid_payload()
        payload["recommended_lane"] = "EDITORIAL_PROPOSAL"
        with self.assertRaisesRegex(ValueError, "independent corroboration"):
            contracts.validate_assessment(payload)

    def test_hidden_reasoning_fields_are_rejected(self):
        payload = valid_payload()
        payload["chain_of_thought"] = "비공개 추론"
        with self.assertRaisesRegex(ValueError, "hidden reasoning"):
            contracts.validate_assessment(payload)

    def test_wrong_snapshot_is_rejected(self):
        payload = copy.deepcopy(valid_payload())
        with self.assertRaisesRegex(ValueError, "expected snapshot"):
            contracts.validate_assessment(
                payload,
                expected_snapshot_id="b" * 64,
            )


if __name__ == "__main__":
    unittest.main()
