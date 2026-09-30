#!/usr/bin/env python3
"""Incremental semantic reading of the keyword-free council archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
import gzip

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
KST = timezone(timedelta(hours=9))
OPENAI = "https://api.openai.com/v1/responses"
STATE_SCHEMA = 1

SIGNAL_TYPES = [
    "EXISTING_HARM",
    "SERVICE_GAP",
    "PUBLIC_COST",
    "SAFETY_RISK",
    "RIGHTS_GAP",
    "REPEATED_FAILURE",
    "NEW_POLICY_UNCERTAINTY",
    "CROSS_DISTRICT_PATTERN",
]
EVIDENCE_STATUSES = [
    "ALLEGATION",
    "OFFICIAL_FINDING",
    "PROPOSAL",
    "PLAN",
    "OBSERVED_OUTCOME",
]
SCOPES = ["SINGLE_CASE", "MULTI_DISTRICT", "CITYWIDE", "UNKNOWN"]

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "signal_type",
                    "headline",
                    "subject",
                    "affected_group",
                    "mechanism",
                    "civic_importance",
                    "anchor_quote",
                    "evidence_status",
                    "unknowns",
                    "public_question",
                    "counterintuitive_question",
                    "scope_hint",
                    "broadcast_potential",
                    "why_not_routine",
                ],
                "properties": {
                    "signal_type": {"type": "string", "enum": SIGNAL_TYPES},
                    "headline": {"type": "string"},
                    "subject": {"type": "string"},
                    "affected_group": {"type": "string"},
                    "mechanism": {"type": "string"},
                    "civic_importance": {"type": "string"},
                    "anchor_quote": {"type": "string"},
                    "evidence_status": {"type": "string", "enum": EVIDENCE_STATUSES},
                    "unknowns": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 4,
                        "items": {"type": "string"},
                    },
                    "public_question": {"type": "string"},
                    "counterintuitive_question": {"type": "string"},
                    "scope_hint": {"type": "string", "enum": SCOPES},
                    "broadcast_potential": {"type": "integer", "minimum": 0, "maximum": 100},
                    "why_not_routine": {"type": "string"},
                },
            },
        }
    },
}

INSTRUCTIONS = """당신은 서울 지역방송의 기획취재 발굴 데스크다.
입력은 서울시의회 또는 자치구의회 회의록의 일부다. 키워드 개수를 세지 말고
발언의 문맥에서 '누가, 어떤 제도·사업·행정 결정 때문에, 어떤 부담·위험·권리 공백을
겪는가'를 구조화하라.

후보로 잡을 수 있는 것:
- 이미 발생한 시민 피해·서비스 공백·공공비용·안전·권리 문제
- 새 사업이라 자료가 아직 없더라도 대상과 공적 책임이 명확하고 시민에게 중요한 질문
- 단일 사례라도 피해가 중대하거나 다른 지역으로 확장 검증할 수 있는 문제
- 현재 인기나 민원이 없어도 시민이 반드시 알아야 할 숨은 구조적 문제
- 의원의 질문·주장 자체도 의미 있는 공적 문제 제기라면 후보가 될 수 있음

후보로 잡지 말 것:
- 단순 행사·인사말·조례 문구 정비·일상적인 공사 일정·기관 내부 행정
- '시민에게 문제가 있는가'처럼 원문 내용을 바꾸지 않은 일반 질문
- 발언 한 문장을 제목·주제·질문에 반복하는 결과
- 공사, 민원, 지원 같은 단어가 있다는 이유만으로 만든 후보
- 6~7분 방송 리포트로 확장할 피해자·책임 주체·현장·비교 축이 전혀 없는 소소한 단일 건

사실이 확인되지 않았다는 이유만으로 버리지 말라. 대신 evidence_status와 unknowns로
검증 전 상태를 분명히 하라. 새 사업은 실적 자료가 없을 수 있다.
anchor_quote는 반드시 입력 원문에 실제로 있는 짧은 문장을 그대로 사용한다.
headline은 인용문 복사가 아니라 갈등·격차·책임 구조를 한 문장으로 요약한다.
public_question은 시민이 자신의 삶과 공공 책임을 구체적으로 따질 수 있는 질문이어야 한다.
counterintuitive_question은 통념과 다른 원인·배분·대체수단·부작용을 확인하는 질문이어야 한다.
유의미한 문제가 없으면 items를 빈 배열로 반환한다."""


def compact(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def read_json(path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_archive(path):
    if not path.is_file():
        return []
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    unique = {row["document_id"]: row for row in rows}
    return sorted(
        unique.values(),
        key=lambda row: (row.get("meeting_date", ""), row.get("document_id", "")),
        reverse=True,
    )


def chunks(text, size=12000, overlap=600):
    paragraphs = [compact(row) for row in str(text or "").splitlines() if compact(row)]
    result = []
    current = []
    length = 0
    for paragraph in paragraphs:
        if len(paragraph) > size:
            pieces = [paragraph[i:i + size] for i in range(0, len(paragraph), size - overlap)]
        else:
            pieces = [paragraph]
        for piece in pieces:
            if current and length + len(piece) + 1 > size:
                joined = "\n".join(current)
                result.append(joined)
                tail = joined[-overlap:] if overlap else ""
                current = [tail, piece] if tail else [piece]
                length = sum(map(len, current)) + len(current) - 1
            else:
                current.append(piece)
                length += len(piece) + 1
    if current:
        result.append("\n".join(current))
    return [row for row in result if len(compact(row)) >= 120]


def call_model(model, api_key, metadata, passage):
    request_data = {
        "model": model,
        "store": False,
        "max_output_tokens": 2600,
        "input": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": json.dumps({
                "source": metadata,
                "meeting_excerpt": passage,
            }, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "council_semantic_signals",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }
    request = urllib.request.Request(
        OPENAI,
        data=json.dumps(request_data, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=150) as response:
        answer = json.load(response)
    texts = [
        part.get("text", "")
        for item in answer.get("output", [])
        if item.get("type") == "message"
        for part in item.get("content", [])
        if part.get("type") == "output_text"
    ]
    if answer.get("status") != "completed" or not texts:
        raise ValueError("Model response incomplete")
    return json.loads("".join(texts))


def validate_item(item, passage):
    required = set(SCHEMA["properties"]["items"]["items"]["required"])
    if not isinstance(item, dict) or set(item) != required:
        raise ValueError("Invalid semantic item keys")
    result = {key: compact(value) for key, value in item.items() if key != "unknowns"}
    result["unknowns"] = [compact(value) for value in item["unknowns"] if compact(value)]
    if result["signal_type"] not in SIGNAL_TYPES:
        raise ValueError("Invalid signal type")
    if result["evidence_status"] not in EVIDENCE_STATUSES:
        raise ValueError("Invalid evidence status")
    if result["scope_hint"] not in SCOPES:
        raise ValueError("Invalid scope hint")
    if not 0 <= item["broadcast_potential"] <= 100:
        raise ValueError("Invalid broadcast potential")
    result["broadcast_potential"] = item["broadcast_potential"]
    if len(result["headline"]) < 12 or len(result["subject"]) < 20:
        raise ValueError("Headline or subject too short")
    quote = result["anchor_quote"]
    if len(quote) < 15 or compact(quote) not in compact(passage):
        raise ValueError("Anchor quote not found in source passage")
    if len(result["unknowns"]) < 1:
        raise ValueError("Missing verification unknowns")
    generic = (
        "시민에게 어떤 영향" in result["public_question"]
        or "문제가 있는가" in result["public_question"]
        or result["public_question"] == result["subject"]
    )
    if generic:
        raise ValueError("Generic public question")
    quote_terms = set(re.findall(r"[가-힣]{2,}", quote))
    headline_terms = set(re.findall(r"[가-힣]{2,}", result["headline"]))
    if headline_terms and len(headline_terms & quote_terms) / len(headline_terms) > 0.9:
        raise ValueError("Headline merely copies quote")
    return result


def load_candidate_log(path):
    rows = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_candidate_log(path, rows):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


STOP_TERMS = {
    "서울", "서울시", "시민", "문제", "사업", "지원", "관련", "대한", "위한",
    "통해", "있는", "있다", "한다", "필요", "확인", "실제", "경우", "여부",
}


def issue_tokens(*values):
    return {
        term
        for value in values
        for term in re.findall(r"[가-힣A-Za-z0-9]{2,}", compact(value))
        if term not in STOP_TERMS
    }


def similarity(left, right):
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def same_issue(left, right):
    headline = similarity(
        issue_tokens(left.get("headline")),
        issue_tokens(right.get("headline")),
    )
    structure = similarity(
        issue_tokens(left.get("subject"), left.get("affected_group"), left.get("mechanism")),
        issue_tokens(right.get("subject"), right.get("affected_group"), right.get("mechanism")),
    )
    affected = similarity(
        issue_tokens(left.get("affected_group")),
        issue_tokens(right.get("affected_group")),
    )
    if left.get("document_id") == right.get("document_id"):
        return (
            headline >= 0.45
            or structure >= 0.50
            or (
                left.get("signal_type") == right.get("signal_type")
                and affected >= 0.50
                and structure >= 0.34
            )
        )
    return (
        left.get("signal_type") == right.get("signal_type")
        and affected >= 0.55
        and (headline >= 0.68 or structure >= 0.68)
    )


def group_for_review(rows):
    """Keep raw evidence, but show one card per semantic issue."""
    ordered = sorted(
        rows,
        key=lambda row: (
            row["broadcast_potential"],
            row["meeting_date"],
            row["candidate_id"],
        ),
        reverse=True,
    )
    groups = []
    for row in ordered:
        target = next(
            (group for group in groups if same_issue(group["representative"], row)),
            None,
        )
        if target is None:
            groups.append({"representative": row, "members": [row]})
        else:
            target["members"].append(row)

    review = []
    for group in groups:
        representative = dict(group["representative"])
        members = group["members"]
        anchors = []
        seen_anchors = set()
        unknowns = []
        for row in members:
            anchor_key = (row["document_id"], row["anchor_quote"])
            if anchor_key not in seen_anchors and len(anchors) < 5:
                seen_anchors.add(anchor_key)
                anchors.append({
                    "source_name": row["source_name"],
                    "meeting_date": row["meeting_date"],
                    "document_url": row["document_url"],
                    "anchor_quote": row["anchor_quote"],
                    "evidence_status": row["evidence_status"],
                })
            for value in row.get("unknowns", []):
                if value not in unknowns:
                    unknowns.append(value)
        representative["unknowns"] = unknowns[:8]
        representative["related_evidence_count"] = len(members)
        representative["related_document_count"] = len({
            row["document_id"] for row in members
        })
        representative["related_sources"] = sorted({
            row["source_name"] for row in members
        })
        representative["supporting_anchors"] = anchors
        review.append(representative)
    return review


def empty_state():
    return {"schema": STATE_SCHEMA, "documents": {}, "updated_at_kst": ""}


def normalize_state(value):
    if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
        value = empty_state()
    value.setdefault("documents", {})
    return value


def analyze(documents, *, state, candidate_path, api_key, model, max_calls):
    existing = load_candidate_log(candidate_path)
    known_ids = {row["candidate_id"] for row in existing}
    added = []
    errors = []
    calls = 0

    doc_chunks = {row["document_id"]: chunks(row["body"]) for row in documents}
    for row in documents:
        state["documents"].setdefault(row["document_id"], {
            "next_chunk": 0,
            "complete": False,
            "error_count": 0,
            "candidate_count": 0,
        })

    while calls < max_calls:
        progress = False
        for document in documents:
            if calls >= max_calls:
                break
            document_id = document["document_id"]
            document_state = state["documents"][document_id]
            passages = doc_chunks[document_id]
            index = int(document_state["next_chunk"])
            if document_state["complete"]:
                continue
            if index >= len(passages):
                document_state["complete"] = True
                continue
            passage = passages[index]
            calls += 1
            try:
                answer = call_model(
                    model,
                    api_key,
                    {
                        "document_id": document_id,
                        "source_name": document["source_name"],
                        "meeting_date": document["meeting_date"],
                        "title": document["title"],
                        "document_url": document["document_url"],
                        "chunk_number": index + 1,
                        "chunk_count": len(passages),
                    },
                    passage,
                )
                items = answer.get("items")
                if not isinstance(items, list):
                    raise ValueError("Semantic response items missing")
                for item in items:
                    validated = validate_item(item, passage)
                    candidate_id = hashlib.sha256(
                        (document_id + "\n" + validated["anchor_quote"]).encode("utf-8")
                    ).hexdigest()[:20]
                    if candidate_id in known_ids:
                        continue
                    known_ids.add(candidate_id)
                    candidate = {
                        "candidate_id": candidate_id,
                        "document_id": document_id,
                        "source_id": document["source_id"],
                        "source_name": document["source_name"],
                        "meeting_date": document["meeting_date"],
                        "document_url": document["document_url"],
                        "chunk_number": index + 1,
                        **validated,
                        "review_status": "UNREVIEWED",
                    }
                    added.append(candidate)
                    document_state["candidate_count"] += 1
                document_state["next_chunk"] = index + 1
                document_state["error_count"] = 0
                if document_state["next_chunk"] >= len(passages):
                    document_state["complete"] = True
                progress = True
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                document_state["error_count"] = int(document_state["error_count"]) + 1
                errors.append({
                    "document_id": document_id,
                    "chunk_number": index + 1,
                    "error_type": type(exc).__name__,
                    "attempt": document_state["error_count"],
                })
                if document_state["error_count"] >= 3:
                    document_state["next_chunk"] = index + 1
                    document_state["error_count"] = 0
                    progress = True
        if not progress:
            break

    append_candidate_log(candidate_path, added)
    state["updated_at_kst"] = datetime.now(KST).isoformat(timespec="seconds")
    all_candidates = existing + added
    grouped_review = group_for_review(all_candidates)
    review = grouped_review[:50]
    return {
        "schema": 1,
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "mode": "FULL_TEXT_SEMANTIC_READING",
        "document_count": len(documents),
        "completed_document_count": sum(
            bool(state["documents"][row["document_id"]]["complete"]) for row in documents
        ),
        "model_call_count": calls,
        "new_candidate_count": len(added),
        "candidate_total": len(all_candidates),
        "review_candidate_count": len(grouped_review),
        "duplicate_collapsed_count": len(all_candidates) - len(grouped_review),
        "error_count": len(errors),
        "selection_boundary": (
            "이 결과는 의미 구조를 추출한 검토 단서이며 기사 후보 확정이 아니다. "
            "반복성·다른 자치구 비교·현장 취재 가능성은 다음 통합 단계에서 판정한다."
        ),
        "review_candidates": review,
        "errors": errors,
    }


def render(payload):
    lines = [
        "# 의회 회의록 의미 분석 검토",
        "",
        f"- 아카이브 문서: {payload['document_count']}건",
        f"- 문서 전체 분석 완료: {payload['completed_document_count']}건",
        f"- 이번 실행 분석 호출: {payload['model_call_count']}회",
        f"- 이번 실행 새 단서: {payload['new_candidate_count']}건",
        f"- 누적 원문 단서: {payload['candidate_total']}건",
        f"- 중복 통합 뒤 검토 사안: {payload['review_candidate_count']}건",
        f"- 묶어서 줄인 중복: {payload['duplicate_collapsed_count']}건",
        f"- 오류: {payload['error_count']}건",
        "",
        "> 발언을 사실로 확정하지 않습니다. 새 사업에 실적 자료가 없다는 이유만으로 "
        "버리지 않고, 확인할 항목을 분리합니다.",
    ]
    for index, row in enumerate(payload["review_candidates"][:20], 1):
        lines.extend([
            "",
            f"## {index}. {row['headline']}",
            f"- 출처: [{row['source_name']} {row['meeting_date']}]({row['document_url']})",
            f"- 구조: {row['affected_group']} · {row['mechanism']}",
            f"- 시민적 의미: {row['civic_importance']}",
            f"- 시민 질문: {row['public_question']}",
            f"- 통념 밖 질문: {row['counterintuitive_question']}",
            f"- 원문 앵커: {row['anchor_quote']}",
            f"- 검증 전 상태: {row['evidence_status']}",
            f"- 확인 필요: {' / '.join(row['unknowns'])}",
            f"- 관련 근거: {row['related_evidence_count']}건 · 문서 {row['related_document_count']}건 · {' / '.join(row['related_sources'])}",
            f"- 방송 확장 점수: {row['broadcast_potential']}",
        ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime",
        type=Path,
        default=ROOT / ".runtime" / "council-archive",
    )
    parser.add_argument("--output", type=Path, default=BASE / "output")
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--max-calls", type=int, choices=(6, 12, 24), default=12)
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required")
    documents = read_archive(args.runtime / "documents.jsonl.gz")
    if not documents:
        raise ValueError("Council archive is empty")

    state_path = args.runtime / "analysis_state.json"
    state = normalize_state(read_json(state_path))
    payload = analyze(
        documents,
        state=state,
        candidate_path=args.runtime / "semantic_candidates.jsonl",
        api_key=api_key,
        model=args.model,
        max_calls=args.max_calls,
    )
    write_json(state_path, state)
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "analysis_latest.json", payload)
    (args.output / "ANALYSIS_SUMMARY.md").write_text(render(payload), encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(render(payload))
    print(json.dumps({
        "document_count": payload["document_count"],
        "completed_document_count": payload["completed_document_count"],
        "model_call_count": payload["model_call_count"],
        "new_candidate_count": payload["new_candidate_count"],
        "candidate_total": payload["candidate_total"],
        "review_candidate_count": payload["review_candidate_count"],
        "duplicate_collapsed_count": payload["duplicate_collapsed_count"],
        "error_count": payload["error_count"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
