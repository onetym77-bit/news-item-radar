from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "agent-system-v1" / "ITEM_LEDGER.csv"
DEFAULT_AUDIT = ROOT / "agent-system-v1" / "QUESTION_QUALITY_AUDIT.csv"
DEFAULT_QUEUE = ROOT / "agent-system-v1" / "VERIFICATION_QUEUE.csv"
DEFAULT_OUTPUT = ROOT / "daily-briefing-v5" / "output" / "briefing_latest.md"
DEFAULT_HISTORY = ROOT / "daily-briefing-v5" / "output" / "history"

QUEUE_FIELDS = [
    "item_id",
    "priority",
    "queued_on",
    "due_status",
    "stage_s",
    "editorial_e",
    "quality_gate",
    "quality_score",
    "central_question",
    "citizen_stake",
    "competing_hypotheses",
    "decision_rule",
    "originality_gate",
    "why_now",
    "minimum_test",
    "status",
    "citizen_loss_search",
    "counterevidence_search",
    "evidence_families",
    "scene_plan",
    "decision",
    "blocker",
    "next_check",
    "review_by",
    "last_updated",
]
CLOSED_STATUSES = {"탈락", "채택"}
DIRECT_SCENES = {"관찰됨", "당사자 진술"}
EDITORIAL_RANK = {"E3": 3, "E2": 2, "E1": 1, "E0": 0}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def parse_day(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def quality_score(audit: dict[str, str] | None) -> int:
    try:
        return int((audit or {}).get("quality_score", "0"))
    except ValueError:
        return 0


def due_status(review_by: str, as_of: date) -> str:
    due = parse_day(review_by)
    if due is None:
        return "UNSCHEDULED"
    if due < as_of:
        return "OVERDUE"
    if due == as_of:
        return "DUE_TODAY"
    return "UPCOMING"


def overdue_days(review_by: str, as_of: date) -> int:
    due = parse_day(review_by)
    return max((as_of - due).days, 0) if due else 0


def priority_for(row: dict[str, str], as_of: date) -> str:
    stage = row.get("stage_s", "")
    editorial = row.get("editorial_e", "")
    due = due_status(row.get("review_by", ""), as_of)
    if stage == "S1" and due in {"OVERDUE", "DUE_TODAY"}:
        return "P1"
    if stage == "S1" and editorial == "E3":
        return "P1"
    if stage == "S1":
        return "P2"
    return "P3"


def bottleneck_for(row: dict[str, str], queue_row: dict[str, str] | None) -> str:
    if row.get("question_gate") != "PASS":
        return "질문 품질 보완"
    queue_row = queue_row or {}
    if queue_row.get("originality_gate", "미평가") not in {"PASS", "통과"}:
        return "독창성·선행보도 확인 미완료"
    if queue_row.get("minimum_test", "미설계") in {"", "미설계", "미수행"}:
        return "최소 판정 실험 미설계"
    if queue_row.get("citizen_loss_search", "미수행") in {"", "미수행"}:
        return "시민 손실 근거 탐색 미수행"
    if queue_row.get("counterevidence_search", "미수행") in {"", "미수행"}:
        return "반대 근거 탐색 미수행"
    families = {part for part in row.get("source_families", "").split("|") if part}
    if len(families) < 2:
        return "독립 근거 계보 부족"
    if row.get("scene_status") not in DIRECT_SCENES:
        return "관찰·당사자 시민 장면 미확인"
    if row.get("upstream_gate") != "PASS":
        return "기사 게이트 미통과"
    return "승격 판정 필요"


def markdown(value: str) -> str:
    return (value or "미기록").replace("|", "·").replace("\r", " ").replace("\n", " ").strip()


def sort_key(
    row: dict[str, str],
    audit_by_id: dict[str, dict[str, str]],
    as_of: date,
) -> tuple[int, int, int, date, str]:
    status_rank = {
        "OVERDUE": 0,
        "DUE_TODAY": 1,
        "UPCOMING": 2,
        "UNSCHEDULED": 3,
    }[due_status(row.get("review_by", ""), as_of)]
    due = parse_day(row.get("review_by", "")) or date.max
    return (
        status_rank,
        -EDITORIAL_RANK.get(row.get("editorial_e", ""), 0),
        -quality_score(audit_by_id.get(row.get("item_id", ""))),
        due,
        row.get("item_id", ""),
    )


def merge_queue(
    ledger_rows: list[dict[str, str]],
    audit_by_id: dict[str, dict[str, str]],
    prior_by_id: dict[str, dict[str, str]],
    as_of: date,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for row in ledger_rows:
        item_id = row.get("item_id", "").strip()
        if row.get("status") in CLOSED_STATUSES:
            continue
        if row.get("question_gate") != "PASS" or row.get("stage_s") not in {"S0", "S1"}:
            continue
        audit = audit_by_id.get(item_id, {})
        prior = prior_by_id.get(item_id, {})
        current = {field: prior.get(field, "") for field in QUEUE_FIELDS}
        current.update(
            {
                "item_id": item_id,
                "priority": priority_for(row, as_of),
                "queued_on": prior.get("queued_on") or as_of.isoformat(),
                "due_status": due_status(row.get("review_by", ""), as_of),
                "stage_s": row.get("stage_s", ""),
                "editorial_e": row.get("editorial_e", ""),
                "quality_gate": audit.get("quality_gate") or row.get("question_gate", ""),
                "quality_score": audit.get("quality_score", ""),
                "central_question": audit.get("central_question") or row.get("structural_question", ""),
                "citizen_stake": audit.get("citizen_stake", ""),
                "competing_hypotheses": audit.get("competing_hypotheses")
                or row.get("question_hypothesis", ""),
                "decision_rule": audit.get("decision_rule", ""),
                "originality_gate": prior.get("originality_gate") or "미평가",
                "why_now": prior.get("why_now") or "미기록",
                "minimum_test": prior.get("minimum_test") or "미설계",
                "status": prior.get("status") or "대기",
                "citizen_loss_search": prior.get("citizen_loss_search") or "미수행",
                "counterevidence_search": prior.get("counterevidence_search") or "미수행",
                "evidence_families": row.get("source_families", ""),
                "scene_plan": prior.get("scene_plan") or "미작성",
                "decision": prior.get("decision") or "미판정",
                "next_check": row.get("next_check", ""),
                "review_by": row.get("review_by", ""),
                "last_updated": as_of.isoformat(),
            }
        )
        current["blocker"] = bottleneck_for(row, current)
        merged.append(current)
    return sorted(
        merged,
        key=lambda row: (
            {"P1": 0, "P2": 1, "P3": 2}.get(row["priority"], 9),
            {"OVERDUE": 0, "DUE_TODAY": 1, "UPCOMING": 2, "UNSCHEDULED": 3}.get(
                row["due_status"], 9
            ),
            -EDITORIAL_RANK.get(row["editorial_e"], 0),
            row["review_by"] or "9999-12-31",
            row["item_id"],
        ),
    )


def write_queue(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=QUEUE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def render_verification_card(
    row: dict[str, str],
    queue_row: dict[str, str],
    audit: dict[str, str],
) -> list[str]:
    return [
        f"### {markdown(row.get('canonical_topic', ''))}",
        "",
        f"- item_id / S·E / 검토기한: {row.get('item_id')} / {row.get('stage_s')}·{row.get('editorial_e')} / {row.get('review_by') or '미정'}",
        f"- 질문 게이트: {row.get('question_gate')}",
        f"- 질문 품질 점수: {audit.get('quality_score', '미기록')}/12",
        f"- 중심 질문: {markdown(audit.get('central_question') or row.get('structural_question'))}",
        f"- 시민 손실 가설: {markdown(audit.get('citizen_stake'))}",
        f"- 경쟁 가설: {markdown(audit.get('competing_hypotheses') or row.get('question_hypothesis'))}",
        f"- 판정선: {markdown(audit.get('decision_rule'))}",
        f"- 출처 프레임: {markdown(row.get('source_report'))}의 최초 주장과 결론을 분리 확인해야 함",
        f"- 편집적 추가: {markdown(audit.get('central_question') or row.get('structural_question'))}",
        f"- 독창성 게이트: {queue_row.get('originality_gate', '미평가')}",
        f"- 왜 지금 유형: {queue_row.get('why_now', '미기록')}",
        f"- 질문 가족: {row.get('item_id')} — 부모 질문 병합 여부 미확인",
        f"- 시민 손실 근거 탐색: {markdown(queue_row.get('citizen_loss_search'))}",
        f"- 반대 근거 탐색: {markdown(queue_row.get('counterevidence_search'))}",
        f"- 최소 판정 실험: {markdown(queue_row.get('minimum_test'))}",
        f"- 현재 병목: {markdown(queue_row.get('blocker'))}",
        f"- 지금 할 일: {markdown(row.get('next_check'))}",
        f"- 완료 결과물: 전환·축소·폐기 중 하나를 판정할 표·원문·당사자 확인 기록",
        "",
    ]


def render_briefing(
    ledger_rows: list[dict[str, str]],
    audit_by_id: dict[str, dict[str, str]],
    queue_rows: list[dict[str, str]],
    as_of: date,
) -> str:
    active = [row for row in ledger_rows if row.get("status") not in CLOSED_STATUSES]
    eligible_final = [
        row
        for row in active
        if row.get("stage_s") in {"S2", "S3"}
        and row.get("question_gate") == "PASS"
        and row.get("upstream_gate") == "PASS"
        and row.get("scene_status") in DIRECT_SCENES
    ]
    eligible_final.sort(
        key=lambda row: (
            -EDITORIAL_RANK.get(row.get("editorial_e", ""), 0),
            row.get("item_id", ""),
        )
    )
    final_rows = eligible_final[:3]

    queue_by_id = {row["item_id"]: row for row in queue_rows}
    verification_source = [
        row
        for row in active
        if row.get("item_id") in queue_by_id and row.get("stage_s") == "S1"
    ]
    verification_source.sort(key=lambda row: sort_key(row, audit_by_id, as_of))
    verification_rows = verification_source[:4]
    verification_ids = {row.get("item_id", "") for row in verification_rows}
    final_ids = {row.get("item_id", "") for row in final_rows}

    raw_rows = [
        row
        for row in active
        if row.get("item_id") not in verification_ids | final_ids
        and row.get("question_gate") in {"PASS", "HOLD"}
    ]
    raw_rows.sort(key=lambda row: sort_key(row, audit_by_id, as_of))
    raw_rows = raw_rows[:10]

    overdue = [
        row
        for row in active
        if row.get("stage_s") == "S1"
        and row.get("question_gate") == "PASS"
        and due_status(row.get("review_by", ""), as_of) == "OVERDUE"
    ]
    overdue.sort(key=lambda row: sort_key(row, audit_by_id, as_of))

    question_pass = sum(row.get("question_gate") == "PASS" for row in active)
    article_pass = sum(row.get("upstream_gate") == "PASS" for row in active)
    s2_s3 = sum(row.get("stage_s") in {"S2", "S3"} for row in active)
    scene_ready = sum(row.get("scene_status") in DIRECT_SCENES for row in active)

    lines = [
        "# 서울 기획기사 데일리 브리핑 v5",
        "",
        f"기준일: {as_of.isoformat()} KST",
        "",
        "## 한눈에 보는 전환 현황",
        "",
        f"- 활성 항목: {len(active)}건",
        f"- 질문 품질 PASS: {question_pass}건",
        f"- 기사 게이트 PASS: {article_pass}건",
        f"- S2·S3: {s2_s3}건",
        f"- 관찰·당사자 시민 장면 확보: {scene_ready}건",
        f"- 검토기한 경과 S1: {len(overdue)}건",
        f"- 오늘의 핵심 병목: 질문 생성보다 독창성·최소 실험·손실/반대 근거·시민 장면 확인이 늦어지는 전환 병목",
        "",
        "## A. 오늘의 편집 제안",
        "",
    ]

    if not final_rows:
        lines.extend(
            [
                "**오늘은 확정 후보 없음.** 기사 게이트와 시민 장면 기준은 낮추지 않는다.",
                "",
            ]
        )
    else:
        for row in final_rows:
            audit = audit_by_id.get(row.get("item_id", ""), {})
            lines.extend(
                [
                    f"### {markdown(row.get('canonical_topic'))}",
                    "",
                    f"- item_id / 등급: {row.get('item_id')} / {row.get('stage_s')}·{row.get('editorial_e')}·{row.get('production_p')}",
                    f"- 중심 질문: {markdown(audit.get('central_question') or row.get('structural_question'))}",
                    f"- 시민 손실: {markdown(audit.get('citizen_stake'))}",
                    f"- 검증된 새 사실: {markdown(row.get('new_evidence'))}",
                    f"- 근거 계보: {markdown(row.get('source_families'))}",
                    f"- 시민 장면과 상태: {row.get('scene_status')}",
                    f"- 기존 프레임 → 새 질문: {markdown(row.get('source_report'))} → {markdown(audit.get('central_question') or row.get('structural_question'))}",
                    f"- 책임 주체: 검증 기록에서 확인",
                    f"- 현장 A안 / 실패 B안: 대기열의 scene_plan과 대체 데이터 경로 확인",
                    f"- 반증·중단 조건: {markdown(audit.get('decision_rule'))}",
                    "",
                ]
            )

    lines.extend(
        [
            "## B. 오늘 4시간 검증할 아이템",
            "",
            "아래 항목은 **기사 후보가 아니라 당일 검증 과제**다.",
            "",
        ]
    )
    if not verification_rows:
        lines.extend(["오늘 배정할 S1 질문 품질 PASS 항목 없음.", ""])
    else:
        for row in verification_rows:
            item_id = row.get("item_id", "")
            lines.extend(
                render_verification_card(
                    row,
                    queue_by_id[item_id],
                    audit_by_id.get(item_id, {}),
                )
            )

    lines.extend(["## 기한 초과 검증 대기열", ""])
    if not overdue:
        lines.extend(["- 없음", ""])
    else:
        lines.extend(
            [
                "| item_id | 경과 | 현재 병목 | 다음 확인 |",
                "|---|---:|---|---|",
            ]
        )
        for row in overdue:
            item_id = row.get("item_id", "")
            lines.append(
                f"| {item_id} | {overdue_days(row.get('review_by', ''), as_of)}일 | "
                f"{markdown(queue_by_id.get(item_id, {}).get('blocker'))} | "
                f"{markdown(row.get('next_check'))} |"
            )
        lines.append("")

    lines.extend(["## C. 새 질문 원석·후속 관찰", ""])
    if not raw_rows:
        lines.extend(["- 없음", ""])
    else:
        lines.extend(
            [
                "| 현상 | 질문 게이트·점수 | 중심 질문 | 시민 이해관계 | 다음 확인 | S·E |",
                "|---|---|---|---|---|---|",
            ]
        )
        for row in raw_rows:
            audit = audit_by_id.get(row.get("item_id", ""), {})
            lines.append(
                f"| {markdown(row.get('canonical_topic'))} | "
                f"{row.get('question_gate')}·{audit.get('quality_score', '미기록')}/12 | "
                f"{markdown(audit.get('central_question') or row.get('structural_question'))} | "
                f"{markdown(audit.get('citizen_stake'))} | "
                f"{markdown(row.get('next_check'))} | "
                f"{row.get('stage_s')}·{row.get('editorial_e')} |"
            )
        lines.append("")

    editorial_result = (
        "최종 제안" if final_rows else "조건부 후보" if verification_rows else "후보 없음"
    )
    lines.extend(
        [
            "## 실행 판정",
            "",
            "- 탐색 수행 판정: DEGRADED — 이 자동 실행은 장부 편성·기한 추적을 수행했으며 실제 검색·원문 확인·현장 취재는 수행하지 않음",
            f"- 편집 산출 판정: {editorial_result}",
            f"- 실제 수행한 작업: 장부 {len(ledger_rows)}건과 질문 품질 감사표를 대조하고 검증 대기열 {len(queue_rows)}건을 재편성",
            "- 수행하지 않은 작업: 신규 원석 생성, 독창성 검색, 시민 손실·반대 근거 검색, 원문 분석, 당사자·현장 확인",
            "",
            "## 기록 필드 기준",
            "",
            "- 질문 품질 점수 / 중심 질문 / 시민 손실 가설 / 경쟁 가설 / 판정선",
            "- 출처 프레임 / 편집적 추가 / 독창성 게이트 / 왜 지금 유형 / 질문 가족",
            "- 시민 손실 근거 탐색 / 반대 근거 탐색 / 최소 판정 실험",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="서울 기획기사 데일리 브리핑 v5 생성")
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--history-dir", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--as-of", type=date.fromisoformat)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    as_of = args.as_of or datetime.now(ZoneInfo("Asia/Seoul")).date()

    ledger_rows = read_csv(args.ledger)
    audit_rows = read_csv(args.audit)
    audit_by_id = {row.get("item_id", ""): row for row in audit_rows}
    prior_rows = read_csv(args.queue) if args.queue.is_file() else []
    prior_by_id = {row.get("item_id", ""): row for row in prior_rows}

    queue_rows = merge_queue(ledger_rows, audit_by_id, prior_by_id, as_of)
    write_queue(args.queue, queue_rows)

    briefing = render_briefing(ledger_rows, audit_by_id, queue_rows, as_of)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(briefing, encoding="utf-8")

    args.history_dir.mkdir(parents=True, exist_ok=True)
    history_path = args.history_dir / f"briefing_{as_of.isoformat()}.md"
    history_path.write_text(briefing, encoding="utf-8")

    print(f"briefing={args.output}")
    print(f"history={history_path}")
    print(f"verification_queue={len(queue_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
