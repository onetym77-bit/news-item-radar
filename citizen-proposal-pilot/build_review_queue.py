#!/usr/bin/env python3
"""Build a bounded public review queue from citizen-proposal shadow reviews."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
QUEUE = BASE / "output" / "editorial_review_queue.json"
DECISIONS = BASE / "output" / "editor_decisions.json"
FIELDS = {
    "id", "title", "source", "date", "url", "subject", "why_now",
    "citizen_question", "uncommon_question", "first_check", "decisive_test",
    "counterhypothesis", "scene_path", "anchor_quote", "claim_status",
    "editorial_risk", "independent_review", "status",
    "production_eligible", "briefing_output",
}
LIMITS = {
    "title": 100, "date": 30, "subject": 400, "why_now": 500,
    "citizen_question": 500, "uncommon_question": 500,
    "first_check": 500, "decisive_test": 500, "counterhypothesis": 500,
    "scene_path": 600, "anchor_quote": 240, "claim_status": 80,
    "editorial_risk": 500, "independent_review": 500, "status": 80,
}

def compact(value) -> str:
    return " ".join(str(value or "").split())

def redact(value) -> str:
    value = compact(value)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[이메일 제거]", value)
    value = re.sub(
        r"(?<!\d)(?:0\d{1,2}|\+82[- .]?(?:0?\d{1,2}))[- .)]?\d{3,4}[- .]?\d{4}(?!\d)",
        "[전화번호 제거]", value,
    )
    value = re.sub(r"(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)", "[식별번호 제거]", value)
    value = re.sub(r"\d+\s*동\s*\d+\s*호", "[상세주소 제거]", value)
    value = re.sub(r"[가-힣A-Za-z0-9]{1,24}(?:로|길)\s*\d+(?:-\d+)?", "[상세주소 제거]", value)
    value = re.sub(r"(?:제 이름은|이름[:：]?)\s*[가-힣]{2,4}", "[이름 제거]", value)
    return value

def bounded(name: str, value) -> str:
    return redact(value)[:LIMITS.get(name, 500)].strip()

def empty_queue() -> dict:
    return {
        "schema": 1,
        "mode": "CITIZEN_SIGNAL_SHADOW",
        "updated_at_utc": None,
        "items": [],
    }

def validate_queue(document: dict) -> dict:
    if not isinstance(document, dict) or document.get("schema") != 1:
        raise ValueError("지원하지 않는 시민 신호 검토 큐")
    if document.get("mode") != "CITIZEN_SIGNAL_SHADOW":
        raise ValueError("시민 신호 검토 큐 모드 불일치")
    items = document.get("items")
    if not isinstance(items, list) or len(items) > 50:
        raise ValueError("시민 신호 검토 큐 항목 오류")
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise ValueError("시민 신호 검토 카드 필드 오류")
        item_id = str(item.get("id", ""))
        if not re.fullmatch(r"[0-9a-f]{16}", item_id) or item_id in seen:
            raise ValueError("시민 신호 검토 카드 ID 오류")
        parsed = urlparse(item.get("url", ""))
        if parsed.scheme != "https" or parsed.hostname != "idea.seoul.go.kr":
            raise ValueError("시민 신호 공식 원문 주소 오류")
        if item.get("production_eligible") is not False or item.get("briefing_output") != "NONE":
            raise ValueError("시민 신호 그림자 경계 오류")
        if len(item.get("anchor_quote", "")) > 240:
            raise ValueError("시민 신호 근거 문장 길이 오류")
        seen.add(item_id)
    return document

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"읽을 수 없는 JSON: {path}") from exc

def public_item(item: dict) -> dict | None:
    if (
        item.get("family") != "시민제안"
        or item.get("production_eligible") is not False
        or item.get("briefing_output") != "NONE"
    ):
        return None
    item_id = compact(item.get("id"))
    if not re.fullmatch(r"[0-9a-f]{16}", item_id):
        return None
    parsed = urlparse(compact(item.get("url")))
    if parsed.scheme != "https" or parsed.hostname != "idea.seoul.go.kr":
        return None
    anchor = bounded("anchor_quote", item.get("anchor_quote"))
    if len(anchor) < 15:
        return None
    return {
        "id": item_id,
        "title": bounded("title", item.get("title")) or "시민 경험 신호",
        "source": "상상대로 서울 시민제안",
        "date": bounded("date", item.get("date")) or "게시일 확인 필요",
        "url": compact(item.get("url")),
        "subject": bounded("subject", item.get("subject")),
        "why_now": bounded("why_now", item.get("why_now")),
        "citizen_question": bounded("citizen_question", item.get("citizen_question")),
        "uncommon_question": bounded("uncommon_question", item.get("uncommon_question")),
        "first_check": bounded("first_check", item.get("first_check")),
        "decisive_test": bounded("decisive_test", item.get("decisive_test")),
        "counterhypothesis": bounded("counterhypothesis", item.get("counterhypothesis")),
        "scene_path": bounded("scene_path", item.get("scene_path")),
        "anchor_quote": anchor,
        "claim_status": bounded("claim_status", item.get("claim_status")) or "시민 진술·미검증",
        "editorial_risk": bounded("editorial_risk", item.get("editorial_risk")),
        "independent_review": bounded("independent_review", item.get("independent_review")),
        "status": "검증 전용·최종 후보 아님",
        "production_eligible": False,
        "briefing_output": "NONE",
    }

def build_queue(shadow: dict, queue: dict, decisions: list[dict]) -> dict:
    validate_queue(queue)
    if not isinstance(decisions, list):
        raise ValueError("지원하지 않는 시민 신호 판정 이력")
    decided = {
        str(row.get("id")) for row in decisions
        if row.get("decision") in {"PROMISING", "HOLD", "DISCARD"}
    }
    existing = [item for item in queue["items"] if item["id"] not in decided]
    by_id = {item["id"]: item for item in existing}
    for raw in shadow.get("shadow_reviews", []):
        item = public_item(raw)
        if item and item["id"] not in decided:
            by_id[item["id"]] = item
    items = list(by_id.values())[-50:]
    if items == queue["items"]:
        return queue
    return validate_queue({
        "schema": 1,
        "mode": "CITIZEN_SIGNAL_SHADOW",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "items": items,
    })

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--queue", type=Path, default=QUEUE)
    parser.add_argument("--decisions", type=Path, default=DECISIONS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    shadow = load_json(args.input, {})
    queue = load_json(args.queue, empty_queue())
    decisions = load_json(args.decisions, [])
    result = build_queue(shadow, queue, decisions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pending": len(result["items"])}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
