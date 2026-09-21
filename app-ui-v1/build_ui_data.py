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
decisions = load("source-scout-v1/output/editorial_decisions.json", [])

sources = [[s.get("source_name", s.get("source_id", "미상")), s.get("maturity", "UNKNOWN"), s.get("candidate_role", "미분류")] for s in registry.get("sources", [])]
cards = []
card_ids = set()
for card in cards_doc.get("review_cards", [])[:8]:
    candidate_id = card.get("candidate_id", "")
    card_ids.add(candidate_id)
    source_date = card.get("source_date") or card.get("speech_date") or "기준일 미상"
    cards.append([
        card.get("context_subject") or card.get("fact", "")[:80],
        f'{card.get("source_name", "미상")} · {card.get("transition_state", "상태 미상")} · 기준일 {source_date}',
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
            history.append([row.get("canonical_topic", "제목 미상"), f'{status} · {row.get("first_seen", "")}~{row.get("last_seen", "")}', row.get("structural_question", "") or row.get("question_hypothesis", ""), row.get("source_report", ""), status])
except (FileNotFoundError, UnicodeError):
    history = []

decision_map = {str(item.get("candidate_id")): item for item in decisions if item.get("candidate_id")}

pending_items = []
seen = set()
seen_topics = set()
topic_aliases = {
    "seoul_bus_wage": "서울 시내버스 통상임금·노사 분쟁",
    "sign_language_centers": "서울 자치구 수어통역센터 재정·서비스",
    "seoul_rent_fraud": "서울 전세사기 피해 인정·지원",
}
try:
    with (ROOT / "source-scout-v1" / "HUMAN_REVIEW_QUEUE.csv").open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            candidate_id = row.get("candidate_id", "")
            if not candidate_id or candidate_id in card_ids or candidate_id in seen:
                continue
            seen.add(candidate_id)
            decision = decision_map.get(candidate_id, {})
            if decision.get("decision") in {"COMPLETE", "DISCARD"}:
                continue
            question_text = row.get("question", "") or row.get("central_question", "")
            raw_title = topic_aliases.get(row.get("context_rule", "")) or row.get("context_subject") or row.get("display_fact", "").split(" — ", 1)[0]
            if not raw_title and "통상임금" in question_text:
                raw_title = topic_aliases["seoul_bus_wage"]
            elif not raw_title and "수어통역" in question_text:
                raw_title = topic_aliases["sign_language_centers"]
            elif not raw_title and "전세사기" in question_text:
                raw_title = topic_aliases["seoul_rent_fraud"]
            title = raw_title.strip()[:100] if raw_title.strip() else f'검토 후보 {candidate_id}'
            topic_key = title if raw_title.strip() else candidate_id
            if topic_key in seen_topics:
                continue
            seen_topics.add(topic_key)
            status = row.get("editor_judgment") or "PENDING"
            pending_items.append([
                title,
                f'{row.get("source_name", "미상")} · {row.get("first_seen", "")}~{row.get("last_seen", "")}',
                question_text,
                row.get("url", ""),
                status,
                row.get("evidence_values", ""),
                row.get("citizen_stake", ""),
                row.get("verification_axes", ""),
                candidate_id,
            ])
except (FileNotFoundError, UnicodeError):
    pending_items = []

source_counts = Counter(item[1].split(" · ", 1)[0] for item in pending_items)
source_performance = [[name, str(count), "판정 대기"] for name, count in sorted(source_counts.items())]
data = {
    "lastRun": manifest.get("generated_at_kst", "미확인"),
    "dataMode": "실제 산출물",
    "metrics": [["등록 소스", str(len(sources))], ["사람 판정 대기", str(len(pending_items))], ["접속·수집 상태", "확인 필요"], ["브리핑 연결", "가능" if manifest.get("publishable") else "보류"]],
    "sources": sources,
    "cards": cards,
    "pending": pending_items,
    "history": history,
    "sourcePerformance": source_performance,
    "queue": [["사람 판정", f'{summary.get("labeled", 0)}/{summary.get("generated", 0)}건 완료'], ["브리핑", "공개 가능" if manifest.get("publishable") else "검토 필요"], ["데이터 신선도", "정상" if not manifest.get("stale_at_generation") else "오래됨"]],
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
