#!/usr/bin/env python3
"""Semantic shadow review for repeated YouTube citizen-signal clusters.

The collector's keyword clusters are discovery aids. This module adds a separate
content gate and never promotes a video or cluster to an article candidate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect_source_material_v2_1 import build_clusters


BASE = Path(__file__).resolve().parent
LEDGER = BASE / "output" / "youtube_signal_ledger_v2_1.json"
CONFIG = BASE / "config" / "editorial_lenses.json"
OUTPUT = BASE / "output" / "youtube_semantic_shadow_latest.json"
OPENAI = "https://api.openai.com/v1/responses"
KST = timezone(timedelta(hours=9))
MAX_CLUSTERS = 3
MAX_RECORDS_PER_CLUSTER = 6
QUALIFIED_TYPES = {"당사자 가능성", "상담·지원", "현장·운영자"}
DIRECT_TYPES = {"당사자 가능성", "현장·운영자"}


INSTRUCTIONS = """당신은 서울 시민 대상 기획기사의 유튜브 시민 신호 검증자다.
입력은 검색어와 규칙으로 묶인 영상 군집이며, 군집 이름은 사실도 결론도 아니다.
제목과 설명의 실제 문맥만 읽고 아래를 판정한다.

- REVIEW: 서로 다른 채널의 두 영상 이상이 같은 실제 경험·행동 변화·운영 장면을 말하고,
  그 현상 자체가 서울과 직접 연결된다. 확인 전 가설이므로 기사 후보라고 부르지 않는다.
- HOLD: 의미 있는 단서는 있으나 같은 현상인지, 서울 현상인지, 실제 경험인지 더 확인해야 한다.
- NO_SIGNAL: 검색어 우연 일치, 법률·생활 조언, 홍보, 뉴스 재유통, AI 창작·재연,
  유명인 일화, 일반 브이로그처럼 군집이 주장한 현상을 뒷받침하지 않는다.

서울이라는 단어가 제목에 있다는 이유, 동일 검색어에 잡혔다는 이유, 조회수가 높다는 이유만으로
REVIEW하지 않는다. 군집 이름을 질문에 그대로 넣지 말고 영상에 실제로 나타난 선택·손실·변화가
무엇인지 먼저 적는다. 피해를 전제하지 말고 다른 설명과 첫 확인 경로를 반드시 제시한다.
anchor_quote는 제공된 한 영상의 제목 또는 설명에 연속해서 존재하는 문장이어야 한다.
"""


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["assessments"],
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "cluster_id", "verdict", "anchor_video_id", "anchor_quote",
                    "observed_pattern", "seoul_connection", "repetition_basis",
                    "citizen_stake_to_check", "test_question",
                    "alternative_explanation", "first_check", "scene_path", "reason",
                ],
                "properties": {
                    "cluster_id": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["REVIEW", "HOLD", "NO_SIGNAL"]},
                    "anchor_video_id": {"type": "string"},
                    "anchor_quote": {"type": "string"},
                    "observed_pattern": {"type": "string"},
                    "seoul_connection": {"type": "string"},
                    "repetition_basis": {"type": "string"},
                    "citizen_stake_to_check": {"type": "string"},
                    "test_question": {"type": "string"},
                    "alternative_explanation": {"type": "string"},
                    "first_check": {"type": "string"},
                    "scene_path": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        }
    },
}


def compact(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_cluster_id(agenda: str, name: str) -> str:
    raw = f"{agenda}|{name}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def label_lanes(record: dict) -> list[str]:
    return sorted({
        compact(label.get("lane"))
        for label in record.get("query_labels", [])
        if compact(label.get("lane"))
    })


def supporting_rows(cluster: dict) -> list[dict]:
    return [
        row for row in cluster.get("records", [])
        if row.get("source_archetype") in QUALIFIED_TYPES
    ]


def select_clusters(records: list[dict], config: dict,
                    max_clusters: int = MAX_CLUSTERS) -> tuple[list[dict], list[dict]]:
    """Return strict semantic-review inputs and deterministic exclusions."""
    if not 0 <= max_clusters <= MAX_CLUSTERS:
        raise ValueError("YouTube semantic cluster limit exceeded")
    selected, excluded = [], []
    for cluster in build_clusters(records, config):
        if cluster.get("readiness") != "CORROBORATED":
            continue
        rows = supporting_rows(cluster)
        direct = [row for row in rows if row.get("source_archetype") in DIRECT_TYPES]
        scene = [row for row in rows if row.get("signal_markers")]
        channels = {compact(row.get("channel")) for row in rows if compact(row.get("channel"))}
        seoul_rows = [row for row in rows if row.get("seoul_place_terms")]
        reasons = []
        if len(channels) < 2:
            reasons.append("독립 비언론 채널 2개 미만")
        if len(scene) < 2:
            reasons.append("행동·손실 표현 영상 2개 미만")
        if not direct:
            reasons.append("당사자·현장 영상 없음")
        if not seoul_rows:
            reasons.append("검토 가능 영상 안에 서울 지역 단서 없음")
        cluster_id = stable_cluster_id(cluster["agenda"], cluster["cluster"])
        if reasons:
            excluded.append({
                "cluster_id": cluster_id,
                "cluster": cluster["cluster"],
                "reason": " / ".join(reasons),
            })
            continue
        ordered = sorted(
            rows,
            key=lambda row: (
                not bool(row.get("seoul_place_terms")),
                row.get("source_archetype") not in DIRECT_TYPES,
                not bool(row.get("signal_markers")),
                compact(row.get("published_at")),
            ),
        )
        sample = []
        for row in ordered[:MAX_RECORDS_PER_CLUSTER]:
            sample.append({
                "video_id": compact(row.get("id")),
                "title": compact(row.get("title"))[:300],
                "description": compact(row.get("description"))[:1000],
                "channel": compact(row.get("channel"))[:120],
                "published_at": compact(row.get("published_at")),
                "url": compact(row.get("url")),
                "source_archetype": compact(row.get("source_archetype")),
                "seoul_place_terms": row.get("seoul_place_terms") or [],
                "signal_markers": row.get("signal_markers") or [],
                "first_person_markers": row.get("first_person_markers") or [],
                "query_lanes": label_lanes(row),
            })
        selected.append({
            "cluster_id": cluster_id,
            "agenda": cluster["agenda"],
            "search_cluster_name": cluster["cluster"],
            "collector_readiness": cluster["readiness"],
            "independent_qualified_channels": len(channels),
            "scene_records": len(scene),
            "seoul_supporting_records": len(seoul_rows),
            "videos": sample,
        })
        if len(selected) >= max_clusters:
            break
    return selected, excluded


def call_model(clusters: list[dict], model: str, api_key: str) -> dict:
    payload = {
        "model": model,
        "store": False,
        "max_output_tokens": 6000,
        "input": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": json.dumps({"clusters": clusters}, ensure_ascii=False)},
        ],
        "text": {"format": {
            "type": "json_schema", "name": "youtube_semantic_shadow",
            "strict": True, "schema": SCHEMA,
        }},
    }
    request = urllib.request.Request(
        OPENAI,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        answer = json.load(response)
    parts = [
        part.get("text", "")
        for item in answer.get("output", []) if item.get("type") == "message"
        for part in item.get("content", []) if part.get("type") == "output_text"
    ]
    if answer.get("status") != "completed" or not parts:
        raise ValueError("유튜브 의미 검토 모델 응답 미완료")
    return json.loads("".join(parts))


def validate_assessments(clusters: list[dict], answer: dict) -> list[dict]:
    raw = answer.get("assessments")
    if not isinstance(raw, list):
        raise ValueError("유튜브 의미 검토 목록 누락")
    by_id = {row["cluster_id"]: row for row in clusters}
    seen, output = set(), []
    for assessment in raw:
        cluster_id = compact(assessment.get("cluster_id"))
        if cluster_id not in by_id or cluster_id in seen:
            continue
        seen.add(cluster_id)
        cluster = by_id[cluster_id]
        verdict = assessment.get("verdict")
        video_id = compact(assessment.get("anchor_video_id"))
        quote = compact(assessment.get("anchor_quote"))
        videos = {row["video_id"]: row for row in cluster["videos"]}
        anchor = videos.get(video_id)
        material = compact((anchor or {}).get("title")) + " " + compact((anchor or {}).get("description"))
        required = [
            compact(assessment.get(name)) for name in (
                "observed_pattern", "seoul_connection", "repetition_basis",
                "citizen_stake_to_check", "test_question", "alternative_explanation",
                "first_check", "scene_path", "reason",
            )
        ]
        invalid = (
            verdict not in {"REVIEW", "HOLD", "NO_SIGNAL"}
            or not anchor or len(quote) < 12 or quote not in material
            or any(len(value) < 8 for value in required)
            or "?" not in compact(assessment.get("test_question"))
        )
        if invalid:
            output.append({
                "cluster_id": cluster_id,
                "search_cluster_name": cluster["search_cluster_name"],
                "verdict": "HOLD",
                "reason": "모델 판정의 원문 인용·질문·검증 경로 형식이 불충분함",
            })
            continue
        output.append({
            "cluster_id": cluster_id,
            "search_cluster_name": cluster["search_cluster_name"],
            "verdict": verdict,
            "anchor_video_id": video_id,
            "anchor_url": anchor["url"],
            "anchor_quote": quote,
            "observed_pattern": required[0],
            "seoul_connection": required[1],
            "repetition_basis": required[2],
            "citizen_stake_to_check": required[3],
            "test_question": required[4],
            "alternative_explanation": required[5],
            "first_check": required[6],
            "scene_path": required[7],
            "reason": required[8],
            "source_stage": "유튜브 의미 검증 그림자",
            "claim_status": "영상 서술·미검증",
            "production_eligible": False,
            "briefing_output": "NONE",
        })
    for cluster_id, cluster in by_id.items():
        if cluster_id not in seen:
            output.append({
                "cluster_id": cluster_id,
                "search_cluster_name": cluster["search_cluster_name"],
                "verdict": "HOLD",
                "reason": "모델 평가 누락",
            })
    return output


def render(payload: dict) -> str:
    lines = [
        "# 유튜브 시민 신호 의미 검증", "",
        "검색어 군집을 곧바로 아이템으로 보지 않고, 영상 제목·설명에 실제로 반복되는 서울 시민 현상인지 확인한다.",
        "모든 결과는 검증 전용이며 브리핑·공개 화면·아이템 장부에 자동 반영하지 않는다.", "",
        f"사전 검토 {payload['prefilter_count']}개 군집 · 의미 검토 {payload['reviewed_count']}개 · "
        f"추가 검토 {payload['review_count']}개 · 모델 호출 {payload['model_calls']}회", "",
    ]
    for row in payload.get("assessments", []):
        lines.extend([
            f"## {row['search_cluster_name']} · {row['verdict']}",
            f"- 판단 이유: {row['reason']}",
        ])
        if row.get("anchor_quote"):
            lines.extend([
                f"- 원문 단서: {row['anchor_quote']}",
                f"- 실제 관찰: {row['observed_pattern']}",
                f"- 서울 연결: {row['seoul_connection']}",
                f"- 반복 근거: {row['repetition_basis']}",
                f"- 가를 질문: {row['test_question']}",
                f"- 다른 설명: {row['alternative_explanation']}",
                f"- 첫 확인: {row['first_check']}",
                f"- 방송 장면 가능성: {row['scene_path']}",
                f"- 원본: {row['anchor_url']}",
            ])
        lines.append("")
    if not payload.get("assessments"):
        lines.append("이번 실행에는 의미 검토에 올릴 조건을 갖춘 군집이 없다. 이는 유튜브에 시민 신호가 없다는 뜻이 아니다.")
    return "\n".join(lines).rstrip() + "\n"


def run(ledger_path: Path, config_path: Path, output_path: Path,
        model: str, dry_run: bool = False, max_clusters: int = MAX_CLUSTERS,
        api_key: str = "") -> dict:
    records = json.loads(ledger_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    selected, excluded = select_clusters(records, config, max_clusters)
    payload = {
        "schema": 1,
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "status": "PREFILTER_ONLY" if dry_run else "NO_ELIGIBLE_CLUSTER",
        "record_count": len(records),
        "prefilter_count": len(selected),
        "reviewed_count": 0,
        "review_count": 0,
        "model_calls": 0,
        "selected_clusters": selected,
        "prefilter_exclusions": excluded,
        "assessments": [],
        "production_eligible": False,
        "briefing_output": "NONE",
        "automatic_ledger_write": False,
        "note": "검색 군집의 의미 검증용 그림자 결과이며 사실 확인·기사 후보가 아니다.",
    }
    if selected and not dry_run:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY 미설정")
        payload["assessments"] = validate_assessments(
            selected, call_model(selected, model, api_key))
        payload["model_calls"] = 1
        payload["reviewed_count"] = len(payload["assessments"])
        payload["review_count"] = sum(
            row.get("verdict") == "REVIEW" for row in payload["assessments"])
        payload["status"] = "SHADOW_REVIEW_READY" if payload["review_count"] else "NO_SEMANTIC_SIGNAL"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(render(payload))
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--max-clusters", type=int, default=MAX_CLUSTERS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    payload = run(
        args.ledger, args.config, args.output, args.model, args.dry_run,
        args.max_clusters, os.getenv("OPENAI_API_KEY", ""),
    )
    print(json.dumps({
        "status": payload["status"],
        "prefilter_count": payload["prefilter_count"],
        "review_count": payload["review_count"],
        "model_calls": payload["model_calls"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

