#!/usr/bin/env python3
"""Build the role-separated daily source feed.

Discovery records remain pre-S0 leads. This script never appends to ITEM_LEDGER.csv
and never upgrades an item stage.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCOUT_PATH = HERE / "scout_sources.py"
OUTPUT = HERE / "output"
QUEUE = HERE / "HUMAN_REVIEW_QUEUE.csv"
DAILY_SOURCE_IDS = {
    "eungdapso",
    "council_minutes",
    "seoul_open_data",
    "seoul_bigdata",
    "seoul_research",
    "labor_arrears",
    "consumer_agency",
}
SUPPLEMENTARY_DISCOVERY_IDS = {
    "eungdapso",
    "seoul_research",
    "labor_arrears",
    "consumer_agency",
}
REVIEW_FIELDS = [
    "first_seen",
    "last_seen",
    "candidate_id",
    "source_revision",
    "auto_active_today",
    "lane",
    "source_id",
    "source_name",
    "ranking_score",
    "auto_evidence_anchor",
    "claim_status",
    "precheck_status",
    "precheck_reason",
    "grounding_status",
    "question_basis",
    "text",
    "question",
    "verification_axes",
    "url",
    "editor_judgment",
    "judgment_reason",
    "editor_evidence_anchor",
    "anchor_detail",
    "anchor_scope",
    "duplicate_parent_id",
    "central_question",
    "citizen_stake",
    "competing_hypotheses",
    "decision_rule",
    "minimum_test",
    "test_timebox_hours",
    "test_pass_rule",
    "test_kill_rule",
    "reviewed_by",
    "reviewed_at",
    "review_revision",
    "transition_state",
    "transitioned_item_id",
    "question_newness",
    "four_hour_testable",
    "notes",
]





def load_scout_module():
    spec = importlib.util.spec_from_file_location("source_scout_runtime", SCOUT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {SCOUT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def concise(text: str, limit: int = 260) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def candidate_id(row: dict) -> str:
    basis = f"{row.get('source_id')}|{row.get('url')}|{concise(row.get('text', ''), 120)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def verification_question(row: dict) -> str:
    return row.get("question") or (
        "이 자료의 실제 값과 분류항목으로 기존 발표의 총량 또는 집중 현상을 검증할 수 있는가?"
    )


def discovery_question(row: dict) -> str:
    anchor = row.get("evidence_anchor") or row.get("signals", {}).get("evidence_anchor", "NONE")
    if anchor == "NONE":
        return "근거 앵커 없음 — 질문 점수 평가 제외"
    return row.get("question") or (
        "확인된 근거를 어떤 범위·기간·비교집단으로 나누면 구조적 차이를 검증할 수 있는가?"
    )



def unique_top(
    rows: list[dict],
    limit: int,
    *,
    dedupe_by: str = "text",
    near_duplicate=None,
) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: item.get("score", 0), reverse=True):
        if dedupe_by == "url":
            key = row.get("url") or row.get("text")
        else:
            key = re.sub(r"[^0-9A-Za-z가-힣]", "", row.get("text", "")).lower()
            key = key or row.get("url")
        if not key or key in seen:
            continue
        if near_duplicate and any(near_duplicate(row, prior) for prior in selected):
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def build_feed(module) -> dict:
    metrics: list[dict] = []
    records: list[dict] = []
    for source in module.SOURCES:
        if source["id"] not in DAILY_SOURCE_IDS:
            continue
        metric, source_records = module.run_source(source)
        metrics.append(metric)
        records.extend(source_records)
        print(
            f"{source['id']}: status={metric['status']} requests={metric['requests']} "
            f"items={metric['extracted']} precheck={metric.get('precheck_pass', 0)} "
            f"grounded={metric.get('grounded', 0)} qualified={metric['qualified']}"
        )

    core = unique_top(
        [
            {**row, "lane": "CORE_DISCOVERY", "question": discovery_question(row)}
            for row in records
            if row["source_id"] == "council_minutes"
            and row.get("qualified")
            and row.get("grounding_status") == "PASS"
        ],
        3,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    auxiliary = unique_top(
        [
            {**row, "lane": "AUX_DISCOVERY", "question": discovery_question(row)}
            for row in records
            if row["source_id"] in SUPPLEMENTARY_DISCOVERY_IDS
            and row.get("qualified")
            and row.get("grounding_status") == "PASS"
        ],
        3,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    verification = unique_top(
        [
            {
                **row,
                "lane": "VERIFICATION_MAP",
                "question": verification_question(row),
            }
            for row in records
            if row["source_id"] in {"seoul_open_data", "seoul_bigdata"}
            and row.get("verification_usable")
            and row.get("grounding_status") == "PASS"
        ],
        4,
        dedupe_by="url",
    )
    verification_schema_leads = unique_top(
        [
            {**row, "lane": "VERIFICATION_SCHEMA_LEAD"}
            for row in records
            if row.get("verification_schema_lead")
            and not row.get("verification_usable")
        ],
        4,
        dedupe_by="url",
    )
    verification_leads = unique_top(
        [
            {**row, "lane": "VERIFICATION_METADATA_LEAD"}
            for row in records
            if row.get("verification_metadata_lead")
            and not row.get("verification_usable")
        ],
        4,
        dedupe_by="url",
    )
    activity_baselines = unique_top(
        [
            {**row, "lane": "ACTIVITY_BASELINE"}
            for row in records
            if row.get("content_class") == "AGGREGATE_ACTIVITY_DASHBOARD"
        ],
        2,
        dedupe_by="url",
    )
    held = unique_top(
        [
            {**row, "lane": "HOLD_FOR_SOURCE_DETAIL"}
            for row in records
            if (
                row.get("content_class") != "AGGREGATE_ACTIVITY_DASHBOARD"
                and (
                    row.get("precheck_status") == "HOLD"
                    or row.get("grounding_status") == "HOLD"
                )
            )
        ],
        5,
    )
    failed_count = sum(row.get("precheck_status") == "FAIL" for row in records)
    return {
        "generated_at_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "status": {
            "discovery_core": "서울시의회 회의록",
            "discovery_auxiliary": [
                "서울시 응답소 공개민원",
                "서울연구원 정책·연구 자료",
                "고용노동부 임금체불 통계",
                "한국소비자원 피해·분쟁 자료",
            ],
            "verification_only": ["서울 열린데이터", "서울 빅데이터캠퍼스"],
            "warning": "근거 앵커와 질문 일치를 통과한 레코드도 S0 이전 질문 씨앗이며 기사 후보가 아님",
        },
        "funnel": {
            "extracted": len(records),
            "precheck_pass": sum(row.get("precheck_status") == "PASS" for row in records),
            "precheck_hold": sum(row.get("precheck_status") == "HOLD" for row in records),
            "precheck_fail": failed_count,
            "grounded": sum(row.get("grounding_status") == "PASS" for row in records),
            "qualified": sum(row.get("qualified") for row in records),
            "selected_discovery": len(core) + len(auxiliary),
            "selected_verification": len(verification),
            "verification_metadata_leads": len(verification_leads),
            "verification_schema_leads": len(verification_schema_leads),
            "activity_baselines": len(activity_baselines),
        },
        "metrics": metrics,
        "core_discovery": core,
        "auxiliary_discovery": auxiliary,
        "activity_baselines": activity_baselines,
        "verification_metadata_leads": verification_leads,
        "verification_schema_leads": verification_schema_leads,
        "verification_map": verification,
        "held_for_source_detail": held,
    }



def read_review_queue() -> list[dict[str, str]]:
    if not QUEUE.is_file():
        return []
    with QUEUE.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def update_review_queue(feed: dict) -> None:
    today = feed["generated_at_kst"][:10]
    prior = read_review_queue()
    by_id: dict[str, dict[str, str]] = {}
    for old in prior:
        normalized = {field: old.get(field, "") for field in REVIEW_FIELDS}
        normalized["ranking_score"] = normalized["ranking_score"] or old.get("auto_score", "")
        normalized["auto_evidence_anchor"] = (
            normalized["auto_evidence_anchor"] or old.get("evidence_anchor", "")
        )
        normalized["auto_active_today"] = "false"
        if normalized["candidate_id"]:
            by_id[normalized["candidate_id"]] = normalized

    for row in feed["core_discovery"] + feed["auxiliary_discovery"]:
        item_id = candidate_id(row)
        current = by_id.get(item_id, {field: "" for field in REVIEW_FIELDS})
        revision_basis = f"{row.get('url', '')}|{concise(row.get('text', ''), 500)}"
        source_revision = hashlib.sha1(revision_basis.encode("utf-8")).hexdigest()[:12]
        current.update(
            {
                "first_seen": current.get("first_seen") or today,
                "last_seen": today,
                "candidate_id": item_id,
                "source_revision": source_revision,
                "auto_active_today": "true",
                "lane": row["lane"],
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "ranking_score": str(row["score"]),
                "auto_evidence_anchor": row.get("evidence_anchor", "NONE"),
                "claim_status": row.get("claim_status", "UNRESOLVED"),
                "precheck_status": row.get("precheck_status", ""),
                "precheck_reason": row.get("precheck_reason", ""),
                "grounding_status": row.get("grounding_status", ""),
                "question_basis": concise(row.get("question_basis", ""), 500),
                "text": concise(row["text"], 500),
                "question": row["question"],
                "verification_axes": ", ".join(row.get("verification_axes", [])),
                "url": row["url"],
            }
        )
        by_id[item_id] = current

    ordered = sorted(
        by_id.values(),
        key=lambda row: (row.get("first_seen", ""), row.get("candidate_id", "")),
        reverse=True,
    )
    with QUEUE.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(ordered)



def render_markdown(feed: dict) -> str:
    funnel = feed.get("funnel", {})
    lines = [
        "# 역할 분리형 신규 소스 입력",
        "",
        f"- 생성: {feed['generated_at_kst']}",
        "- 상태: 아래 발굴 단서는 모두 S0 이전이며 자동으로 아이템 장부에 들어가지 않음",
        "- 자동 점수: 수집 정렬용이며 편집 승인 점수가 아님",
        "",
        "## 오늘의 변환 깔때기",
        "",
        "| 추출 | 사전통과 | 보류 | 제외 | 질문-근거 일치 | 자동 유효 | 편집 판정 카드 | 활동 기준선 | 제목 후보 | 스키마 후보 | 실제값 검증자료 |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        (
            f"| {funnel.get('extracted', 0)} | {funnel.get('precheck_pass', 0)} | "
            f"{funnel.get('precheck_hold', 0)} | {funnel.get('precheck_fail', 0)} | "
            f"{funnel.get('grounded', 0)} | {funnel.get('qualified', 0)} | "
            f"{funnel.get('selected_discovery', 0)} | {funnel.get('activity_baselines', 0)} | "
            f"{funnel.get('verification_metadata_leads', 0)} | "
            f"{funnel.get('verification_schema_leads', 0)} | "
            f"{funnel.get('selected_verification', 0)} |"
        ),
        "",
        "## 오늘 판정이 필요한 카드",
        "",
    ]
    candidates = feed["core_discovery"] + feed["auxiliary_discovery"]
    if not candidates:
        lines.extend(
            [
                "- 오늘 자동 기준을 통과한 질문 씨앗 없음",
                "- 이는 '현상이 없음'이 아니라 위 깔때기에서 수집 실패·본문 부족·오탐 제외·질문 불일치 중 어디서 막혔는지 확인해야 한다는 뜻임",
                "",
            ]
        )
    else:
        for index, row in enumerate(candidates, 1):
            item_id = candidate_id(row)
            axes = ", ".join(row.get("verification_axes", [])) or "추가 설계 필요"
            recommendation = "PROMISING 검토" if (
                row.get("evidence_anchor") in {"MEASURED_PROBLEM_SIGNAL", "DECOMPOSABLE_STRUCTURE"}
                and row.get("grounding_status") == "PASS"
                and row.get("claim_status") == "OBSERVED_OR_PUBLISHED"
            ) else "VERIFY 검토"
            lines.extend(
                [
                    f"### 판정 카드 {index} · {item_id}",
                    "",
                    f"- 관찰된 사실: {concise(row.get('question_basis') or row['text'], 320)}",
                    f"- 자동 분류: {row.get('evidence_anchor', 'NONE')} · {row.get('claim_status', 'UNRESOLVED')} — 사람 판정 아님",
                    f"- 제안 질문: {row['question']}",
                    f"- 아직 확인할 변수: {axes}",
                    f"- 질문-근거 일치: {row.get('grounding_status', 'HOLD')}",
                    f"- 시스템 추천: {recommendation}",
                    f"- 수집 정렬점수: {row['score']} (편집점수 아님)",
                    f"- 출처: {row.get('source_name', row.get('source_id', '미상'))}",
                    f"- 원문: {row['url']}",
                    "- 선택: PROMISING / VERIFY / NOISE / DUPLICATE",
                    "- 현재 전이: 미승인 — 장부 변경 없음",
                    "",
                ]
            )

    lines.extend(["## 활동량 기준선 · 후보 아님", ""])
    baselines = feed.get("activity_baselines", [])
    if not baselines:
        lines.extend(["- 오늘 저장된 활동량 기준선 없음", ""])
    else:
        for row in baselines:
            lines.append(
                f"- {concise(row['text'], 180)} — 단일 총량만으로 이상 현상 판정 금지; "
                "누적된 전일·전월 기준선과 비교한 뒤에만 신호 생성"
            )
        lines.append("")

    lines.extend(["## 본문 근거 보완 대기", ""])
    held = feed.get("held_for_source_detail", [])
    if not held:
        lines.extend(["- 보완 대기 항목 없음", ""])
    else:
        for row in held:
            lines.append(
                f"- {concise(row['text'], 140)} — {row.get('precheck_reason', '근거 확인 필요')} "
                f"([{row.get('source_name', '원문')}]({row.get('url', '')}))"
            )
        lines.append("")

    lines.extend(["## 데이터 구조 확인 · 실제 값 미수집", ""])
    schema_leads = feed.get("verification_schema_leads", [])
    if not schema_leads:
        lines.extend(["- 오늘 구조만 확인된 데이터셋 없음", ""])
    else:
        for row in schema_leads:
            lines.append(
                f"- {concise(row['text'], 160)} — 분류·갱신 구조만 확인; 실제 데이터 행 수집 전 검증 자산 사용 금지 "
                f"([{row.get('source_name', '원문')}]({row.get('url', '')}))"
            )
        lines.append("")

    lines.extend(["## 데이터셋 후보 · 스키마·값 미확인", ""])
    metadata_leads = feed.get("verification_metadata_leads", [])
    if not metadata_leads:
        lines.extend(["- 오늘 확인 대기 중인 데이터셋 제목 없음", ""])
    else:
        for row in metadata_leads:
            lines.append(
                f"- {concise(row['text'], 140)} — 제목만 발견; 컬럼·실제 값 확인 전에는 검증 자산으로 사용 금지 "
                f"([{row.get('source_name', '원문')}]({row.get('url', '')}))"
            )
        lines.append("")

    lines.extend(["## 검증 데이터 지도", ""])
    if not feed["verification_map"]:
        lines.extend(["- 오늘 연결할 검증 자료 없음", ""])
    else:
        lines.extend(
            [
                "| 자료 | 검증 질문 | 원문 |",
                "|---|---|---|",
            ]
        )
        for row in feed["verification_map"]:
            lines.append(
                f"| {concise(row['text'], 120).replace('|', '·')} | "
                f"{row['question']} | {row['url']} |"
            )
        lines.append("")

    lines.extend(["## 수집 상태", ""])
    lines.extend(
        [
            "| 소스 | 접속 | 상태 진단 | 요청/실패 | 추출 | 사전통과 | 질문일치 | 자동 유효 |",
            "|---|---:|---|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in feed["metrics"]:
        access = f"HTTP {metric['status']}" if metric["http_ok"] else metric["error"]
        lines.append(
            f"| {metric['name']} | {access} | {metric.get('status_detail', '-')} | "
            f"{metric['requests']}/{metric['failed_requests']} | {metric['extracted']} | "
            f"{metric.get('precheck_pass', 0)} | {metric.get('grounded', 0)} | "
            f"{metric['qualified']} |"
        )
    lines.append("")
    return "\n".join(lines)



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-review-queue", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    module = load_scout_module()
    feed = build_feed(module)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "daily_feed_latest.json").write_text(
        json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT / "daily_feed_latest.md").write_text(render_markdown(feed), encoding="utf-8")
    history = OUTPUT / "history"
    history.mkdir(parents=True, exist_ok=True)
    run_day = feed["generated_at_kst"][:10]
    run_key = os.environ.get("GITHUB_RUN_ID") or feed["generated_at_kst"][11:19].replace(":", "")
    (history / f"daily_feed_{run_day}_{run_key}.json").write_text(
        json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not args.skip_review_queue:
        update_review_queue(feed)
    print(f"feed={OUTPUT / 'daily_feed_latest.json'}")
    print(f"review_queue={QUEUE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
