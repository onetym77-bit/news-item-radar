"""Create immutable baseline snapshots from Seoul commercial-area APIs.

Required environment variable: SEOUL_OPEN_API_KEY
This collector does not generate story ideas. It only collects point-in-time
commercial structure data, reports coverage, and writes a readable .txt status.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
PAGE_SIZE = 1000
MAX_ROWS_PER_SOURCE = 20000
SOURCES = {
    "stores_by_district": "VwsmSignguStorW",
    "sales_by_district": "VwsmSignguSelngW",
}


def fetch_page(key: str, service: str, start: int, end: int) -> dict:
    # HTTPS only: the key must not be transmitted over an unencrypted connection.
    url = f"https://openapi.seoul.go.kr:8088/{key}/json/{service}/{start}/{end}/"
    context = ssl.create_default_context()
    with urlopen(url, timeout=45, context=context) as response:  # nosec B310: fixed official host
        return json.loads(response.read().decode("utf-8"))


def service_payload(payload: dict, service: str) -> dict:
    if service in payload:
        return payload[service]
    # Seoul OpenAPI error responses are not always wrapped under the service name.
    return {"RESULT": payload.get("RESULT", {"CODE": "UNKNOWN", "MESSAGE": json.dumps(payload, ensure_ascii=False)})}


def collect_source(key: str, label: str, service: str) -> dict:
    try:
        first = service_payload(fetch_page(key, service, 1, PAGE_SIZE), service)
        result = first.get("RESULT", {})
        if result.get("CODE") not in (None, "INFO-000"):
            return {"label": label, "service": service, "status": "error", "message": result.get("MESSAGE", "API error")}
        total = int(first.get("list_total_count", 0))
        rows = list(first.get("row", []))
        capped = total > MAX_ROWS_PER_SOURCE
        stop = min(total, MAX_ROWS_PER_SOURCE)
        for start in range(PAGE_SIZE + 1, stop + 1, PAGE_SIZE):
            page = service_payload(fetch_page(key, service, start, min(start + PAGE_SIZE - 1, stop)), service)
            page_result = page.get("RESULT", {})
            if page_result.get("CODE") not in (None, "INFO-000"):
                return {"label": label, "service": service, "status": "partial_error", "message": page_result.get("MESSAGE", "API error"), "rows": rows}
            rows.extend(page.get("row", []))
        return {"label": label, "service": service, "status": "ok", "reported_total_rows": total,
                "collected_rows": len(rows), "capped": capped, "rows": rows}
    except (HTTPError, URLError, TimeoutError, ValueError, OSError) as error:
        return {"label": label, "service": service, "status": "error", "message": str(error)}


def source_summary(source: dict) -> list[str]:
    lines = [f"[{source['label']}] {source['status']}"]
    if source["status"] != "ok":
        lines.append(f"- 오류: {source.get('message', '상세 없음')}")
        return lines
    rows = source.get("rows", [])
    lines.append(f"- API 보고 행: {source['reported_total_rows']}, 수집 행: {source['collected_rows']}")
    if source.get("capped"):
        lines.append("- 주의: 안전 상한을 넘어 일부 행만 수집됨. 분석 전 전체 수집 설정이 필요함.")
    if not rows:
        return lines
    fields = sorted(rows[0].keys())
    period_fields = [field for field in fields if "YY" in field or "QU" in field or "STDR" in field]
    lines.append("- 확인된 기준기간 필드: " + (", ".join(period_fields) if period_fields else "자동 확인 불가"))
    lines.append("- 첫 행 필드: " + ", ".join(fields[:16]))
    return lines


def main() -> int:
    key = os.environ.get("SEOUL_OPEN_API_KEY")
    if not key:
        print("SEOUL_OPEN_API_KEY 환경변수가 없습니다.")
        return 2
    now = datetime.now(KST)
    sources = [collect_source(key, label, service) for label, service in SOURCES.items()]
    stamp = now.strftime("%Y-%m-%d-%H%M")
    raw_dir = ROOT / "output" / "commercial" / "raw"
    report_dir = ROOT / "output" / "commercial" / "report"
    raw_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{stamp}.json"
    raw_path.write_text(json.dumps({"collected_at": now.isoformat(), "sources": sources}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["서울 구조 레이더 — 상권 기준선 수집", "=" * 38, f"수집 시각: {now.isoformat()}", "목적: 기사 후보 생성이 아닌 기준선 축적", ""]
    for source in sources:
        lines.extend(source_summary(source))
        lines.append("")
    lines.extend(["다음 단계", "- 최소 두 개 분기의 동일 지표를 확보한 뒤 변화율을 계산합니다.", "- 이 파일에는 API 키가 기록되지 않습니다."])
    report_path = report_dir / f"{stamp}.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
