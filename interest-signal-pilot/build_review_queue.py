#!/usr/bin/env python3
"""Turn discovery signals into structural editorial questions for human review."""
from __future__ import annotations
import json, re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "interest-signal-pilot" / "output" / "interest_signals_latest.json"
OUTPUT = ROOT / "interest-signal-pilot" / "output" / "review_queue_latest.json"
TOPIC_LABELS = {
    "서울 민원": "공공서비스의 지역 격차",
    "서울 건설 공사 지연": "도시사업 지연과 책임",
    "서울 안전 사고": "도시 안전의 사각지대",
    "서울 재개발 갈등": "재개발 이익과 부담의 충돌",
    "서울 교통 불편": "교통 불편과 이동권",
    "서울 주거 피해": "주거 비용과 피해",
    "서울 복지 공백": "복지 접근의 공백",
    "서울 자치구 논란": "자치구 행정의 책임",
}
QUESTION_TEMPLATES = {
    "서울 민원": "반복되는 민원이 특정 동네·시설 이용자에게만 쌓이는 이유는 무엇이며, 서울시와 자치구의 처리 기준은 같은가?",
    "서울 건설 공사 지연": "공사 일정이 늦어진 비용과 불편을 누가 부담했으며, 지연을 사전에 막거나 공개할 장치는 작동했는가?",
    "서울 안전 사고": "사고 위험이 드러난 뒤에도 같은 장소·이용자에게 위험이 남은 이유는 무엇이며, 관리 책임은 어디에 있는가?",
    "서울 재개발 갈등": "개발 이익과 이주·생활 부담이 누구에게 다르게 배분되며, 주민 의견은 의사결정에 실제 반영됐는가?",
    "서울 교통 불편": "교통 대책의 편익은 누구에게 돌아가고 불편·추가 비용은 어느 지역과 이용자에게 전가되는가?",
    "서울 주거 피해": "주거 피해가 특정 지역과 계약 유형에 집중되는 이유는 무엇이며, 피해 예방·회복 장치는 작동했는가?",
    "서울 복지 공백": "지원 제도가 있어도 이용하지 못하는 시민이 생기는 경로는 무엇이며, 자치구별 접근 차이는 얼마나 큰가?",
    "서울 자치구 논란": "같은 행정 기준이 자치구마다 다르게 적용되는 이유는 무엇이며, 설명·책임 절차는 충분했는가?",
}

def published_key(row: dict) -> float:
    try:
        return parsedate_to_datetime(row.get("published_at", "")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0.0

def story_key(title: str) -> str:
    value = re.sub(r"[^0-9a-z가-힣]+", " ", title.lower())
    return re.sub(r"\s+", " ", value).strip()[:100]

def make_item(row: dict) -> dict:
    title = row.get("title", "").strip()
    topic = row.get("query", "서울 지역 현안")
    label = TOPIC_LABELS.get(topic, "서울 시민 생활의 구조적 격차")
    concise = re.split(r"\s[-|]\s", title, maxsplit=1)[0].strip()
    question = QUESTION_TEMPLATES.get(topic, "이 사건의 부담과 책임이 특정 시민에게 집중되는 구조는 무엇이며, 서울 다른 지역에서도 반복되는가?")
    return {
        "review_id": row.get("url", "").split("/")[-1][:24] or title[:24],
        "title_options": [f"{label}: {concise}", f"{concise}에서 서울 전체의 {label}을 묻다"],
        "seed_event": title,
        "topic": topic,
        "topic_label": label,
        "structural_question": question,
        "scope_hypothesis": "한 지역의 사례가 서울 다른 자치구에서도 반복되는지 비교한다.",
        "reason": "지역 뉴스 관심 신호에서 출발해 서울 전체의 제도·배치·책임 구조로 확장할 수 있는지 검토하기 위해",
        "conflict_groups": ["직접 피해 시민·이용자", "인근 주민", "서울시·자치구", "사업자·기관"],
        "citizen_questions": [
            question,
            f"서울의 다른 자치구에서도 {label}이 반복되는지 어떤 자료와 현장을 비교해야 하는가?",
            "문제가 확인되면 바뀌어야 할 예산·규정·운영 주체는 누구인가?",
        ],
        "reporting_paths": ["서울시·자치구 공식 계획·예산·통계 확인", "25개 자치구 유사 사례 비교", "당사자·주민·책임 기관 인터뷰"],
        "evidence": [{"type": "news", "url": row.get("url"), "published_at": row.get("published_at")}],
        "status": "DISCOVERY_ONLY",
        "editorial_status": "확장 질문 초안",
        "needs_human_review": True,
        "needs_official_cross_check": True,
        "source_name": "검색 관심도·뉴스 확산",
        "source_query": topic,
        "editorial_eligible": row.get("editorial_eligible", True),
        "editorial_reason": row.get("editorial_reason", ""),
    }

def main() -> int:
    payload = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = sorted(payload.get("news_signals", []), key=published_key, reverse=True)
    grouped = {}
    for row in rows:
        grouped.setdefault(row.get("query", "기타"), []).append(row)
    unique, seen = [], set()
    while grouped and len(unique) < 30:
        for query in list(grouped):
            row = grouped[query].pop(0)
            key = story_key(row.get("title", ""))
            if key and key not in seen:
                seen.add(key)
                unique.append(row)
            if not grouped[query]:
                del grouped[query]
            if len(unique) >= 30:
                break
    queue = [make_item(row) for row in unique]
    output = {"schema": 3, "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source_snapshot": payload.get("generated_at_utc"), "candidate_ready": False, "review_count": len(queue), "items": queue, "policy": "관심 신호는 자동 확정 후보가 아니며 출발 사건·구조 질문·시민 영향·확인 경로를 사람이 판정한다."}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"review_queue={len(queue)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
