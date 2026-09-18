import json
from datetime import datetime, timezone
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

sources = []
for source in registry.get("sources", []):
    sources.append([
        source.get("source_name", source.get("source_id", "미상")),
        source.get("maturity", "UNKNOWN"),
        source.get("candidate_role", "미분류"),
    ])

cards = []
for card in cards_doc.get("review_cards", [])[:8]:
    cards.append([
        card.get("context_subject") or card.get("fact", "")[:80],
        f'{card.get("source_name", "미상")} · {card.get("transition_state", "상태 미상")}',
        card.get("question") or card.get("fact", ""),
    ])

pending = summary.get("generated", 0) - summary.get("labeled", 0)
data = {
    "lastRun": manifest.get("generated_at_kst", "미확인"),
    "dataMode": "실제 산출물",
    "metrics": [
        ["등록 소스", str(len(sources))],
        ["사람 판정 대기", str(max(0, pending))],
        ["접속·수집 상태", "확인 필요"],
        ["브리핑 연결", "가능" if manifest.get("publishable") else "보류"],
    ],
    "sources": sources,
    "cards": cards,
    "queue": [
        ["사람 판정", f'{summary.get("labeled", 0)}/{summary.get("generated", 0)}건 완료'],
        ["브리핑", "공개 가능" if manifest.get("publishable") else "검토 필요"],
        ["데이터 신선도", "정상" if not manifest.get("stale_at_generation") else "오래됨"],
    ],
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
