#!/usr/bin/env python3
"""Bounded historical issue-seed backfill for council lifecycle tracking."""
from __future__ import annotations

import argparse
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pipeline

BASE = Path(__file__).resolve().parent
TERMS = ("반복 지적", "미이행", "아직도", "개선되지", "수년째", "장기 지연")
DOCID = re.compile(r"CLIKC[0-9]+")

EXTRACT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["TRACK", "HOLD", "NO_SIGNAL"]},
        "issue_title": {"type": "string"},
        "anchor_quote": {"type": "string"},
        "observed_problem": {"type": "string"},
        "responsible_body": {"type": "string"},
        "affected_group": {"type": "string"},
        "public_obligation": {"type": "string"},
        "promise_or_deadline": {"type": "string"},
        "search_keywords": {
            "type": "array", "minItems": 2, "maxItems": 4,
            "items": {"type": "string"},
        },
        "reason": {"type": "string"},
    },
    "required": [
        "verdict", "issue_title", "anchor_quote", "observed_problem",
        "responsible_body", "affected_group", "public_obligation",
        "promise_or_deadline", "search_keywords", "reason",
    ],
}

INSTRUCTIONS = """9~18개월 전 서울시·자치구 의회 회의록에서 이후 이행 여부를 추적할 구체적인 행정 문제를 한 건만 찾는다.
TRACK은 책임 기관, 영향을 받는 시민, 해야 할 행정 의무, 실제로 지적된 공백이 원문에 함께 있을 때만 허용한다.
단순 정치적 비판, 의례, 예산·조례 제목, 홍보 발언, 구체적 의무가 없는 일반론은 HOLD 또는 NO_SIGNAL이다.
실제 피해 사례가 없다는 이유만으로 배제하지 않는다. 신규 사업도 시민에게 중요한 권리·안전·서비스 의무와 확인 경로가 구체적이면 TRACK할 수 있다.
promise_or_deadline은 원문에 약속·기한이 있으면 그대로 요약하고, 없으면 '명시적 약속·기한 없음'이라고 쓴다.
anchor_quote는 원문 안의 연속 문자열 15~180자다. 검색어는 같은 사안의 후속 회의록을 찾을 고유 명사구 2~4개다.
발언을 사실이나 미해결 상태로 확정하지 않는다."""


def discover(api_key, sources, start_date, end_date, per_query=5):
    found = {}
    for term in TERMS:
        signature = {"search_keywords": [term]}
        for source in sources:
            payload = pipeline.fetch_payload(
                api_key,
                displayType="list",
                startCount=0,
                listCount=per_query,
                searchType="MINTS_HTML",
                searchKeyword=term,
                rasmblyId=source["clik_assembly_id"],
                sort="WEIGHT/DESC",
            )
            for entry in payload.get("LIST") or []:
                row = entry.get("ROW") if isinstance(entry, dict) else None
                if not isinstance(row, dict):
                    continue
                docid = pipeline.compact(row.get("DOCID"))
                meeting_date = pipeline.parse_api_date(row.get("MTG_DE"))
                if (
                    not DOCID.fullmatch(docid)
                    or row.get("RASMBLY_ID") != source["clik_assembly_id"]
                    or not meeting_date
                    or not start_date <= date.fromisoformat(meeting_date) <= end_date
                ):
                    continue
                item = found.setdefault(docid, {
                    "document_id": docid,
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "meeting_date": meeting_date,
                    "document_url": pipeline.public_document_url(docid),
                    "matched_terms": [],
                })
                if term not in item["matched_terms"]:
                    item["matched_terms"].append(term)
    return sorted(
        found.values(),
        key=lambda row: (-len(row["matched_terms"]), -date.fromisoformat(row["meeting_date"]).toordinal()),
    )


def validate_extract(answer, body):
    if not isinstance(answer, dict) or set(answer) != set(EXTRACT_SCHEMA["required"]):
        raise ValueError("Invalid historical extraction keys")
    answer = {
        key: ([pipeline.compact(value) for value in answer[key]]
              if key == "search_keywords" else pipeline.compact(answer[key]))
        for key in answer
    }
    if answer["verdict"] not in {"TRACK", "HOLD", "NO_SIGNAL"}:
        raise ValueError("Invalid historical extraction verdict")
    if answer["verdict"] == "TRACK":
        if len(answer["anchor_quote"]) < 15 or answer["anchor_quote"] not in pipeline.compact(body):
            raise ValueError("Historical anchor is not in source body")
        pipeline.validate_signature({
            "issue_title": answer["issue_title"],
            "responsible_body": answer["responsible_body"],
            "affected_group": answer["affected_group"],
            "place_scope": "서울 또는 해당 자치구",
            "public_obligation": answer["public_obligation"],
            "failure_mode": answer["observed_problem"],
            "search_keywords": answer["search_keywords"],
        })
    return answer


def run(*, api_key, openai_key, model, sources, as_of,
        lookback_months=18, minimum_age_months=9, max_docs=12, max_seeds=5):
    start_date = as_of - timedelta(days=lookback_months * 31)
    end_date = as_of - timedelta(days=minimum_age_months * 30)
    candidates = discover(api_key, sources, start_date, end_date)
    payload = {
        "schema": 1,
        "generated_at_kst": datetime.now(pipeline.KST).isoformat(timespec="seconds"),
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "source_count": len(sources),
        "query_terms": list(TERMS),
        "candidate_count": len(candidates),
        "reviewed_count": 0,
        "historical_seeds": [],
        "holds": [],
        "errors": [],
        "automatic_unresolved_finding": False,
    }
    for candidate in candidates[:max_docs]:
        if len(payload["historical_seeds"]) >= max_seeds:
            break
        try:
            body = pipeline.fetch_candidate_body(api_key, candidate)
            answer = validate_extract(pipeline.call_json(
                model, openai_key, INSTRUCTIONS,
                {
                    "source_name": candidate["source_name"],
                    "meeting_date": candidate["meeting_date"],
                    "document_url": candidate["document_url"],
                    "matched_terms": candidate["matched_terms"],
                    "transcript": body[:18000],
                },
                EXTRACT_SCHEMA,
                "historical_council_issue_seed",
                1600,
            ), body)
            payload["reviewed_count"] += 1
            if answer["verdict"] != "TRACK":
                payload["holds"].append({
                    "source_name": candidate["source_name"],
                    "meeting_date": candidate["meeting_date"],
                    "document_url": candidate["document_url"],
                    "reason": answer["reason"],
                    "verdict": answer["verdict"],
                })
                continue
            payload["historical_seeds"].append({
                "historical_seed": True,
                "source_id": candidate["source_id"],
                "source_name": candidate["source_name"],
                "meeting_date": candidate["meeting_date"],
                "document_url": candidate["document_url"],
                "context_subject": answer["issue_title"],
                "text": " | ".join([
                    answer["anchor_quote"], answer["observed_problem"],
                    answer["public_obligation"], answer["promise_or_deadline"],
                ]),
                "affected_group": answer["affected_group"],
                "responsible_body": answer["responsible_body"],
                "search_keywords": answer["search_keywords"],
                "source_claim_status": "과거 의회 발언·사람 검토 전",
            })
        except (OSError, ValueError, KeyError, TypeError) as exc:
            payload["errors"].append({
                "document_id": candidate.get("document_id", ""),
                "error_type": type(exc).__name__,
            })
    payload["seed_count"] = len(payload["historical_seeds"])
    return payload


def render(payload):
    lines = [
        "# 과거 의회 지적 추적 씨앗", "",
        f"- 탐색 기간: {payload['window_start']}~{payload['window_end']}",
        f"- 대상 의회: {payload['source_count']}곳",
        f"- 검색 후보: {payload['candidate_count']}건",
        f"- 본문 검토: {payload['reviewed_count']}건",
        f"- 후속 추적 씨앗: {payload['seed_count']}건", "",
        "> 이 목록은 과거 발언의 후속 상태를 묻기 위한 시작점이다. "
        "후속 언급이 없다는 이유로 미해결로 판정하지 않는다.",
    ]
    for row in payload["historical_seeds"]:
        lines.extend([
            "", f"## {row['context_subject']}",
            f"- 원문: [{row['source_name']} {row['meeting_date']}]({row['document_url']})",
            f"- 추적 단서: {row['text']}",
            f"- 후속 검색어: {', '.join(row['search_keywords'])}",
        ])
    if payload["errors"]:
        lines.extend(["", f"- 처리 오류: {len(payload['errors'])}건 — 자료 없음으로 해석하지 않음"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=pipeline.DISTRICT / "sources_25.json")
    parser.add_argument("--output", type=Path, default=BASE / "output")
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--lookback-months", type=int, choices=(12, 18), default=18)
    parser.add_argument("--minimum-age-months", type=int, choices=(6, 9, 12), default=9)
    parser.add_argument("--max-docs", type=int, default=12)
    parser.add_argument("--max-seeds", type=int, choices=(1, 3, 5), default=5)
    args = parser.parse_args()
    if not 1 <= args.max_docs <= 20:
        raise ValueError("Historical document limit must be between 1 and 20")
    clik_key = os.getenv("CLIK_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not clik_key or not openai_key:
        raise ValueError("CLIK_API_KEY and OPENAI_API_KEY are required")
    payload = run(
        api_key=clik_key,
        openai_key=openai_key,
        model=args.model,
        sources=pipeline.council_sources(args.sources),
        as_of=datetime.now(pipeline.KST).date(),
        lookback_months=args.lookback_months,
        minimum_age_months=args.minimum_age_months,
        max_docs=args.max_docs,
        max_seeds=args.max_seeds,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "historical_seeds_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "HISTORICAL_SEEDS.md").write_text(render(payload), encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(render(payload))
    print(json.dumps({
        "candidate_count": payload["candidate_count"],
        "reviewed_count": payload["reviewed_count"],
        "seed_count": payload["seed_count"],
        "error_count": len(payload["errors"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
