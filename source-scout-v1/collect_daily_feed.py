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
NATIONAL_LOCALIZATION_IDS = {"labor_arrears", "consumer_agency"}
REVIEW_FIELDS = [
    "first_seen",
    "last_seen",
    "candidate_id",
    "source_revision",
    "source_revision_history",
    "auto_active_today",
    "review_eligible",
    "lane",
    "context_status",
    "context_rule",
    "context_subject",
    "context_trigger",
    "context_text",
    "context_reason",
    "context_missing_fields",
    "source_type",
    "speech_type",
    "speech_type_label",
    "speaker",
    "affected_group",
    "geography",
    "sector_scope",
    "scope_exclusion",
    "speech_date",
    "event_period",
    "context_period",
    "metric_scope",
    "metric_period",
    "metric_period_status",
    "metric_source_status",
    "statement_label",
    "display_fact",
    "evidence_values",
    "source_id",
    "source_name",
    "source_date",
    "freshness_days",
    "freshness_window_days",
    "freshness_status",
    "cadence",
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


CLAIM_STATUS_LABELS = {
    "ATTRIBUTED_CLAIM": "의원 발언에서 제시",
    "OBSERVED_OR_PUBLISHED": "원자료에 공개된 값",
    "UNRESOLVED": "확인 수준 미분류",
}
METRIC_SOURCE_LABELS = {
    "SPEAKER_ONLY": "산정 원자료 미확인",
    "CITED_SOURCE_UNCHECKED": "인용 원자료 대조 전",
    "INDEPENDENTLY_VERIFIED": "원자료 재확인 완료",
}
METRIC_PERIOD_LABELS = {
    "EXPLICIT": "발언문에 기간 명시",
    "RELATIVE_TO_DOCUMENT": "발언 당시 기준",
    "UNKNOWN": "기준기간 확인 필요",
    "NOT_APPLICABLE": "정량 수치 없음",
}


def status_label(mapping: dict[str, str], value: str) -> str:
    return mapping.get(value, value or "미확인")


def candidate_id(row: dict) -> str:
    basis = f"{row.get('source_id')}|{row.get('url')}|{concise(row.get('text', ''), 120)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def source_revision_for_row(row: dict) -> str:
    normalized_text = " ".join(str(row.get("text", "")).split())
    context_signature = "|".join(
        " ".join(str(row.get(field, "")).split())
        for field in (
            "context_status",
            "context_rule",
            "context_subject",
            "context_trigger",
            "context_text",
            "speaker",
            "speech_type",
            "sector_scope",
            "scope_exclusion",
            "speech_date",
            "event_period",
            "context_period",
            "metric_scope",
            "metric_period",
            "metric_period_status",
            "metric_source_status",
        )
    )
    basis = (
        f"{row.get('source_id', '')}|{row.get('url', '')}|"
        f"{normalized_text}|{context_signature}"
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def revision_history_values(row: dict) -> set[str]:
    values = {
        value.strip()
        for value in str(row.get("source_revision_history", "")).split("|")
        if value.strip()
    }
    current = str(row.get("source_revision", "")).strip()
    if current:
        values.add(current)
    return values

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


def localization_question(row: dict) -> str:
    return (
        "이 전국 현상이 서울에서도 확인되는가? 서울 원자료로 규모·분포·피해 대상을 "
        "재현하고 전국 평균과의 차이를 설명할 수 있는가?"
    )



def is_fresh(row: dict) -> bool:
    return row.get("freshness_status") == "FRESH"


def is_freshness_hold(row: dict) -> bool:
    status = row.get("freshness_status") or "FRESHNESS_UNKNOWN"
    return status in {"FRESHNESS_UNKNOWN", "FUTURE_DATED"}


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


def council_context_pass(row: dict) -> bool:
    return (
        row.get("source_id") != "council_minutes"
        or row.get("context_status") == "PASS"
    )


def fail_closed_council_context(row: dict) -> None:
    if row.get("source_id") != "council_minutes":
        return
    if row.get("context_status") == "PASS":
        return
    row["context_status"] = "HOLD"
    row["qualified"] = False
    row["localization_lead"] = False
    row["grounding_status"] = "HOLD"
    row.setdefault("context_rule", "UNLOCKED")
    row.setdefault(
        "context_reason",
        "서울시의회 행에 발언 블록 문맥이 없어 질문 생성 금지",
    )
    row.setdefault(
        "context_missing_fields",
        ["발언자", "정확한 사안", "서울·자치구 적용 범위", "영향 대상·부담 주체"],
    )
    row["question"] = (
        "문맥 잠금 미완료 — 사건·대상·수치 범위·기준기간을 "
        "확인한 뒤 질문 생성"
    )



def qualification_paths(
    records: list[dict],
    prior_source_revisions: set[str],
    metrics: list[dict],
) -> dict:
    """Explain the qualified-to-new funnel without relaxing any selection gate."""
    paths = {
        "qualified": 0,
        "fresh_new": 0,
        "fresh_repeat": 0,
        "stale": 0,
        "archived": 0,
        "date_hold": 0,
    }
    by_source: dict[str, dict[str, int]] = {}
    for row in records:
        if not row.get("qualified"):
            continue
        source_id = row.get("source_id", "")
        source_paths = by_source.setdefault(
            source_id, {key: 0 for key in paths}
        )
        status = row.get("freshness_status")
        if status == "FRESH":
            key = (
                "fresh_repeat"
                if source_revision_for_row(row) in prior_source_revisions
                else "fresh_new"
            )
        elif status == "STALE_CARRYOVER":
            key = "stale"
        elif status == "ARCHIVED_STALE":
            key = "archived"
        else:
            key = "date_hold"
        paths["qualified"] += 1
        source_paths["qualified"] += 1
        paths[key] += 1
        source_paths[key] += 1
    failed_sources = [
        {"source_id": metric.get("source_id", ""), "reason": metric.get("error", "")}
        for metric in metrics
        if not metric.get("http_ok")
    ]
    return {
        **paths,
        "by_source": by_source,
        "failed_sources": failed_sources,
        "zero_new_reason": (
            "NO_NEW_FRESH_QUALIFIED" if paths["fresh_new"] == 0 else ""
        ),
        "note": "원자료 판정 경로이며 후보 상한·근접중복 선별 전의 건수",
    }


def build_feed(
    module,
    prior_source_revisions: set[str] | None = None,
) -> dict:
    prior_source_revisions = prior_source_revisions or set()
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

    for row in records:
        fail_closed_council_context(row)

    core = unique_top(
        [
            {**row, "lane": "CORE_DISCOVERY", "question": discovery_question(row)}
            for row in records
            if row["source_id"] == "council_minutes"
            and row.get("qualified")
            and row.get("grounding_status") == "PASS"
            and row.get("context_status") == "PASS"
            and is_fresh(row)
            and source_revision_for_row(row) not in prior_source_revisions
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
            and is_fresh(row)
            and source_revision_for_row(row) not in prior_source_revisions
        ],
        3,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    localization = unique_top(
        [
            {
                **row,
                "lane": "LOCALIZE_TO_SEOUL",
                "question": localization_question(row),
            }
            for row in records
            if row["source_id"] in NATIONAL_LOCALIZATION_IDS
            and row.get("localization_lead")
            and row.get("grounding_status") == "PASS"
            and is_fresh(row)
            and source_revision_for_row(row) not in prior_source_revisions
        ],
        2,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    rediscovered_carryover = unique_top(
        [
            {**row, "lane": "REDISCOVERED_CARRYOVER", "question": discovery_question(row)}
            for row in records
            if row["source_id"] in (SUPPLEMENTARY_DISCOVERY_IDS | {"council_minutes"})
            and (row.get("qualified") or row.get("localization_lead"))
            and row.get("grounding_status") == "PASS"
            and council_context_pass(row)
            and is_fresh(row)
            and source_revision_for_row(row) in prior_source_revisions
        ],
        5,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    stale_carryover = unique_top(
        [
            {**row, "lane": "STALE_CARRYOVER", "question": discovery_question(row)}
            for row in records
            if row["source_id"] in (SUPPLEMENTARY_DISCOVERY_IDS | {"council_minutes"})
            and (row.get("qualified") or row.get("localization_lead"))
            and row.get("grounding_status") == "PASS"
            and council_context_pass(row)
            and row.get("freshness_status") == "STALE_CARRYOVER"
        ],
        5,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    context_holds = unique_top(
        [
            {
                **row,
                "lane": "CONTEXT_HOLD",
                "question": (
                    "문맥 잠금 미완료 — 사건·대상·수치 범위·기준기간을 확인한 뒤 질문 생성"
                ),
            }
            for row in records
            if row.get("source_id") == "council_minutes"
            and row.get("context_status") != "PASS"
        ],
        8,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    freshness_holds = unique_top(
        [
            {**row, "lane": "FRESHNESS_HOLD", "question": discovery_question(row)}
            for row in records
            if row["source_id"] in (SUPPLEMENTARY_DISCOVERY_IDS | {"council_minutes"})
            and (row.get("qualified") or row.get("localization_lead"))
            and row.get("grounding_status") == "PASS"
            and council_context_pass(row)
            and is_freshness_hold(row)
        ],
        5,
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
    archived_stale = unique_top(
        [
            {**row, "lane": "ARCHIVED_STALE"}
            for row in records
            if row["source_id"] in (SUPPLEMENTARY_DISCOVERY_IDS | {"council_minutes"})
            and (row.get("qualified") or row.get("localization_lead"))
            and row.get("grounding_status") == "PASS"
            and council_context_pass(row)
            and row.get("freshness_status") == "ARCHIVED_STALE"
        ],
        5,
        near_duplicate=getattr(module, "near_duplicate_context", None),
    )
    held = unique_top(
        [
            {**row, "lane": "HOLD_FOR_SOURCE_DETAIL"}
            for row in records
            if (
                row.get("content_class") != "AGGREGATE_ACTIVITY_DASHBOARD"
                and row.get("context_status") != "HOLD"
                and (
                    row.get("precheck_status") == "HOLD"
                    or row.get("grounding_status") == "HOLD"
                )
            )
        ],
        5,
    )
    failed_count = sum(row.get("precheck_status") == "FAIL" for row in records)
    paths = qualification_paths(records, prior_source_revisions, metrics)
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
            "freshness_policy_days": getattr(module, "FRESHNESS_POLICY_DAYS", {}),
            "warning": "근거 앵커와 질문 일치를 통과한 레코드도 S0 이전 질문 씨앗이며 기사 후보가 아님",
        },
        "funnel": {
            "extracted": len(records),
            "precheck_pass": sum(row.get("precheck_status") == "PASS" for row in records),
            "precheck_hold": sum(row.get("precheck_status") == "HOLD" for row in records),
            "precheck_fail": failed_count,
            "grounded": sum(row.get("grounding_status") == "PASS" for row in records),
            "qualified": sum(row.get("qualified") for row in records),
            "fresh_qualified": sum(
                row.get("qualified") and is_fresh(row) for row in records
            ),
            "selected_discovery": len(core) + len(auxiliary),
            "selected_localization": len(localization),
            "rediscovered_carryover": len(rediscovered_carryover),
            "stale_carryover": len(stale_carryover),
            "archived_stale": sum(
                row.get("freshness_status") == "ARCHIVED_STALE" for row in records
            ),
            "freshness_holds": len(freshness_holds),
            "context_holds": len(context_holds),
            "selected_verification": len(verification),
            "verification_metadata_leads": len(verification_leads),
            "verification_schema_leads": len(verification_schema_leads),
            "activity_baselines": len(activity_baselines),
        },
        "metrics": metrics,
        "qualification_paths": paths,
        "core_discovery": core,
        "auxiliary_discovery": auxiliary,
        "localization_discovery": localization,
        "rediscovered_carryover": rediscovered_carryover,
        "stale_carryover": stale_carryover,
        "archived_stale": archived_stale,
        "freshness_holds": freshness_holds,
        "context_holds": context_holds,
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
        normalized["review_eligible"] = "false"
        if normalized["candidate_id"]:
            by_id[normalized["candidate_id"]] = normalized

    queue_rows = (
        feed["core_discovery"]
        + feed["auxiliary_discovery"]
        + feed.get("localization_discovery", [])
        + feed.get("rediscovered_carryover", [])
    )
    for row in queue_rows:
        item_id = candidate_id(row)
        current = by_id.get(item_id, {field: "" for field in REVIEW_FIELDS})
        source_revision = source_revision_for_row(row)
        revision_history = revision_history_values(current)
        revision_history.add(source_revision)
        active_today = row.get("lane") in {"CORE_DISCOVERY", "AUX_DISCOVERY"}
        reviewed_current_revision = bool(current.get("editor_judgment", "").strip()) and (
            current.get("review_revision", "").strip() == source_revision
        )
        review_eligible = active_today or (
            row.get("lane") == "REDISCOVERED_CARRYOVER"
            and reviewed_current_revision
        )
        current.update(
            {
                "first_seen": current.get("first_seen") or today,
                "last_seen": today,
                "candidate_id": item_id,
                "source_revision": source_revision,
                "source_revision_history": "|".join(sorted(revision_history)),
                "auto_active_today": "true" if active_today else "false",
                "review_eligible": "true" if review_eligible else "false",
                "lane": (
                    "LOCALIZE_TO_SEOUL"
                    if row.get("localization_lead") and not row.get("seoul_scope")
                    else row["lane"]
                ),
                "context_status": str(row.get("context_status", "")),
                "context_rule": str(row.get("context_rule", "")),
                "context_subject": str(row.get("context_subject", "")),
                "context_trigger": str(row.get("context_trigger", "")),
                "context_text": concise(row.get("context_text", ""), 800),
                "context_reason": str(row.get("context_reason", "")),
                "context_missing_fields": ", ".join(
                    row.get("context_missing_fields", [])
                ),
                "source_type": str(row.get("source_type", "")),
                "speech_type": str(row.get("speech_type", "")),
                "speech_type_label": str(row.get("speech_type_label", "")),
                "speaker": str(row.get("speaker", "")),
                "affected_group": str(row.get("affected_group", "")),
                "geography": str(row.get("geography", "")),
                "sector_scope": str(row.get("sector_scope", "")),
                "scope_exclusion": str(row.get("scope_exclusion", "")),
                "speech_date": str(row.get("speech_date", "")),
                "event_period": str(row.get("event_period", "")),
                "context_period": str(row.get("context_period", "")),
                "metric_scope": str(row.get("metric_scope", "")),
                "metric_period": str(row.get("metric_period", "")),
                "metric_period_status": str(
                    row.get("metric_period_status", "")
                ),
                "metric_source_status": str(
                    row.get("metric_source_status", "")
                ),
                "statement_label": str(row.get("statement_label", "")),
                "display_fact": concise(row.get("display_fact", ""), 800),
                "evidence_values": ", ".join(row.get("evidence_values", [])),
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "source_date": str(row.get("source_date", "")),
                "freshness_days": str(row.get("freshness_days", "")),
                "freshness_window_days": str(row.get("freshness_window_days", "")),
                "freshness_status": str(row.get("freshness_status") or "FRESHNESS_UNKNOWN"),
                "cadence": str(row.get("cadence", "")),
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
        "- 오늘 카드: 원문 날짜가 소스 주기별 신선도 창 안에 있는 항목만 포함",
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
        (
            f"- 신선도 게이트: 신선 유효 {funnel.get('fresh_qualified', 0)}건 · "
            f"오늘 카드 {funnel.get('selected_discovery', 0)}건 · "
            f"서울 지역화 대기 {funnel.get('selected_localization', 0)}건 · "
            f"동일 원문 재등장 {funnel.get('rediscovered_carryover', 0)}건 · "
            f"STALE {funnel.get('stale_carryover', 0)}건 · "
            f"보관 종료 {funnel.get('archived_stale', 0)}건 · "
            f"날짜 확인 대기 {funnel.get('freshness_holds', 0)}건 · "
            f"문맥 확인 대기 {funnel.get('context_holds', 0)}건"
        ),
        "",
        "## 유효 원문이 오늘 후보로 이어진 경로",
        "",
        (
            f"- 자동 유효 {feed['qualification_paths']['qualified']}건 → "
            f"오늘 새 원문 {feed['qualification_paths']['fresh_new']}건 · "
            f"이미 본 원문 {feed['qualification_paths']['fresh_repeat']}건 · "
            f"신선도 초과 {feed['qualification_paths']['stale']}건 · "
            f"보관 종료 {feed['qualification_paths']['archived']}건 · "
            f"날짜 보류 {feed['qualification_paths']['date_hold']}건"
        ),
        "- 이 수치는 원자료 기준이며 후보 상한·근접중복 선별 전입니다.",
        *[
            (
                f"- {source_id}: 유효 {counts['qualified']}건 · "
                f"새 원문 {counts['fresh_new']}건 · "
                f"기존 원문 {counts['fresh_repeat']}건 · "
                f"신선도 초과 {counts['stale']}건 · "
                f"보관 종료 {counts['archived']}건"
            )
            for source_id, counts in sorted(
                feed["qualification_paths"]["by_source"].items()
            )
        ],
        *[
            f"- 수집 실패: {item['source_id']} — {item['reason']}"
            for item in feed["qualification_paths"]["failed_sources"]
        ],
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
            fact_label = row.get("statement_label") or (
                "원자료에서 확인된 수치"
                if row.get("claim_status") == "OBSERVED_OR_PUBLISHED"
                else "제시된 내용"
            )
            is_council = row.get("source_id") == "council_minutes"
            claim_level = status_label(
                CLAIM_STATUS_LABELS,
                row.get("claim_status", "UNRESOLVED"),
            )
            if is_council:
                event = " · ".join(
                    value for value in (
                        row.get("context_subject", ""),
                        row.get("context_trigger", ""),
                    ) if value
                )
                source_level = " · ".join(
                    value for value in (
                        row.get("speaker", ""),
                        row.get("speech_type_label", ""),
                        claim_level,
                        status_label(
                            METRIC_SOURCE_LABELS,
                            row.get("metric_source_status", ""),
                        ),
                    ) if value
                )
                context_lines = [
                    f"- 무슨 일: {event or '사안 미확인'}",
                    f"- 적용 범위: {row.get('sector_scope') or '확인 필요'}",
                    f"- 영향 확인 대상: {row.get('affected_group') or '확인 필요'}",
                    f"- {fact_label}: {concise(row.get('display_fact') or row.get('question_basis') or row['text'], 320)}",
                    (
                        f"- 수치 범위·기준: {row.get('metric_scope') or '정량 수치 없음'} · "
                        f"{row.get('metric_period') or '확인 필요'} "
                        f"({status_label(METRIC_PERIOD_LABELS, row.get('metric_period_status', 'UNKNOWN'))})"
                    ),
                    f"- 출처·확인 수준: {source_level}",
                    f"- 회의록 문서일: {row.get('speech_date') or '미확인'}",
                    f"- 범위 주의: {row.get('scope_exclusion') or '별도 주의 없음'}",
                ]
            else:
                context_lines = [
                    "- 사안·범위: 별도 문맥 잠금 불필요",
                    f"- {fact_label}: {concise(row.get('display_fact') or row.get('question_basis') or row['text'], 320)}",
                    f"- 출처·확인 수준: {row.get('source_name', row.get('source_id', '미상'))} · {claim_level}",
                ]
            lines.extend(
                [
                    f"### 판정 카드 {index} · {item_id}",
                    "",
                    *context_lines,
                    f"- 자동 분류: {row.get('evidence_anchor', 'NONE')} · {claim_level} — 사람 판정 아님",
                    f"- 제안 질문: {row['question']}",
                    f"- 아직 확인할 변수: {axes}",
                    f"- 질문-근거 일치: {row.get('grounding_status', 'HOLD')}",
                    f"- 시스템 추천: {recommendation}",
                    f"- 수집 정렬점수: {row['score']} (편집점수 아님)",
                    f"- 출처: {row.get('source_name', row.get('source_id', '미상'))}",
                    f"- 원문 최신일: {row.get('source_date', '미상')} · 경과 {row.get('freshness_days', '미상')}일 · 허용창 {row.get('freshness_window_days', '미상')}일",
                    f"- 원문: {row['url']}",
                    "- 선택: PROMISING / VERIFY / NOISE / DUPLICATE",
                    "- 현재 전이: 미승인 — 장부 변경 없음",
                    "",
                ]
            )

    context_holds = feed.get("context_holds", [])
    lines.extend(["## 문맥 확인 대기 · 질문 생성 금지", ""])
    if not context_holds:
        lines.extend(["- 정확한 사건·대상 범위가 비어 보류된 의회 단서 없음", ""])
    else:
        for row in context_holds:
            missing = ", ".join(row.get("context_missing_fields", [])) or "세부 문맥"
            lines.extend(
                [
                    f"- 발언 조각: {concise(row.get('text', ''), 220)}",
                    f"- 보류 이유: {row.get('context_reason') or '문맥 잠금 미완료'}",
                    f"- 빠진 항목: {missing}",
                    f"- 회의록 문서일: {row.get('speech_date') or '미확인'}",
                    f"- 원문: {row.get('url', '')}",
                    "",
                ]
            )

    localization = feed.get("localization_discovery", [])
    lines.extend(["## 서울 지역화 대기 · 서울 근거 확보 전 S0 불가", ""])
    if not localization:
        lines.extend(["- 오늘 서울 자료로 재확인할 전국 단서 없음", ""])
    else:
        for row in localization:
            lines.extend(
                [
                    f"- 전국 단서: {concise(row.get('question_basis') or row['text'], 260)}",
                    f"- 서울 검증 질문: {row['question']}",
                    f"- 출처: {row.get('source_name', row.get('source_id', '미상'))}",
                    f"- 원문: {row['url']}",
                    "- 상태: 서울 수치 미확보 — 편집 카드·S0 전이 대상 아님",
                    "",
                ]
            )

    rediscovered = feed.get("rediscovered_carryover", [])
    lines.extend(["## 동일 원문 재등장 · 오늘 새 카드 제외", ""])
    if not rediscovered:
        lines.extend(["- 이전 실행과 동일한 원문·날짜의 재등장 없음", ""])
    else:
        for row in rediscovered:
            lines.append(
                f"- {concise(row.get('question_basis') or row.get('text', ''), 180)} — "
                "이전과 같은 원문 지문; 새 카드·자동 재활성화·S0 제안 제외"
            )
        lines.append("")
    stale = feed.get("stale_carryover", [])
    lines.extend(["## STALE_CARRYOVER · 오늘 판정 제외", ""])
    if not stale:
        lines.extend(["- 신선도 창을 넘긴 유효 단서 없음", ""])
    else:
        for row in stale:
            lines.append(
                f"- {concise(row.get('question_basis') or row.get('text', ''), 180)} — "
                f"{row.get('source_date', '날짜 미상')} 기준 {row.get('freshness_days', '?')}일 경과; "
                "근거는 보관하되 오늘 카드·재활성화·S0 제안에서 제외"
            )
        lines.append("")

    archived = feed.get("archived_stale", [])
    lines.extend(["## 보관 종료 단서 · 감사용 표본", ""])
    if not archived:
        lines.extend(["- 보관 기한을 넘긴 유효 단서 표본 없음", ""])
    else:
        for row in archived:
            lines.append(
                f"- {concise(row.get('question_basis') or row.get('text', ''), 180)} — "
                f"{row.get('source_date', '날짜 미상')} 기준 {row.get('freshness_days', '?')}일 경과; "
                f"오늘 후보 제외, 감사용 원문: {row.get('url', '')}"
            )
        lines.append("")

    freshness_holds = feed.get("freshness_holds", [])
    lines.extend(["## 날짜 확인 대기 · 오늘 판정 제외", ""])
    if not freshness_holds:
        lines.extend(["- 날짜를 확인하지 못한 유효 단서 없음", ""])
    else:
        for row in freshness_holds:
            lines.append(
                f"- {concise(row.get('question_basis') or row.get('text', ''), 180)} — "
                f"{row.get('freshness_status', 'FRESHNESS_UNKNOWN')}; 원문 날짜 확인 전 후보 제외"
            )
        lines.append("")
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
                f"(자료일 {row.get('source_date') or '미상'} · {row.get('freshness_status') or 'FRESHNESS_UNKNOWN'}) "
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
                f"(자료일 {row.get('source_date') or '미상'} · {row.get('freshness_status') or 'FRESHNESS_UNKNOWN'}) "
                f"([{row.get('source_name', '원문')}]({row.get('url', '')}))"
            )
        lines.append("")

    lines.extend(["## 검증 데이터 지도", ""])
    if not feed["verification_map"]:
        lines.extend(["- 오늘 연결할 검증 자료 없음", ""])
    else:
        lines.extend(
            [
                "| 자료 | 자료일·상태 | 검증 질문 | 원문 |",
                "|---|---|---|---|",
            ]
        )
        for row in feed["verification_map"]:
            lines.append(
                f"| {concise(row['text'], 120).replace('|', '·')} | "
                f"{row.get('source_date') or '미상'} · {row.get('freshness_status') or 'FRESHNESS_UNKNOWN'} | "
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
    prior_revisions: set[str] = set()
    for row in read_review_queue():
        prior_revisions.update(revision_history_values(row))
    feed = build_feed(module, prior_revisions)
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
