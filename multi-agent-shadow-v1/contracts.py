#!/usr/bin/env python3
"""Runtime contract for auditable multi-agent shadow assessments."""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "candidate-assessment-v1"
AGENT_ROLES = {
    "DISCOVERY_PUBLIC",
    "DISCOVERY_CITIZEN",
    "DISCOVERY_STRUCTURE",
    "EDITOR",
    "SKEPTIC",
    "BACKFILL",
    "ORCHESTRATOR",
}
GROUNDING_LEVELS = {
    "G0_UNGROUNDED",
    "G1_ATTRIBUTED_CLAIM",
    "G2_SUPPORTING_RECORD",
    "G3_INDEPENDENT_CORROBORATION",
}
VERDICTS = {"PASS", "HOLD", "FAIL"}
LANES = {"QUESTION_RAW", "VERIFY_TODAY", "EDITORIAL_PROPOSAL", "REJECT"}
LOSS_TYPES = {"MONEY", "TIME", "SAFETY", "RIGHTS", "ACCESS", "CHOICE", "MULTIPLE"}
SOURCE_FAMILIES = {"PUBLIC", "PRICE", "BEHAVIOR", "VOICE", "FIELD", "INDUSTRY", "MEDIA", "SOCIAL"}
SCORE_FIELDS = (
    "tension_surprise",
    "citizen_loss_rights",
    "distribution_exclusion",
    "competing_hypotheses",
    "accountability_change",
    "falsification_decision_line",
)
REQUIRED_FIELDS = {
    "schema_version",
    "agent_role",
    "snapshot_id",
    "candidate_id",
    "issue_title",
    "issue_summary",
    "evidence_refs",
    "citizen_stake",
    "structural_mechanism",
    "editorial_tension",
    "confirmed_facts",
    "unverified_claims",
    "competing_hypotheses",
    "verification_plan",
    "kill_criteria",
    "scores",
    "score_total",
    "grounding_level",
    "verdict",
    "recommended_lane",
    "scope_warning",
    "reasoning_summary",
}


def require_text(payload: dict, field: str, *, maximum: int | None = None) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be non-empty text")
    if maximum is not None and len(value) > maximum:
        raise ValueError(f"{field} exceeds {maximum} characters")
    return value.strip()


def require_enum(payload: dict, field: str, allowed: set[str]) -> str:
    value = payload.get(field)
    if value not in allowed:
        raise ValueError(f"{field} has unsupported value: {value}")
    return value


def validate_sourced_statements(
    statements: Any,
    field: str,
    evidence_ids: set[str],
) -> None:
    if not isinstance(statements, list):
        raise ValueError(f"{field} must be a list")
    for index, statement in enumerate(statements):
        if not isinstance(statement, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        require_text(statement, "text", maximum=600)
        ref_ids = statement.get("source_ref_ids")
        if not isinstance(ref_ids, list) or not ref_ids:
            raise ValueError(f"{field}[{index}] must cite source_ref_ids")
        unknown = [ref_id for ref_id in ref_ids if ref_id not in evidence_ids]
        if unknown:
            raise ValueError(
                f"{field}[{index}] cites unknown evidence refs: "
                + ", ".join(unknown)
            )


def validate_assessment(
    payload: Any,
    *,
    expected_snapshot_id: str | None = None,
) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("assessment must be a JSON object")
    missing = sorted(REQUIRED_FIELDS - payload.keys())
    if missing:
        raise ValueError("assessment is missing fields: " + ", ".join(missing))
    forbidden = {"chain_of_thought", "hidden_reasoning", "internal_monologue"} & payload.keys()
    if forbidden:
        raise ValueError("assessment contains forbidden hidden reasoning fields")
    if payload["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported assessment schema")
    require_enum(payload, "agent_role", AGENT_ROLES)
    snapshot_id = require_text(payload, "snapshot_id")
    if len(snapshot_id) != 64 or any(ch not in "0123456789abcdef" for ch in snapshot_id):
        raise ValueError("snapshot_id must be a lowercase SHA-256 digest")
    if expected_snapshot_id and snapshot_id != expected_snapshot_id:
        raise ValueError("assessment does not belong to the expected snapshot")
    require_text(payload, "candidate_id", maximum=120)
    require_text(payload, "issue_title", maximum=160)
    require_text(payload, "issue_summary", maximum=800)
    require_text(payload, "structural_mechanism", maximum=800)
    require_text(payload, "editorial_tension", maximum=600)
    require_text(payload, "reasoning_summary", maximum=800)
    if not isinstance(payload.get("scope_warning"), str):
        raise ValueError("scope_warning must be text")

    evidence = payload.get("evidence_refs")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("evidence_refs must contain at least one source")
    evidence_ids: set[str] = set()
    for index, ref in enumerate(evidence):
        if not isinstance(ref, dict):
            raise ValueError(f"evidence_refs[{index}] must be an object")
        quote_id = require_text(ref, "quote_id", maximum=80)
        if quote_id in evidence_ids:
            raise ValueError(f"duplicate quote_id: {quote_id}")
        evidence_ids.add(quote_id)
        require_text(ref, "ref_id")
        require_text(ref, "source_id")
        url = require_text(ref, "url")
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"evidence_refs[{index}] url must be HTTP(S)")
        require_text(ref, "exact_text", maximum=1600)
        if ref.get("claim_status") not in {
            "OBSERVED_OR_PUBLISHED",
            "ATTRIBUTED_CLAIM",
            "UNRESOLVED",
        }:
            raise ValueError(f"evidence_refs[{index}] has invalid claim_status")

    stake = payload.get("citizen_stake")
    if not isinstance(stake, dict):
        raise ValueError("citizen_stake must be an object")
    require_text(stake, "affected_group", maximum=240)
    require_enum(stake, "loss_type", LOSS_TYPES)
    require_text(stake, "consequence", maximum=600)

    validate_sourced_statements(
        payload.get("confirmed_facts"),
        "confirmed_facts",
        evidence_ids,
    )
    validate_sourced_statements(
        payload.get("unverified_claims"),
        "unverified_claims",
        evidence_ids,
    )

    hypotheses = payload.get("competing_hypotheses")
    if not isinstance(hypotheses, list) or len(hypotheses) < 2:
        raise ValueError("at least two competing_hypotheses are required")
    for index, hypothesis in enumerate(hypotheses):
        if not isinstance(hypothesis, dict):
            raise ValueError(f"competing_hypotheses[{index}] must be an object")
        require_text(hypothesis, "name", maximum=120)
        require_text(hypothesis, "explanation", maximum=600)
        require_text(hypothesis, "discriminating_evidence", maximum=500)

    plan = payload.get("verification_plan")
    if not isinstance(plan, list):
        raise ValueError("verification_plan must be a list")
    for index, step in enumerate(plan):
        if not isinstance(step, dict):
            raise ValueError(f"verification_plan[{index}] must be an object")
        require_text(step, "action", maximum=500)
        require_enum(step, "source_family", SOURCE_FAMILIES)
        require_text(step, "pass_signal", maximum=400)

    kill_criteria = payload.get("kill_criteria")
    if not isinstance(kill_criteria, list) or any(
        not isinstance(item, str) or not item.strip() for item in kill_criteria
    ):
        raise ValueError("kill_criteria must be a list of non-empty text")

    scores = payload.get("scores")
    if not isinstance(scores, dict) or set(scores) != set(SCORE_FIELDS):
        raise ValueError("scores must contain exactly the six quality dimensions")
    for field in SCORE_FIELDS:
        value = scores[field]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 2:
            raise ValueError(f"scores.{field} must be an integer from 0 to 2")
    total = sum(scores.values())
    if payload.get("score_total") != total:
        raise ValueError("score_total does not equal the six score dimensions")

    grounding = require_enum(payload, "grounding_level", GROUNDING_LEVELS)
    verdict = require_enum(payload, "verdict", VERDICTS)
    lane = require_enum(payload, "recommended_lane", LANES)

    if verdict == "PASS":
        mandatory = (
            scores["citizen_loss_rights"],
            scores["competing_hypotheses"],
            scores["falsification_decision_line"],
        )
        if total < 8 or any(score < 1 for score in mandatory):
            raise ValueError("PASS does not satisfy the 8/12 quality gate")
        if not plan or not kill_criteria:
            raise ValueError("PASS requires a verification plan and kill criteria")
    if lane == "EDITORIAL_PROPOSAL" and grounding != "G3_INDEPENDENT_CORROBORATION":
        raise ValueError("EDITORIAL_PROPOSAL requires independent corroboration")
    if lane == "VERIFY_TODAY" and grounding == "G0_UNGROUNDED":
        raise ValueError("VERIFY_TODAY cannot use ungrounded material")
    if lane == "REJECT" and verdict != "FAIL":
        raise ValueError("REJECT lane requires FAIL verdict")
    return payload
