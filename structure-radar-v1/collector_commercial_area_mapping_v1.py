"""서울시 상권영역 API에서 상권코드→자치구·행정동 연결표를 수집한다.

SEOUL_OPEN_API_KEY 환경변수를 사용하며, 키는 출력·저장하지 않는다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "commercial_area_mapping"
SERVICE = "TbgisTrdarRelm"
BASE = "http://openapi.seoul.go.kr:8088"
PAGE = 1000


def fetch(key: str, start: int, end: int):
    url = f"{BASE}/{key}/json/{SERVICE}/{start}/{end}/"
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    text_report = OUTPUT / "commercial_area_mapping_report.txt"
    key = os.environ.get("SEOUL_OPEN_API_KEY")
    if not key:
        text_report.write_text("# 상권 코드→자치구 연결표 수집\n\n환경변수 SEOUL_OPEN_API_KEY를 찾지 못했습니다.\n", encoding="utf-8")
        print(f"완료: {text_report}")
        return 0
    try:
        first = fetch(key, 1, PAGE)
        block = first.get(SERVICE, {})
        rows = list(block.get("row", []))
        total = int(block.get("list_total_count", len(rows)))
        for start in range(PAGE + 1, total + 1, PAGE):
            payload = fetch(key, start, min(start + PAGE - 1, total))
            rows.extend(payload.get(SERVICE, {}).get("row", []))
            time.sleep(0.12)
        now = datetime.now(timezone(timedelta(hours=9))).isoformat()
        raw_path = OUTPUT / "commercial_area_mapping.json"
        raw_path.write_text(json.dumps({"collected_at": now, "service": SERVICE, "rows": rows}, ensure_ascii=False), encoding="utf-8")
        districts = sorted({str(row.get("SIGNGU_CD_NM", "")) for row in rows if row.get("SIGNGU_CD_NM")})
        text_report.write_text(
            "# 서울 구조 레이더 — 상권 코드→자치구 연결표 수집\n\n"
            f"상태: ok\n수집 행: {len(rows)} / API 보고 행: {total}\n"
            f"자치구: {', '.join(districts)}\n"
            "\n다음 단계: 상권 단위 매출·점포 원본의 TRDAR_CD와 이 연결표를 결합합니다.\n"
            "이 보고서와 JSON에는 API 키를 기록하지 않습니다.\n",
            encoding="utf-8",
        )
    except Exception as exc:  # API 오류는 키 없이 문구만 출력
        text_report.write_text(f"# 상권 코드→자치구 연결표 수집\n\n상태: error\n오류: {exc}\n", encoding="utf-8")
    print(f"완료: {text_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
