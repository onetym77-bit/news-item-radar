"""Collect commercial-area (not district) data for a matched year-on-year pair.

Uses the user-approved dedicated key with Seoul's documented HTTP endpoint.
Only two comparable quarters are fetched to keep the first spatial baseline
focused and bounded.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
PAGE_SIZE, MAX_ROWS = 1000, 200000
PERIODS = ("20261", "20251")
SOURCES = {"stores_by_area": "VwsmTrdarStorQq", "sales_by_area": "VwsmTrdarSelngQq"}


def fetch(key: str, service: str, start: int, end: int, period: str) -> dict:
    url = f"http://openapi.seoul.go.kr:8088/{key}/json/{service}/{start}/{end}/{period}/"
    time.sleep(0.12)
    with urlopen(url, timeout=45) as response:  # nosec B310: official HTTP-only endpoint, user-approved dedicated key
        return json.loads(response.read().decode("utf-8"))


def unwrap(payload: dict, service: str) -> dict:
    return payload.get(service, {"RESULT": payload.get("RESULT", {"CODE": "UNKNOWN", "MESSAGE": json.dumps(payload, ensure_ascii=False)})})


def collect_period(key: str, service: str, period: str) -> dict:
    try:
        first = unwrap(fetch(key, service, 1, PAGE_SIZE, period), service)
        result = first.get("RESULT", {})
        if result.get("CODE") not in (None, "INFO-000"):
            return {"period": period, "status": "error", "message": result.get("MESSAGE", "API error"), "rows": []}
        total, rows = int(first.get("list_total_count", 0)), list(first.get("row", []))
        capped = total > MAX_ROWS
        for start in range(PAGE_SIZE + 1, min(total, MAX_ROWS) + 1, PAGE_SIZE):
            page = unwrap(fetch(key, service, start, min(start + PAGE_SIZE - 1, total), period), service)
            if page.get("RESULT", {}).get("CODE") not in (None, "INFO-000"):
                return {"period": period, "status": "partial_error", "message": page.get("RESULT", {}).get("MESSAGE", "API error"), "rows": rows}
            rows.extend(page.get("row", []))
        return {"period": period, "status": "ok", "reported_total_rows": total, "collected_rows": len(rows), "capped": capped, "rows": rows}
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
        return {"period": period, "status": "error", "message": str(error), "rows": []}


def main() -> int:
    key = os.environ.get("SEOUL_OPEN_API_KEY")
    if not key:
        print("SEOUL_OPEN_API_KEY 환경변수가 없습니다.")
        return 2
    now = datetime.now(KST)
    sources = []
    for label, service in SOURCES.items():
        periods = [collect_period(key, service, period) for period in PERIODS]
        sources.append({"label": label, "service": service, "periods": periods})
    stamp = now.strftime("%Y-%m-%d-%H%M")
    raw_dir, report_dir = ROOT / "output" / "area" / "raw", ROOT / "output" / "area" / "report"
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{stamp}.json"
    raw_path.write_text(json.dumps({"collected_at": now.isoformat(), "periods": PERIODS, "sources": sources}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["서울 구조 레이더 — 상권 단위 기준선 수집", "=" * 40, f"수집 시각: {now.isoformat()}", f"비교 분기: {PERIODS[0]} 대 {PERIODS[1]}", ""]
    for source in sources:
        lines.append(f"[{source['label']}]")
        for item in source["periods"]:
            lines.append(f"- {item['period']}: {item['status']} / API 행 {item.get('reported_total_rows', 0)}, 수집 행 {item.get('collected_rows', 0)}")
            if item.get("capped"):
                lines.append("  주의: 안전 상한으로 일부 행만 수집됨")
            if item.get("message"):
                lines.append("  오류: " + item["message"])
        lines.append("")
    lines.extend(["이 단계는 기사 후보를 만들지 않습니다.", "상권 단위 비교가 완료된 뒤, 대형 점포 효과·업종 분류·공간 집중을 분리합니다."])
    report_path = report_dir / f"{stamp}.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
