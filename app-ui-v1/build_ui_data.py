import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app-ui-v1" / "data" / "latest.json"

def load(path, default):
    try:
        return json.loads((ROOT / path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default

registry = load("source-onboarding-v1/source_maturity_registry.json", {"sources": []})
cards_doc = load("source-scout-v1/output/editorial_review_cards_latest.json", {"review_cards": []})
summary = load("source-scout-v1/output/review_summary_latest.json", {})
manifest = load("daily-briefing-v5/output/run_manifest_latest.json", {})
construction_state = load("construction-watch-pilot/output/state_latest.json", {})
interest_queue = load("interest-signal-pilot/output/review_queue_latest.json", {"items": []})
decisions = load("source-scout-v1/output/editorial_decisions.json", [])

sources = [[
    s.get("source_name", s.get("source_id", "미상")),
    s.get("maturity", "UNKNOWN"),
    s.get("candidate_role", "미분류"),
] for s in registry.get("sources", [])]

topic_aliases = {
    "seoul_bus_wage": "서울 시내버스 통상임금·노사 분쟁",
    "sign_language_centers": "서울 자치구 수어통역센터 재정·서비스",
    "seoul_rent_fraud": "서울 전세사기 피해 인정·지원",
}

cards = []
card_ids = set()
card_topics = set()
for card in cards_doc.get("review_cards", [])[:8]:
    candidate_id = card.get("candidate_id", "")
    card_ids.add(candidate_id)
    card_topic = card.get("context_subject", "").strip()
    if card_topic:
        card_topics.add(card_topic)
    source_date = card.get("source_date") or card.get("speech_date") or "기준일 미상"
    cards.append([
        card.get("context_subject") or card.get("fact", "")[:80],
        card.get("source_name", "미상"),
        source_date,
        card.get("question") or card.get("fact", ""),
        card.get("url", ""),
        card.get("editor_judgment", "PENDING"),
        candidate_id,
    ])

status_map = {"탈락": "기각", "보류": "보류", "장기 관찰": "관찰", "통과": "통과"}
history = []
try:
    with (ROOT / "agent-system-v1" / "ITEM_LEDGER.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            status = status_map.get(row.get("status", ""), row.get("status", "미판정"))
            history.append([
                row.get("canonical_topic", "제목 미상"),
                status,
                f'{row.get("first_seen", "")}~{row.get("last_seen", "")}',
                row.get("structural_question", "") or row.get("question_hypothesis", ""),
                row.get("source_report", ""),
            ])
except (FileNotFoundError, UnicodeError):
    pass

decision_map = {str(item.get("candidate_id")): item for item in decisions if item.get("candidate_id")}
pending_items = []
quarantine = []
seen_ids = set()
seen_topics = set()

try:
    with (ROOT / "source-scout-v1" / "HUMAN_REVIEW_QUEUE.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            candidate_id = row.get("candidate_id", "")
            if not candidate_id or candidate_id in card_ids or candidate_id in seen_ids:
                continue
            seen_ids.add(candidate_id)
            if row.get("review_eligible", "").strip().lower() != "true":
                continue
            decision = decision_map.get(candidate_id, {})
            if decision.get("decision") in {"COMPLETE", "DISCARD"}:
                continue

            context_rule = row.get("context_rule", "")
            title = topic_aliases.get(context_rule) or row.get("context_subject", "").strip()
            question = (row.get("question", "") or row.get("central_question", "")).strip()
            if not title:
                if "통상임금" in question:
                    title = topic_aliases["seoul_bus_wage"]
                elif "수어통역" in question:
                    title = topic_aliases["sign_language_centers"]
                elif "전세사기" in question:
                    title = topic_aliases["seoul_rent_fraud"]
            if not title:
                quarantine.append({
                    "source": row.get("source_name", "미상"),
                    "reason": "사안명이 없어 검토 목록에서 제외",
                    "candidate_id": candidate_id,
                })
                continue
            topic_key = title
            if topic_key in card_topics or topic_key in seen_topics:
                continue
            seen_topics.add(topic_key)
            pending_items.append([
                title,
                row.get("source_name", "미상"),
                f'{row.get("first_seen", "")}~{row.get("last_seen", "")}',
                question,
                row.get("url", ""),
                row.get("editor_judgment") or "PENDING",
                candidate_id,
            ])
except (FileNotFoundError, UnicodeError):
    pass

observations = []
for event in construction_state.get("events", {}).values():
    if event.get("category") == "EXTENSION" and int(event.get("extension_days", 0) or 0) >= 14:
        observations.append([
            event.get("title", "공사명 미상"),
            "서울 건설알림이 변화 관측",
            f'{event.get("before_completion", "기존 일정")} → {event.get("after_completion", "변경 일정")}',
            "공기 연장 사유가 무엇이며 시민 이용·예산·안전 영향으로 이어졌는가?",
            event.get("source_url", ""),
            "추가 확인",
        ])
observations = observations[:10]

source_counts = Counter(item[1] for item in pending_items)
source_performance = [[name, str(count), "판정 대기"] for name, count in sorted(source_counts.items())]
source_groups = []
for source_name in sorted(source_counts):
    source_groups.append({
        "source": source_name,
        "count": source_counts[source_name],
        "items": [item for item in pending_items if item[1] == source_name],
    })

def signal_priority(item):
    """Order review work; this score never promotes a signal to a story."""
    headline = item.get("headline") or item.get("seed_event", "")
    concrete = ("철거", "폐쇄", "사망", "부상", "고발", "기소", "체납", "미지급")
    return (item.get("screening_priority") == "높음", sum(word in headline for word in concrete))


ranked_interest = sorted(interest_queue.get("items", []), key=signal_priority, reverse=True)
discovery_signals = []
seen_queries = set()
for item in ranked_interest:
    query = item.get("source_query", "")
    if query in seen_queries:
        continue
    seen_queries.add(query)
    discovery_signals.append({
        "review_id": item.get("review_id", ""),
        "headline": item.get("headline") or item.get("source_headline") or item.get("seed_event", "제목 미상"),
        "source": item.get("source_name", "검색 관심도·뉴스 확산"),
        "observed_signal": item.get("observed_signal", "검색 결과에 기사 제목이 표시됨"),
        "source_context_status": item.get("source_context_status", "TITLE_ONLY"),
        "problem_status": item.get("problem_status", "UNASSESSED"),
        "first_check": item.get("first_check", "기사 본문 확인"),
        "counterpossibility": item.get("counterpossibility", ""),
        "evidence": item.get("evidence", []),
    })
    if len(discovery_signals) >= 3:
        break

# The search feed contains titles, not verified article bodies. Editorial candidates
# need an explicit later decision based on context and a meaningful reporting question.
ui_editorial_brief = {
    "schema": 4,
    "input": "interest-signal-pilot/review_queue_latest.json",
    "generated_at_utc": interest_queue.get("generated_at_utc"),
    "count": 0,
    "candidates": [],
    "discovery_count": len(discovery_signals),
    "discovery_signals": discovery_signals,
    "queue_status": "본문 검토 전 탐색 신호" if discovery_signals else "탐색 신호 없음",
}

data = {
    "lastRun": interest_queue.get("generated_at_utc") or manifest.get("generated_at_kst", "미확인"),
    "dataMode": "실제 산출물",
    "editorialBrief": ui_editorial_brief,
    "metrics": [
        ["검토 대상 소스", str(len(sources))],
        ["사람 판정 대기", str(len(pending_items))],
        ["문맥 보강 필요", str(len(quarantine))],
        ["브리핑 연결", "가능" if manifest.get("publishable") else "보류"],
        ["검증할 신호", str(len(discovery_signals))],
        ["편집 후보", str(len(ui_editorial_brief["candidates"]))],
    ],
    "sources": sources,
    "cards": cards,
    "pending": pending_items,
    "pendingGroups": source_groups,
    "observations": observations,
    "quarantineCount": len(quarantine),
    "history": history,
    "sourcePerformance": source_performance,
    "queue": [
        ["사람 판정", f'{summary.get("labeled", 0)}/{summary.get("generated", 0)}건 완료'],
        ["브리핑", "공개 가능" if manifest.get("publishable") else "검토 필요"],
        ["데이터 신선도", "정상" if not manifest.get("stale_at_generation") else "오래됨"],
    ],
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
