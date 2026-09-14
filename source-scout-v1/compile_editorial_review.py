#!/usr/bin/env python3
"""Compile human-review cards and safe S0 transition proposals.

This script is deliberately read-only with respect to ITEM_LEDGER.csv and
QUESTION_QUALITY_AUDIT.csv. Scheduled runs may prepare proposals, never apply them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
DEFAULT_QUEUE = HERE / "HUMAN_REVIEW_QUEUE.csv"
DEFAULT_LEDGER = ROOT / "agent-system-v1" / "ITEM_LEDGER.csv"
DEFAULT_AUDIT = ROOT / "agent-system-v1" / "QUESTION_QUALITY_AUDIT.csv"
OUTPUT = HERE / "output"
VALID_JUDGMENTS = {"PROMISING", "VERIFY", "NOISE", "DUPLICATE"}
POSITIVE_ANCHORS = {
    "DIRECT_PROBLEM_SIGNAL",
    "MEASURED_PROBLEM_SIGNAL",
    "DECOMPOSABLE_STRUCTURE",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def text(row: dict[str, str], key: str, legacy: str = "") -> str:
    return (row.get(key) or (row.get(legacy) if legacy else "") or "").strip()


def candidate_revision(row: dict[str, str]) -> str:
    basis = f"{text(row, 'url')}|{text(row, 'text')}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def proposal_blockers(row: dict[str, str]) -> list[str]:
    blockers: list[str] = []
    if text(row, "editor_judgment").upper() != "PROMISING":
        blockers.append("PROMISING 판정 아님")
    if text(row, "editor_evidence_anchor").upper() not in POSITIVE_ANCHORS:
        blockers.append("사람이 확인한 긍정 근거 앵커 없음")
    required = {
        "anchor_detail": "확인된 앵커 사실",
        "anchor_scope": "앵커 범위",
        "central_question": "중심 질문",
        "citizen_stake": "시민 손실",
        "competing_hypotheses": "경쟁 가설",
        "decision_rule": "판정선",
        "reviewed_by": "검토자",
        "reviewed_at": "검토 시각",
    }
    for field, label in required.items():
        if not text(row, field):
            blockers.append(f"{label} 없음")
    current_revision = text(row, "source_revision") or candidate_revision(row)
    if text(row, "review_revision") != current_revision:
        blockers.append("원문 지문과 검토 지문 불일치")
    if text(row, "grounding_status").upper() != "PASS":
        blockers.append("질문-근거 일치 미통과")
    return blockers


def build_review(queue_rows: list[dict[str, str]], ledger_rows: list[dict[str, str]]) -> dict:
    ledger_ids = {text(row, "item_id") for row in ledger_rows}
    cards: list[dict] = []
    proposals: list[dict] = []
    killer_candidates: list[dict] = []
    invalid_labels: list[str] = []

    for row in queue_rows:
        judgment = text(row, "editor_judgment").upper()
        active_raw = text(row, "auto_active_today")
        active_today = active_raw.lower() == "true" if active_raw else True
        if not active_today and not judgment:
            continue
        candidate_id = text(row, "candidate_id")
        if judgment and judgment not in VALID_JUDGMENTS:
            invalid_labels.append(candidate_id)
        auto_anchor = text(row, "auto_evidence_anchor", "evidence_anchor") or "NONE"
        card = {
            "candidate_id": candidate_id,
            "source_revision": text(row, "source_revision") or candidate_revision(row),
            "fact": text(row, "question_basis") or text(row, "text"),
            "source_name": text(row, "source_name"),
            "url": text(row, "url"),
            "auto_anchor": auto_anchor,
            "claim_status": text(row, "claim_status") or "UNRESOLVED",
            "question": text(row, "central_question") or text(row, "question"),
            "verification_axes": text(row, "verification_axes"),
            "editor_judgment": judgment or "PENDING",
            "transition_state": text(row, "transition_state") or "미승인",
            "active_today": active_today,
        }
        cards.append(card)

        if judgment == "DUPLICATE":
            parent = text(row, "duplicate_parent_id")
            if not parent or parent not in ledger_ids:
                card["decision_blocker"] = "유효한 기존 parent_item_id 필요"
            continue
        if judgment in {"NOISE", ""}:
            continue

        blockers = proposal_blockers(row)
        if judgment == "PROMISING" and not blockers:
            proposal = {
                "candidate_id": candidate_id,
                "source_revision": card["source_revision"],
                "proposed_stage": "S0",
                "proposed_production": "미판정",
                "proposed_upstream_gate": "HOLD",
                "proposed_scene_status": "없음",
                "confirmed_evidence": text(row, "anchor_detail"),
                "central_question": text(row, "central_question"),
                "citizen_stake": text(row, "citizen_stake"),
                "competing_hypotheses": text(row, "competing_hypotheses"),
                "decision_rule": text(row, "decision_rule"),
                "minimum_test": text(row, "minimum_test"),
                "approval_required": True,
                "applied": False,
            }
            proposals.append(proposal)
        elif judgment == "PROMISING":
            card["decision_blocker"] = "; ".join(blockers)

        test_fields = {
            "test_question": text(row, "minimum_test"),
            "test_pass_rule": text(row, "test_pass_rule"),
            "test_kill_rule": text(row, "test_kill_rule"),
            "test_timebox_hours": text(row, "test_timebox_hours"),
        }
        if judgment in {"PROMISING", "VERIFY"} and all(test_fields.values()):
            killer_candidates.append(
                {
                    "candidate_id": candidate_id,
                    "judgment": judgment,
                    **test_fields,
                    "test_status": "PLANNED",
                    "test_evidence_ref": "",
                    "test_result": "",
                    "test_decision": "",
                }
            )

    killer_candidates.sort(
        key=lambda item: (item["judgment"] == "PROMISING", item["candidate_id"]),
        reverse=True,
    )
    return {
        "review_cards": cards,
        "transition_proposals": proposals,
        "killer_test": killer_candidates[0] if killer_candidates else None,
        "invalid_labels": invalid_labels,
        "safety": {
            "scheduled_apply": False,
            "ledger_mutated": False,
            "audit_mutated": False,
            "rule": "제안은 사람 승인 뒤 별도 커밋에서만 audit와 ledger에 함께 반영",
        },
    }


def build_legacy_rereview(
    audit_rows: list[dict[str, str]], ledger_rows: list[dict[str, str]]
) -> list[dict]:
    ledger = {text(row, "item_id"): row for row in ledger_rows}
    result: list[dict] = []
    for audit in audit_rows:
        item_id = text(audit, "item_id")
        item = ledger.get(item_id, {})
        source_report = text(item, "source_report")
        source_exists = bool(source_report and (ROOT / source_report).is_file())
        priority = 1 if text(item, "upstream_gate") == "PASS" else (
            2 if text(item, "editorial_e") == "E3" or text(item, "stage_s") == "S1" else 3
        )
        result.append(
            {
                "item_id": item_id,
                "priority": priority,
                "previous_quality_gate": text(audit, "quality_gate"),
                "previous_quality_score": text(audit, "quality_score"),
                "stage": text(item, "stage_s"),
                "editorial_e": text(item, "editorial_e"),
                "source_report": source_report,
                "source_status": "AVAILABLE" if source_exists else "SOURCE_REQUIRED",
                "evidence_anchor": text(audit, "evidence_anchor") or "UNREVIEWED",
                "action": "원자료 복구 후 0점부터 재심사",
            }
        )
    return sorted(result, key=lambda row: (row["priority"], row["item_id"]))


def render_cards(payload: dict) -> str:
    lines = [
        "# 편집 판정 카드",
        "",
        "자동 추천과 사람 판정을 분리한다. 이 문서는 장부를 변경하지 않는다.",
        "",
        "## 판정 대기·완료 카드",
        "",
    ]
    if not payload["review_cards"]:
        lines.extend(["- 카드 없음", ""])
    for index, card in enumerate(payload["review_cards"], 1):
        lines.extend(
            [
                f"### {index}. {card['candidate_id']}",
                "",
                f"- 관찰된 사실: {card['fact'] or '-'}",
                f"- 자동 추정: {card['auto_anchor']} · {card['claim_status']} — 사람 판정 아님",
                f"- 제안 질문: {card['question'] or '-'}",
                f"- 아직 확인할 변수: {card['verification_axes'] or '-'}",
                f"- 사람 판정: {card['editor_judgment']}",
                f"- 원문: {card['url'] or '-'}",
                f"- 전이 상태: {card['transition_state']} — 장부 변경 없음",
            ]
        )
        if card.get("decision_blocker"):
            lines.append(f"- 전이 차단: {card['decision_blocker']}")
        lines.append("")
    lines.extend(
        [
            "응답 예시: 1번 VERIFY, 2번 PROMISING, 3번은 기존 ITEM_ID와 DUPLICATE",
            "",
            "## S0 전이 승인 대기",
            "",
        ]
    )
    if not payload["transition_proposals"]:
        lines.extend(["- 완전한 사람 검토를 마친 전이 제안 없음", ""])
    else:
        for proposal in payload["transition_proposals"]:
            lines.append(
                f"- {proposal['candidate_id']}: S0/HOLD 제안 · 별도 승인 필요 · 아직 미적용"
            )
        lines.append("")
    lines.extend(["## 오늘의 킬러 테스트", ""])
    killer = payload["killer_test"]
    if killer is None:
        lines.extend(["- 완전한 판정선이 입력된 테스트 없음", ""])
    else:
        lines.extend(
            [
                f"- 대상: {killer['candidate_id']}",
                f"- 질문: {killer['test_question']}",
                f"- 통과선: {killer['test_pass_rule']}",
                f"- 폐기선: {killer['test_kill_rule']}",
                f"- 시간상자: {killer['test_timebox_hours']}시간",
                "- 상태: PLANNED — 아직 수행하지 않음",
                "",
            ]
        )
    return "\n".join(lines)


def render_legacy(rows: list[dict]) -> str:
    lines = [
        "# 기존 질문 20건 근거 앵커 재심사표",
        "",
        "기존 점수는 승계하지 않는다. 원자료를 복구한 뒤 0점부터 다시 심사한다.",
        "",
        "| 우선 | item_id | 기존 판정/점수 | 단계/E | 원자료 | 앵커 | 조치 |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['priority']} | {row['item_id']} | "
            f"{row['previous_quality_gate']}/{row['previous_quality_score']} | "
            f"{row['stage']}/{row['editorial_e']} | {row['source_status']} | "
            f"{row['evidence_anchor']} | {row['action']} |"
        )
    lines.extend(
        [
            "",
            f"- 총 {len(rows)}건",
            f"- 원자료 복구 필요: {sum(row['source_status'] == 'SOURCE_REQUIRED' for row in rows)}건",
            "- 이 표는 재심사 대기열이며 앵커를 자동 추정하지 않는다.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    queue_rows = read_csv(args.queue)
    ledger_rows = read_csv(args.ledger)
    audit_rows = read_csv(args.audit)
    before_ledger = args.ledger.read_bytes() if args.ledger.is_file() else b""
    before_audit = args.audit.read_bytes() if args.audit.is_file() else b""
    payload = build_review(queue_rows, ledger_rows)
    legacy = build_legacy_rereview(audit_rows, ledger_rows)
    payload["legacy_rereview"] = legacy
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "editorial_review_cards_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT / "editorial_review_cards_latest.md").write_text(
        render_cards(payload), encoding="utf-8"
    )
    (OUTPUT / "legacy_anchor_rereview_latest.md").write_text(
        render_legacy(legacy), encoding="utf-8"
    )
    if args.ledger.is_file() and args.ledger.read_bytes() != before_ledger:
        raise RuntimeError("scheduled compiler changed ITEM_LEDGER.csv")
    if args.audit.is_file() and args.audit.read_bytes() != before_audit:
        raise RuntimeError("scheduled compiler changed QUESTION_QUALITY_AUDIT.csv")
    print(
        f"review_cards={len(payload['review_cards'])} "
        f"proposals={len(payload['transition_proposals'])} "
        f"legacy={len(legacy)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
