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
}
REVIEW_FIELDS = [
    "first_seen",
    "last_seen",
    "candidate_id",
    "lane",
    "source_id",
    "source_name",
    "auto_score",
    "evidence_anchor",
    "text",
    "question",
    "url",
    "editor_judgment",
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
    if row.get("source_id") == "seoul_open_data":
        return "이 신규 데이터로 기존 발표의 총량을 지역·대상·시간대별로 분해할 수 있는가?"
    return "이 자료가 발굴된 질문의 지역·대상·업종 집중을 실제로 확인할 수 있는가?"


def discovery_question(row: dict) -> str:
    text = row.get("text", "")
    anchor = row.get("evidence_anchor") or row.get("signals", {}).get("evidence_anchor", "NONE")
    if anchor == "NONE":
        return "근거 앵커 없음 — 질문 점수 평가 제외"
    if "장애인콜택시" in text or "UD택시" in text:
        return (
            "서울 전역 12대와 06~15시 운행은 실제 요청량과 병원 이동 수요를 감당하는가, "
            "자치구·시간대별 미배차 격차는 얼마나 큰가?"
        )
    if "전세사기" in text:
        return (
            "인정 피해 1만 1,664가구와 약 1조 9,860억 원은 어느 자치구·주택유형·"
            "임대인 관계망에 집중됐고, 현행 지원은 그 집중도와 맞는가?"
        )
    if "시내버스" in text and ("소송" in text or "준공영제" in text):
        return (
            "최대 1조 원대 소송 부담은 운송사·서울시·시민 사이에 어떻게 배분되며, "
            "준공영제의 어떤 계약·관리 공백이 이 비용을 만들었는가?"
        )
    if "침수" in text and ("방문" in text or "이력" in text):
        return (
            "침수 피해 규모가 큰 지역일수록 현장 점검과 후속 조치가 우선됐는가, "
            "시장 방문·지원 일정은 자치구별로 편중됐는가?"
        )
    if "긴급교실안심" in text or "SEM" in text:
        return (
            "긴급교실안심SEM 도입 뒤 교사의 개입과 학생 보호는 실제로 늘었는가, "
            "사건 유형·학교별 이용 격차와 미개입 사유는 무엇인가?"
        )
    if "예산" in text or "추경" in text:
        return (
            "계획한 예산과 실제 집행 사이에 확인되는 차이는 얼마이며, "
            "그 차이가 서비스 대상·자치구별 이용에 어떤 영향을 주는가?"
        )
    return (
        "이 발언에서 확인된 문제 징후 또는 구조 자료는 무엇이며, "
        "어떤 비교가 정상 변동과 구조적 반복을 가르는가?"
    )


def unique_top(rows: list[dict], limit: int) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: item.get("score", 0), reverse=True):
        key = row.get("url") or row.get("text")
        if not key or key in seen:
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
            f"items={metric['extracted']} qualified={metric['qualified']}"
        )

    core = unique_top(
        [
            {**row, "lane": "CORE_DISCOVERY", "question": discovery_question(row)}
            for row in records
            if row["source_id"] == "council_minutes" and row.get("qualified")
        ],
        3,
    )
    auxiliary = unique_top(
        [
            {**row, "lane": "AUX_DISCOVERY", "question": discovery_question(row)}
            for row in records
            if row["source_id"] == "eungdapso" and row.get("qualified")
        ],
        1,
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
            and (row.get("signals", {}).get("evidence") or row.get("score", 0) >= 4)
        ],
        4,
    )
    return {
        "generated_at_kst": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
        "status": {
            "discovery_core": "서울시의회 회의록",
            "discovery_auxiliary": "서울시 응답소 공개민원",
            "verification_only": ["서울 열린데이터", "서울 빅데이터캠퍼스"],
            "warning": "근거 앵커를 통과한 레코드도 S0 이전 질문 씨앗이며 기사 후보가 아님",
        },
        "metrics": metrics,
        "core_discovery": core,
        "auxiliary_discovery": auxiliary,
        "verification_map": verification,
    }


def read_review_queue() -> list[dict[str, str]]:
    if not QUEUE.is_file():
        return []
    with QUEUE.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def update_review_queue(feed: dict) -> None:
    today = feed["generated_at_kst"][:10]
    prior = read_review_queue()
    by_id = {row.get("candidate_id", ""): row for row in prior}
    for row in feed["core_discovery"] + feed["auxiliary_discovery"]:
        item_id = candidate_id(row)
        current = by_id.get(item_id, {field: "" for field in REVIEW_FIELDS})
        current.update(
            {
                "first_seen": current.get("first_seen") or today,
                "last_seen": today,
                "candidate_id": item_id,
                "lane": row["lane"],
                "source_id": row["source_id"],
                "source_name": row["source_name"],
                "auto_score": str(row["score"]),
                "evidence_anchor": row.get("evidence_anchor", "NONE"),
                "text": concise(row["text"], 500),
                "question": row["question"],
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
    lines = [
        "# 역할 분리형 신규 소스 입력",
        "",
        f"- 생성: {feed['generated_at_kst']}",
        "- 상태: 아래 발굴 단서는 모두 S0 이전이며 자동으로 아이템 장부에 들어가지 않음",
        "",
        "## 핵심 발굴 — 서울시의회 회의록",
        "",
    ]
    if not feed["core_discovery"]:
        lines.extend(["- 오늘 자동 기준을 통과한 질문 씨앗 없음", ""])
    else:
        for row in feed["core_discovery"]:
            lines.extend(
                [
                    f"### {concise(row['text'], 100)}",
                    "",
                    f"- 근거 앵커: {row.get('evidence_anchor', 'NONE')}",
                    f"- 붙일 질문: {row['question']}",
                    f"- 자동 점수: {row['score']}점",
                    f"- 원문: {row['url']}",
                    "- 편집 상태: 미검증 질문 씨앗",
                    "",
                ]
            )

    lines.extend(["## 보조 발굴 — 서울시 응답소", ""])
    if not feed["auxiliary_discovery"]:
        lines.extend(["- 오늘 자동 기준을 통과한 시민 경험 단서 없음", ""])
    else:
        for row in feed["auxiliary_discovery"]:
            lines.extend(
                [
                    f"- 단서: {concise(row['text'])}",
                    f"- 근거 앵커: {row.get('evidence_anchor', 'NONE')}",
                    f"- 붙일 질문: {row['question']}",
                    f"- 원문: {row['url']}",
                    "",
                ]
            )

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
            "| 소스 | 접속 | 요청/실패 | 추출 | 자동 유효 |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for metric in feed["metrics"]:
        access = f"HTTP {metric['status']}" if metric["http_ok"] else metric["error"]
        lines.append(
            f"| {metric['name']} | {access} | {metric['requests']}/{metric['failed_requests']} | "
            f"{metric['extracted']} | {metric['qualified']} |"
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
    (history / f"daily_feed_{run_day}.json").write_text(
        json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not args.skip_review_queue:
        update_review_queue(feed)
    print(f"feed={OUTPUT / 'daily_feed_latest.json'}")
    print(f"review_queue={QUEUE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
