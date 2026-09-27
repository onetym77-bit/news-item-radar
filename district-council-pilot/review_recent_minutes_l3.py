#!/usr/bin/env python3
"""Bounded L3 shadow review for recent, unreviewed district-council minutes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from collect_body_l2 import collect as collect_l2
from collect_pilot import Client, KST, day, detail_from, norm, transcript
from interpret_l3_context import (
    assessment_reason,
    call_desk,
    call_model,
    desk_context,
    semantic_status_label,
    validate_assessment,
    validate_desk_response,
)
from watch_new_minutes import record_key

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output" / "recent-l3"
WATCH = BASE / "output" / "watch" / "state_latest.json"
HISTORY = OUTPUT / "reviewed_documents.json"
FIXED = BASE / "l3_fixed_sample_2026-09-22.json"
MAX_DOCS = 5
VALID_FINAL = {"REVIEW", "HOLD", "NO_SIGNAL"}


def empty_history():
    return {"schema": 1, "reviewed_documents": []}


def load_history(path):
    if not path.is_file():
        return empty_history()
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != 1 or not isinstance(value.get("reviewed_documents"), list):
        raise ValueError("Unsupported recent L3 history")
    keys = [row.get("key") for row in value["reviewed_documents"]]
    if any(not re.fullmatch(r"[0-9a-f]{24}", key or "") for key in keys):
        raise ValueError("Invalid recent L3 history key")
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate recent L3 history key")
    return value


def select_plan(l2_payload, watch_state, history, fixed_sample, as_of, max_docs=MAX_DOCS):
    if l2_payload.get("source_count") != 25 or len(l2_payload.get("results", [])) != 25:
        raise ValueError("Expected current L2 results for all 25 councils")
    if not 0 <= max_docs <= MAX_DOCS:
        raise ValueError("Recent L3 document limit exceeded")
    reviewed = {row["key"] for row in history["reviewed_documents"]}
    fixed = {record_key(row["document_url"]) for row in fixed_sample.get("documents", [])}
    fresh = {
        candidate["key"]
        for source in watch_state.get("last_run", {}).get("results", [])
        if source.get("status") == "NEW_IN_VISIBLE_WINDOW"
        for candidate in source.get("candidates", [])
    }
    eligible = []
    for row in l2_payload["results"]:
        url = row.get("document_url", "")
        meeting_date = row.get("meeting_date", "")
        if row.get("status") != "BODY_METADATA_MATCH" or not url or not meeting_date:
            continue
        if row.get("provisional") or date.fromisoformat(meeting_date) > as_of:
            continue
        key = record_key(url)
        if key in reviewed or key in fixed:
            continue
        eligible.append({
            "key": key,
            "source_id": row["source_id"],
            "source_name": row["source_name"],
            "document_url": url,
            "meeting_date": meeting_date,
            "body_sha256": row["body_sha256"],
            "selection_reason": (
                "NEW_IN_VISIBLE_WINDOW" if key in fresh
                else "LATEST_UNREVIEWED_BOOTSTRAP"
            ),
        })
    eligible.sort(key=lambda row: (
        row["selection_reason"] != "NEW_IN_VISIBLE_WINDOW",
        -date.fromisoformat(row["meeting_date"]).toordinal(),
        row["source_id"],
    ))
    return eligible[:max_docs]


def fetch_document(row, source):
    client = Client(source)
    outer = client.get(row["document_url"])
    if outer is None:
        return {"status": "FETCH_FAILED", "body": "", "parts": [],
                "request_status": client.logs[-1]["status"] if client.logs else 0}
    outer_title_date = day(norm(" ".join(outer.title)))
    page = outer
    body, parts = transcript(page)
    if not body:
        inner = detail_from([("src", url) for url in page.frames], row["document_url"], source)
        if inner and inner != row["document_url"]:
            framed = client.get(inner)
            if framed:
                body, parts = transcript(framed)
    if not body:
        return {"status": "BODY_UNAVAILABLE", "body": "", "parts": [],
                "request_status": client.logs[-1]["status"]}
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if outer_title_date and outer_title_date != row["meeting_date"]:
        status = "DATE_CONFLICT"
    elif digest != row["body_sha256"]:
        status = "BODY_CHANGED"
    else:
        status = "BODY_READ"
    return {"status": status, "body": body, "parts": parts,
            "request_status": client.logs[-1]["status"],
            "body_sha256": digest, "title_date": outer_title_date}


def review_plan(plan, sources, history, *, model, api_key="", offline=False,
                fetcher=fetch_document, assessor=call_model, desk_assessor=call_desk):
    by_id = {source["id"]: source for source in sources}
    if len(by_id) != 25:
        raise ValueError("Expected 25 configured council sources")
    if not offline and plan and not api_key:
        raise ValueError("OPENAI_API_KEY required for recent semantic shadow")
    payload = {
        "schema": 1,
        "sampled_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "coverage": "MAX_FIVE_CURRENT_L2_VERIFIED_DOCUMENTS",
        "mode": "CONTEXT_ONLY" if offline else "SEMANTIC_SHADOW",
        "source_count": 25,
        "selected_count": len(plan),
        "selection_counts": {},
        "results": [],
        "question_output": "NONE" if offline else "VERIFICATION_ONLY",
        "briefing_output": "NONE",
        "automatic_ledger_write": False,
    }
    for reason in sorted({row["selection_reason"] for row in plan}):
        payload["selection_counts"][reason] = sum(
            row["selection_reason"] == reason for row in plan)
    desk_inputs = []
    successful = []
    for row in plan:
        item = {key: row[key] for key in (
            "key", "source_id", "source_name", "document_url",
            "meeting_date", "selection_reason")}
        item.update({"public_release_date": None,
                     "source_claim_status": "의회 회의록·발언 미검증"})
        try:
            context = fetcher(row, by_id[row["source_id"]])
            item.update({
                "context_status": context["status"],
                "request_status": context.get("request_status", 0),
                "body_characters": len(context.get("body", "")),
                "speech_turns": len(context.get("parts", [])),
            })
            if context["status"] != "BODY_READ" or offline:
                item["semantic_status"] = "NOT_RUN"
            else:
                answer = assessor(context["body"], row, model, api_key)
                item["semantic_status"], card = validate_assessment(
                    answer, context["body"], context["parts"])
                if item["semantic_status"] == "REVIEW" and card:
                    item["verification_card"] = card
                    desk_inputs.append({
                        "source_id": row["source_id"],
                        "source_name": row["source_name"],
                        "meeting_date": row["meeting_date"],
                        "source_claim_status": item["source_claim_status"],
                        "verification_card": card,
                        "evidence_context": desk_context(context["parts"], card),
                    })
                elif item["semantic_status"] == "HOLD" and card:
                    item["held_cue"] = card
                else:
                    item["semantic_reason"] = assessment_reason(
                        item["semantic_status"], answer, card)
                if item["semantic_status"] in VALID_FINAL:
                    successful.append(row)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            item["context_status"] = item.get("context_status", "UNKNOWN_COLLECTION")
            item["semantic_status"] = "ERROR"
            item["error_type"] = type(exc).__name__
        payload["results"].append(item)
    if offline:
        payload["desk_status"] = "NOT_RUN"
    elif not desk_inputs:
        payload["desk_status"] = "NOT_NEEDED"
    else:
        try:
            reviews = validate_desk_response(
                desk_assessor(desk_inputs, model, api_key),
                [item["source_id"] for item in desk_inputs])
            for item in payload["results"]:
                if item["source_id"] in reviews:
                    item["editorial_review"] = reviews[item["source_id"]]
            payload["desk_status"] = "COMPLETE"
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            payload["desk_status"] = "ERROR"
            payload["desk_error_type"] = type(exc).__name__
            successful = []
    payload["review_count"] = sum(
        row.get("semantic_status") == "REVIEW" for row in payload["results"])
    payload["pursue_count"] = sum(
        row.get("editorial_review", {}).get("verdict") == "PURSUE"
        for row in payload["results"])
    payload["verify_first_count"] = sum(
        row.get("editorial_review", {}).get("verdict") == "VERIFY_FIRST"
        for row in payload["results"])
    payload["error_count"] = sum(
        row.get("semantic_status") == "ERROR" for row in payload["results"])
    existing = list(history["reviewed_documents"])
    known = {row["key"] for row in existing}
    now = payload["sampled_at_kst"]
    for row in successful:
        if row["key"] not in known:
            existing.append({
                "key": row["key"], "source_id": row["source_id"],
                "meeting_date": row["meeting_date"], "reviewed_at_kst": now,
            })
            known.add(row["key"])
    history_next = {"schema": 1, "reviewed_documents": existing[-500:]}
    return payload, history_next


def render(payload):
    labels = {"PURSUE": "취재 우선 검토", "VERIFY_FIRST": "선확인",
              "LOW_PRIORITY": "기획 우선순위 낮음"}
    lines = [
        "# 구의회 최근 회의록 L3 그림자 검토", "",
        "25개 구의회의 현재 L2 확인 문서 중 최대 5건만 다룬다.",
        "NEW_IN_VISIBLE_WINDOW는 최근목록 비교에서 새로 관측된 문서다.",
        "LATEST_UNREVIEWED_BOOTSTRAP은 새 문서라는 뜻이 아니라 아직 L3로 읽지 않은 최신 문서다.",
        "회의일은 공개일이 아니다. 발언은 사실 확인 전 주장이다.",
        "정식 브리핑·아이템 장부에는 자동 반영하지 않는다.", "",
        f"선정 {payload['selected_count']}건 · 발언 신호 {payload['review_count']}건 · "
        f"취재 우선 검토 {payload['pursue_count']}건 · 선확인 {payload['verify_first_count']}건 "
        f"· 오류 {payload['error_count']}건 · 편집 판정 {payload['desk_status']}", "",
        "| 의회 | 회의일 | 선정 이유 | 본문 | 발언 신호 | 방송 가치 |",
        "|---|---|---|---|---|---|",
    ]
    for row in payload["results"]:
        editorial = row.get("editorial_review", {}).get("verdict")
        lines.append(
            f"| {row['source_name']} | {row['meeting_date']} | "
            f"{row['selection_reason']} | {row.get('context_status', '-')} | "
            f"{semantic_status_label(row.get('semantic_status'))} | "
            f"{labels.get(editorial, '미평가')} |")
    if not payload["results"]:
        lines.extend(["", "이번 실행에서 조건을 충족한 미검토 문서가 없다. "
                      "이는 구의회에 아이템이 없다는 뜻이 아니다."])
    for row in payload["results"]:
        cue = row.get("held_cue")
        if cue:
            lines.extend([
                "", f"## {row['source_name']} · 보류된 단서",
                f"- 원문: {row['document_url']}",
                f"- 발언 앵커: {cue['anchor_quote']}",
                f"- 확인된 발언: {cue['observed_issue']}",
                f"- 가를 질문: {cue['test_question']}",
                f"- 다음 확인: {cue['first_check']}",
                f"- 보류 이유: {cue['reason']}",
            ])
        elif row.get("semantic_reason"):
            lines.extend(["", f"## {row['source_name']} · "
                          f"{semantic_status_label(row['semantic_status'])}",
                          f"- 보류·제외 이유: {row['semantic_reason']}"])
        card = row.get("verification_card")
        if not card:
            continue
        lines.extend([
            "", f"## {row['source_name']} · 발언 검증 단서",
            f"- 원문: {row['document_url']}",
            f"- 발언 앵커: {card['anchor_quote']}",
            f"- 발언 내용에 대한 해석(미검증): {card['observed_issue']}",
            f"- 시민의 이해관계(확인 필요): {card['citizen_stake_to_check']}",
            f"- 취재 가설: {card['editorial_hypothesis']}",
            f"- 가를 질문: {card['test_question']}",
            f"- 다른 설명: {card['alternative_explanation']}",
            f"- 첫 확인: {card['first_check']}",
            f"- 방송 구성 가능성(1차 가설): {card['broadcast_path']}",
        ])
        editorial = row.get("editorial_review")
        if editorial:
            lines.extend([
                f"- **독립 편집 판정: {labels[editorial['verdict']]}**",
                f"- 시민에게 닿는 경로: {editorial['citizen_path']}",
                f"- 방송 가치 판단: {editorial['broadcast_value']}",
                f"- 아직 빠진 부분: {editorial['missing_piece']}",
                f"- 우선순위를 바꿀 확인: {editorial['decisive_test']}",
                f"- 판단 이유: {editorial['reason']}",
            ])
        else:
            lines.append("- 독립 편집 판정: 미완료 — 방송 가치 미확인")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=BASE / "sources_25.json")
    parser.add_argument("--watch", type=Path, default=WATCH)
    parser.add_argument("--history", type=Path, default=HISTORY)
    parser.add_argument("--fixed", type=Path, default=FIXED)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--max-docs", type=int, default=MAX_DOCS)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    history = load_history(args.history)
    watch = json.loads(args.watch.read_text(encoding="utf-8")) if args.watch.is_file() else {}
    fixed = json.loads(args.fixed.read_text(encoding="utf-8"))
    as_of = datetime.now(KST).date()
    if args.max_docs == 0:
        l2_payload = {"source_count": 25, "results": [
            {"source_id": source["id"], "source_name": source["name"],
             "status": "UNKNOWN_COLLECTION"} for source in sources]}
    else:
        l2_payload = collect_l2(sources, as_of)
    plan = select_plan(l2_payload, watch, history, fixed, as_of, args.max_docs)
    payload, history_next = review_plan(
        plan, sources, history, model=args.model,
        api_key=os.getenv("OPENAI_API_KEY", ""), offline=args.offline)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "sample_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "SUMMARY.md").write_text(render(payload), encoding="utf-8")
    (args.output / "reviewed_documents_next.json").write_text(
        json.dumps(history_next, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(render(payload))
    print(json.dumps({
        "selected_count": payload["selected_count"],
        "review_count": payload["review_count"],
        "pursue_count": payload["pursue_count"],
        "desk_status": payload["desk_status"],
        "error_count": payload["error_count"],
    }, ensure_ascii=False))
    return 1 if payload["desk_status"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
