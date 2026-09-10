"""상권 단위 2023~2026년 1분기 점포·매출 원본을 수집한다."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "commercial_area_trend"
BASE = "http://openapi.seoul.go.kr:8088"
SERVICES = {"stores": "VwsmTrdarStorQq", "sales": "VwsmTrdarSelngQq"}
PERIODS = (20231, 20241, 20251, 20261)
PAGE = 1000


def get_all(key, service, period):
    def call(start, end):
        url = f"{BASE}/{key}/json/{service}/{start}/{end}/{period}"
        with urllib.request.urlopen(url, timeout=90) as response:
            return json.load(response)
    first = call(1, PAGE).get(service, {})
    rows = list(first.get("row", []))
    total = int(first.get("list_total_count", len(rows)))
    for start in range(PAGE + 1, total + 1, PAGE):
        rows.extend(call(start, min(start + PAGE - 1, total)).get(service, {}).get("row", []))
        time.sleep(0.12)
    return total, rows


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "commercial_area_trend_report.txt"
    key = os.environ.get("SEOUL_OPEN_API_KEY")
    if not key:
        report.write_text("# 상권 단위 장기 경로 수집\n\n환경변수 SEOUL_OPEN_API_KEY를 찾지 못했습니다.\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    payload = {"collected_at": datetime.now(timezone(timedelta(hours=9))).isoformat(), "periods": list(PERIODS), "datasets": {}}
    lines = ["# 서울 구조 레이더 — 상권 단위 장기 경로 수집", "", "비교 분기: 20231, 20241, 20251, 20261", ""]
    try:
        for label, service in SERVICES.items():
            payload["datasets"][label] = {}
            lines.append(f"[{label}]")
            for period in PERIODS:
                total, rows = get_all(key, service, period)
                payload["datasets"][label][str(period)] = rows
                lines.append(f"- {period}: API 행 {total}, 수집 행 {len(rows)}")
        (OUTPUT / "commercial_area_trend.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        lines += ["", "다음 단계: 상권 코드→자치구 연결표와 결합해 북부 3구의 야간 상권 후보를 선별합니다.", "API 키는 출력·저장하지 않습니다."]
    except Exception as exc:
        lines += ["", f"오류: {exc}"]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
