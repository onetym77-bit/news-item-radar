#!/usr/bin/env python3
"""Longitudinal council issue tracker.

The tracker produces a human-review queue only. Silence is never treated as proof
that a problem remains unresolved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
DISTRICT = ROOT / "district-council-pilot"
sys.path.insert(0, str(DISTRICT))

from clik_api import fetch_payload, public_document_url  # noqa: E402
from collect_pilot import Page, transcript  # noqa: E402

OPENAI = "https://api.openai.com/v1/responses"
KST = timezone(timedelta(hours=9))
SEOUL_CITY = {"id": "seoul-city", "name": "서울시의회", "clik_assembly_id": "002001"}
DOCID = re.compile(r"CLIKC[0-9]+")
DATE_TEXT = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}")
GENERIC_TERMS = {"서울", "시민", "문제", "대책", "개선", "지적", "사업", "예산"}

SIGNATURE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "issue_title": {"type": "string"},
        "responsible_body": {"type": "string"},
        "affected_group": {"type": "string"},
        "place_scope": {"type": "string"},
        "public_obligation": {"type": "string"},
        "failure_mode": {"type": "string"},
        "search_keywords": {
            "type": "array", "minItems": 2, "maxItems": 4,
            "items": {"type": "string"},
        },
    },
    "required": [
        "issue_title", "responsible_body", "affected_group", "place_scope",
        "public_obligation", "failure_mode", "search_keywords",
    ],
}

COMPARE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "relation": {
            "type": "string",
            "enum": [
                "SAME_UNRESOLVED", "SAME_PARTIAL", "SAME_RESOLVED",
                "RELATED_DIFFERENT", "NO_MATCH",
            ],
        },
        "anchor_quote": {"type": "string"},
        "why_same": {"type": "string"},
        "status_basis": {"type": "string"},
        "citizen_stake": {"type": "string"},
        "next_check": {"type": "string"},
    },
    "required": [
        "relation", "anchor_quote", "why_same", "status_basis",
        "citizen_stake", "next_check",
    ],
}

SIGNATURE_INSTRUCTIONS = """서울시·자치구 의회 발언에서 장기간 추적할 하나의 행정 문제를 구조화한다.
입력은 사실 확정이 아닌 회의록 단서다. 기관, 영향 대상, 지역·사업, 행정의 의무, 실패 양상을 서로 구분한다.
검색어는 회의록 본문에서 같은 문제를 다시 찾을 수 있는 고유한 한국어 명사구 2~4개만 쓴다.
'서울', '시민', '문제', '대책', '개선', '지적'처럼 단독으로 넓은 단어는 금지한다.
발언에 없는 피해나 미이행을 만들어내지 않는다."""

COMPARE_INSTRUCTIONS = """두 의회 회의록 단서가 같은 행정 문제의 시간상 전후 기록인지 판정한다.
기관명이나 키워드가 같다는 이유만으로 같은 문제로 보지 않는다. 영향 대상, 행정 의무, 실패 양상이 함께 맞아야 한다.
SAME_UNRESOLVED는 뒤 문서가 같은 문제의 지속·재발·미이행을 명시할 때만 쓴다.
SAME_PARTIAL은 조치가 있었으나 공백이 남았다는 명시적 근거가 있을 때다.
SAME_RESOLVED는 완료 또는 해소 근거가 있을 때다.
후속 문서가 없거나 침묵했다는 사실은 미해결 근거가 아니다.
anchor_quote는 비교 대상 문서 안의 연속 문자열 15~180자로 쓴다. 확신할 수 없으면 RELATED_DIFFERENT 또는 NO_MATCH다."""


def compact(value):
    return " ".join(str(value or "").split())


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_seed_payloads(paths):
    """Load available seed snapshots and report optional inputs that are absent."""
    payloads = []
    loaded = []
    missing = []
    for value in paths:
        path = Path(value)
        if not path.is_file():
            missing.append(str(path))
            continue
        payloads.append(read_json(path))
        loaded.append(str(path))
    if not payloads:
        raise FileNotFoundError("No seed input files are available")
    return payloads, loaded, missing


def walk_dicts(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def _date_from(row):
    for key in ("meeting_date", "speech_date", "document_date", "source_date"):
        value = compact(row.get(key))
        if DATE_TEXT.fullmatch(value):
            return value
    return ""


def _url_from(row):
    for key in ("document_url", "url", "container_url", "source_url"):
        value = compact(row.get(key))
        if value.startswith("https://"):
            return value
    return ""


def _joined_text(row):
    card = row.get("verification_card") or row.get("held_cue") or {}
    values = []
    for source in (row, card if isinstance(card, dict) else {}):
        for key in (
            "context_subject", "observed_issue", "observed_problem", "context_text",
            "display_fact", "text", "anchor_quote", "editorial_hypothesis",
            "test_question", "question_basis", "question", "first_check",
            "public_obligation", "promise_or_deadline",
        ):
            value = compact(source.get(key))
            if value and value not in values:
                values.append(value)
    return " | ".join(values)[:8000]


def collect_seed_records(payloads, max_seeds=3):
    """Extract recent Seoul/district council signals from existing JSON outputs."""
    records = []
    seen = set()
    for payload in payloads:
        for row in walk_dicts(payload):
            date_text = _date_from(row)
            url = _url_from(row)
            text = _joined_text(row)
            source_id = compact(row.get("source_id"))
            source_name = compact(row.get("source_name") or row.get("source"))
            has_card = isinstance(row.get("verification_card") or row.get("held_cue"), dict)
            council = (
                source_id == "council_minutes"
                or "시의회" in source_name
                or "구의회" in source_name
                or has_card
                or row.get("historical_seed") is True
            )
            if not council or not date_text or not url or len(text) < 80:
                continue
            identity = hashlib.sha256((url + "\n" + text).encode("utf-8")).hexdigest()[:16]
            if identity in seen:
                continue
            seen.add(identity)
            records.append({
                "seed_id": identity,
                "source_id": source_id or compact(row.get("id")) or "council",
                "source_name": source_name or compact(row.get("family")) or "의회 회의록",
                "meeting_date": date_text,
                "document_url": url,
                "current_text": text,
                "affected_group_hint": compact(row.get("affected_group")),
                "subject_hint": compact(row.get("context_subject")),
                "seed_kind": "HISTORICAL" if row.get("historical_seed") is True else "CURRENT",
            })
    records.sort(key=lambda row: (row["meeting_date"], len(row["current_text"])), reverse=True)
    historical = [row for row in records if row["seed_kind"] == "HISTORICAL"]
    current = [row for row in records if row["seed_kind"] == "CURRENT"]
    if not historical:
        return current[:max_seeds]
    historical_slots = min(len(historical), max(1, max_seeds // 2))
    return historical[:historical_slots] + current[:max_seeds - historical_slots]


def call_json(model, api_key, instructions, data, schema, name, max_tokens=1600):
    request_data = {
        "model": model,
        "store": False,
        "max_output_tokens": max_tokens,
        "input": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
        "text": {"format": {
            "type": "json_schema", "name": name, "strict": True, "schema": schema,
        }},
    }
    request = urllib.request.Request(
        OPENAI,
        data=json.dumps(request_data, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        answer = json.load(response)
    parts = [
        part.get("text", "")
        for item in answer.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    if answer.get("status") != "completed" or not parts:
        raise ValueError("Model response incomplete")
    return json.loads("".join(parts))


def validate_signature(value):
    required = set(SIGNATURE_SCHEMA["required"])
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Invalid issue signature keys")
    keywords = [compact(term) for term in value["search_keywords"]]
    if not 2 <= len(keywords) <= 4 or len(set(keywords)) != len(keywords):
        raise ValueError("Invalid issue search keyword count")
    if any(not term or len(term) > 40 or term in GENERIC_TERMS for term in keywords):
        raise ValueError("Issue search keyword is empty, broad, or too long")
    result = {key: compact(value[key]) for key in required if key != "search_keywords"}
    if any(not result[key] for key in result):
        raise ValueError("Incomplete issue signature")
    result["search_keywords"] = keywords
    return result


def parse_api_date(value):
    text = compact(value)
    if not re.fullmatch(r"20[0-9]{6}", text):
        return ""
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    except ValueError:
        return ""


def council_sources(path):
    rows = read_json(path)
    if not isinstance(rows, list) or len(rows) != 25:
        raise ValueError("Expected 25 district council sources")
    ids = {row.get("clik_assembly_id") for row in rows}
    if len(ids) != 25:
        raise ValueError("Duplicate or missing district assembly IDs")
    return [SEOUL_CITY, *rows]


def search_api(api_key, sources, signature, start_date, end_date, per_query=8):
    """Search CLIK while preserving partial failures as explicit collection errors."""
    found = {}
    errors = []
    successful_requests = 0
    for keyword in signature["search_keywords"]:
        for source in sources:
            try:
                payload = fetch_payload(
                    api_key,
                    displayType="list",
                    startCount=0,
                    listCount=per_query,
                    searchType="MINTS_HTML",
                    searchKeyword=keyword,
                    rasmblyId=source["clik_assembly_id"],
                    sort="WEIGHT/DESC",
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                errors.append({
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "search_keyword": keyword,
                    "error_type": type(exc).__name__,
                })
                continue
            successful_requests += 1
            for entry in payload.get("LIST") or []:
                row = entry.get("ROW") if isinstance(entry, dict) else None
                if not isinstance(row, dict):
                    continue
                docid = compact(row.get("DOCID"))
                meeting_date = parse_api_date(row.get("MTG_DE"))
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
                    "document_url": public_document_url(docid),
                    "matched_keywords": [],
                })
                if keyword not in item["matched_keywords"]:
                    item["matched_keywords"].append(keyword)
    return {
        "rows": sorted(
            found.values(),
            key=lambda row: (
                -len(row["matched_keywords"]), row["meeting_date"], row["document_id"]
            ),
        ),
        "errors": errors,
        "successful_requests": successful_requests,
    }


def fetch_candidate_body(api_key, candidate):
    payload = fetch_payload(api_key, displayType="detail", docid=candidate["document_id"])
    if (
        payload.get("DOCID") != candidate["document_id"]
        or payload.get("RASMBLY_ID") not in {
            "002001", *{f"0020{number:02d}" for number in range(2, 27)}
        }
    ):
        raise ValueError("CLIK detail identity mismatch")
    html = payload.get("MINTS_HTML")
    if not isinstance(html, str):
        raise ValueError("CLIK detail body missing")
    body, _ = transcript(Page(html))
    if not body:
        raise ValueError("CLIK detail transcript unavailable")
    return body


def validate_comparison(value, body):
    required = set(COMPARE_SCHEMA["required"])
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Invalid comparison keys")
    result = {key: compact(value[key]) for key in required}
    if result["relation"] not in COMPARE_SCHEMA["properties"]["relation"]["enum"]:
        raise ValueError("Invalid comparison relation")
    if result["relation"] not in {"RELATED_DIFFERENT", "NO_MATCH"}:
        quote = result["anchor_quote"]
        if len(quote) < 15 or quote not in compact(body):
            raise ValueError("Comparison anchor is not in source body")
    return result


def lifecycle_status(seed_date, candidate_date, relation):
    earlier = min(seed_date, candidate_date)
    later = max(seed_date, candidate_date)
    gap = (later - earlier).days
    if relation == "SAME_RESOLVED":
        return "RESOLVED_EVIDENCE"
    if relation == "SAME_PARTIAL":
        return "PARTIAL_ACTION_EVIDENCE"
    if relation == "SAME_UNRESOLVED" and gap >= 270:
        return "REPEATED_AFTER_9M"
    if relation == "SAME_UNRESOLVED":
        return "REPEATED_WITHIN_9M"
    return "NO_MATCH"


def run(seed_payloads, sources, *, api_key, openai_key, model,
        as_of, lookback_months=18, max_seeds=3, max_comparisons=12):
    seeds = collect_seed_records(seed_payloads, max_seeds)
    output = {
        "schema": 1,
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "lookback_months": lookback_months,
        "source_count": len(sources),
        "seed_count": len(seeds),
        "comparison_limit": max_comparisons,
        "automatic_briefing_write": False,
        "silence_is_unresolved": False,
        "results": [],
        "errors": [],
    }
    comparisons = 0
    start_date = as_of - timedelta(days=lookback_months * 31)
    for seed in seeds:
        try:
            signature = validate_signature(call_json(
                model, openai_key, SIGNATURE_INSTRUCTIONS, seed,
                SIGNATURE_SCHEMA, "council_issue_signature",
            ))
            discovery = search_api(api_key, sources, signature, start_date, as_of)
            if discovery["successful_requests"] == 0:
                raise ValueError("All CLIK follow-up searches failed")
            candidates = discovery["rows"]
            for error in discovery["errors"]:
                output["errors"].append({"seed_id": seed["seed_id"], **error})
            matches = []
            for candidate in candidates:
                if comparisons >= max_comparisons:
                    break
                if candidate["document_url"] == seed["document_url"]:
                    continue
                try:
                    body = fetch_candidate_body(api_key, candidate)
                    earlier, later = sorted(
                        [
                            {"date": seed["meeting_date"], "text": seed["current_text"],
                             "url": seed["document_url"], "source": seed["source_name"]},
                            {"date": candidate["meeting_date"], "text": body[:16000],
                             "url": candidate["document_url"], "source": candidate["source_name"]},
                        ],
                        key=lambda row: row["date"],
                    )
                    answer = validate_comparison(call_json(
                        model, openai_key, COMPARE_INSTRUCTIONS,
                        {"issue_signature": signature, "earlier": earlier, "later": later},
                        COMPARE_SCHEMA, "council_issue_comparison", 1400,
                    ), body)
                    comparisons += 1
                    status = lifecycle_status(
                        date.fromisoformat(seed["meeting_date"]),
                        date.fromisoformat(candidate["meeting_date"]),
                        answer["relation"],
                    )
                    if status != "NO_MATCH":
                        matches.append({
                            **{key: candidate[key] for key in (
                                "source_id", "source_name", "meeting_date",
                                "document_url", "matched_keywords",
                            )},
                            **answer,
                            "lifecycle_status": status,
                            "gap_days": abs(
                                (date.fromisoformat(seed["meeting_date"])
                                 - date.fromisoformat(candidate["meeting_date"])).days
                            ),
                        })
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    output["errors"].append({
                        "seed_id": seed["seed_id"],
                        "document_id": candidate.get("document_id", ""),
                        "error_type": type(exc).__name__,
                    })
            output["results"].append({
                **{key: seed[key] for key in (
                    "seed_id", "source_id", "source_name", "meeting_date", "document_url",
                )},
                "signature": signature,
                "searched_candidate_count": len(candidates),
                "collection_error_count": len(discovery["errors"]),
                "status": (
                    "EVIDENCE_FOUND" if matches else
                    "COLLECTION_INCOMPLETE" if discovery["errors"] else
                    "NO_MATCHING_FOLLOWUP_OR_PRIOR_EVIDENCE"
                ),
                "matches": matches,
                "editorial_boundary": (
                    "사람 검토 전에는 반복·미해결 사실이나 정식 기사 후보로 확정하지 않음"
                ),
            })
        except (OSError, ValueError, KeyError, TypeError) as exc:
            output["errors"].append({
                "seed_id": seed["seed_id"], "error_type": type(exc).__name__,
            })
    output["comparison_count"] = comparisons
    output["evidence_count"] = sum(len(row["matches"]) for row in output["results"])
    return output


def render(payload):
    lines = [
        "# 의회 지적사항 생명주기 검토", "",
        f"- 추적 씨앗: {payload['seed_count']}건",
        f"- 서울시의회·자치구의회: {payload['source_count']}곳",
        f"- 과거 탐색 범위: {payload['lookback_months']}개월",
        f"- 근거 쌍: {payload['evidence_count']}건",
        "",
        "> 뒤 회의록에서 언급이 없다는 사실은 미해결 증거가 아니다. "
        "모든 결과는 사람 검토 전 단계이며 브리핑에 자동 반영하지 않는다.",
    ]
    labels = {
        "REPEATED_AFTER_9M": "9개월 이상 뒤 같은 문제 재지적",
        "REPEATED_WITHIN_9M": "9개월 안에 같은 문제 재지적",
        "PARTIAL_ACTION_EVIDENCE": "일부 조치 뒤 공백 근거",
        "RESOLVED_EVIDENCE": "해결·완료 근거",
    }
    for row in payload["results"]:
        title = row["signature"]["issue_title"]
        lines.extend(["", f"## {title}", f"- 현재 단서: [{row['source_name']}]({row['document_url']})"])
        if not row["matches"]:
            lines.append("- 판정: 동일한 과거·후속 근거를 찾지 못함 — 미해결로 간주하지 않음")
            continue
        for match in row["matches"]:
            lines.extend([
                f"- **{labels.get(match['lifecycle_status'], match['lifecycle_status'])}**",
                f"  - 비교 자료: [{match['source_name']} {match['meeting_date']}]({match['document_url']})",
                f"  - 간격: {match['gap_days']}일",
                f"  - 원문 앵커: {match['anchor_quote']}",
                f"  - 같은 사안으로 본 이유: {match['why_same']}",
                f"  - 상태 근거: {match['status_basis']}",
                f"  - 다음 확인: {match['next_check']}",
            ])
    if payload.get("missing_seed_files"):
        lines.extend([
            "",
            "- 입력 누락: "
            + ", ".join(payload["missing_seed_files"])
            + " — 다른 입력으로 실행했으며 0건으로 해석하지 않음",
        ])
    if payload["errors"]:
        lines.extend(["", f"- 처리 오류: {len(payload['errors'])}건 — 0건으로 해석하지 않음"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-file", action="append", type=Path, required=True)
    parser.add_argument("--sources", type=Path, default=DISTRICT / "sources_25.json")
    parser.add_argument("--output", type=Path, default=BASE / "output")
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--lookback-months", type=int, choices=(12, 18), default=18)
    parser.add_argument("--max-seeds", type=int, choices=(1, 3, 5), default=3)
    parser.add_argument("--max-comparisons", type=int, default=12)
    args = parser.parse_args()
    if not 1 <= args.max_comparisons <= 30:
        raise ValueError("Comparison limit must be between 1 and 30")
    clik_key = os.getenv("CLIK_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not clik_key or not openai_key:
        raise ValueError("CLIK_API_KEY and OPENAI_API_KEY are required")
    seed_payloads, loaded_seed_files, missing_seed_files = load_seed_payloads(args.seed_file)
    payload = run(
        seed_payloads,
        council_sources(args.sources),
        api_key=clik_key,
        openai_key=openai_key,
        model=args.model,
        as_of=datetime.now(KST).date(),
        lookback_months=args.lookback_months,
        max_seeds=args.max_seeds,
        max_comparisons=args.max_comparisons,
    )
    payload["loaded_seed_files"] = loaded_seed_files
    payload["missing_seed_files"] = missing_seed_files
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "SUMMARY.md").write_text(render(payload), encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(render(payload))
    print(json.dumps({
        "seed_count": payload["seed_count"],
        "comparison_count": payload["comparison_count"],
        "evidence_count": payload["evidence_count"],
        "error_count": len(payload["errors"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
