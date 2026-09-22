#!/usr/bin/env python3
"""L2 body-access sample for all 25 Seoul district councils; no editorial output."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path

from collect_pilot import KST, run

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "output" / "body-l2"
SCHEMA = 1


def summarize(source, result):
    """Preserve bounded metadata only; do not archive speech or raw HTML."""
    selected = result.get("selected") or []
    row = selected[0] if selected else {}
    body_ok = row.get("body_ok") is True
    metadata = row.get("metadata_check") or "UNVERIFIED"
    if not result.get("listing_ok"):
        status = "UNKNOWN_COLLECTION"
    elif not selected:
        status = "UNKNOWN_LIST_WINDOW"
    elif row.get("diagnosis") == "FUTURE_MEETING":
        status = "FUTURE_MEETING"
    elif not body_ok:
        status = "BODY_UNAVAILABLE"
    elif metadata == "CONFLICT":
        status = "METADATA_CONFLICT"
    elif row.get("provisional"):
        status = "PROVISIONAL_BODY"
    elif metadata != "MATCH":
        status = "METADATA_UNVERIFIED"
    else:
        status = "BODY_METADATA_MATCH"
    return {
        "source_id": source["id"], "source_name": source["name"],
        "status": status, "diagnosis": row.get("diagnosis") or result.get("diagnosis") or "",
        "document_url": row.get("url") or "", "meeting_date": row.get("meeting_date") or "",
        "public_release_date": None, "provisional": bool(row.get("provisional")),
        "body_observed": body_ok, "body_characters": row.get("body_characters") or 0,
        "speech_turns": row.get("speech_turns") or 0,
        "body_sha256": row.get("body_sha256") or "",
        "metadata_check": metadata, "date_crosschecked": bool(row.get("date_crosschecked")),
        "identity_conflict": bool(row.get("identity_conflict")),
        "review_window_count": len(row.get("review_windows") or []),
        "request_count": len(result.get("requests") or []),
    }


def safe_probe(source, as_of):
    try:
        return summarize(source, run(source, as_of, count=1))
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        return {
            "source_id": source["id"], "source_name": source["name"],
            "status": "UNKNOWN_COLLECTION", "diagnosis": type(exc).__name__,
            "document_url": "", "meeting_date": "", "public_release_date": None,
            "provisional": False, "body_observed": False, "body_characters": 0,
            "speech_turns": 0, "body_sha256": "", "metadata_check": "UNVERIFIED",
            "date_crosschecked": False, "identity_conflict": False,
            "review_window_count": 0, "request_count": 0,
        }


def collect(sources, as_of):
    if len(sources) != 25 or len({source["id"] for source in sources}) != 25:
        raise ValueError("Expected exactly 25 distinct district councils")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda source: safe_probe(source, as_of), sources))
    counts = dict(sorted(Counter(row["status"] for row in results).items()))
    return {
        "schema": SCHEMA, "sampled_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "as_of": as_of.isoformat(),
        "coverage": "ONE_RECENT_LIST_ITEM_PER_COUNCIL",
        "source_count": 25, "status_counts": counts, "results": results,
        "question_output": "NONE", "briefing_output": "NONE",
        "automatic_ledger_write": False,
        "note": "회의일은 공개일이 아니다. 본문 확인은 의미 해석이나 후보 승인이 아니다.",
    }


def render(payload):
    lines = [
        "# 서울 25개 자치구의회 본문 L2 동일 표본", "",
        f"수집 시각: {payload['sampled_at_kst']}",
        "각 의회의 공식 최근목록 최상단 1건만 읽었다. 전체 회의록이나 발언을 대표하지 않는다.",
        "회의일은 공개일이 아니다. 접근 실패·본문 실패는 아이템 0건이 아니다.",
        "본문 원문·발언 발췌·개인정보는 저장하지 않는다. 질문·브리핑·장부에는 연결하지 않는다.",
        "", "| 의회 | 본문·식별정보 | 회의일 | 발언 턴 | 상태 |",
        "|---|---|---|---:|---|",
    ]
    for row in payload["results"]:
        doc = f"[원문]({row['document_url']})" if row["document_url"] else "-"
        lines.append(f"| {row['source_name']} | {doc} | {row['meeting_date'] or '-'} | "
                     f"{row['speech_turns']} | {row['status']} |")
    lines.extend(["", "## 상태별 건수", ""])
    for status, count in payload["status_counts"].items():
        lines.append(f"- {status}: {count}")
    lines.extend(["", "본문·식별정보가 맞는 문서만 다음 L3 의미 해석의 고정 표본으로 사용할 수 있다.",
                  "임시본, 날짜 미대조, 목록 단절 및 접근 실패는 별도로 재확인한다."])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=BASE / "sources_25.json")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    sources = json.loads(args.sources.read_text(encoding="utf-8"))
    payload = collect(sources, datetime.now(KST).date())
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "sample_latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output / "SUMMARY.md").write_text(render(payload), encoding="utf-8")
    print(json.dumps({"source_count": 25, "status_counts": payload["status_counts"],
                      "question_output": "NONE"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
