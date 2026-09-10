"""상권 원본→코드연결표→대상 자치구 필터를 단계별로 계수한다."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAPPING = ROOT / "output" / "commercial_area_mapping" / "commercial_area_mapping.json"
TREND = ROOT / "output" / "commercial_area_trend" / "commercial_area_trend.json"
OUTPUT = ROOT / "output" / "nightlife_check"
TARGET = {"강북구", "도봉구", "노원구"}


def norm(value):
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_nightlife_join_trace.txt"
    mapping = json.loads(MAPPING.read_text(encoding="utf-8")).get("rows", [])
    sales = json.loads(TREND.read_text(encoding="utf-8")).get("datasets", {}).get("sales", {}).get("20261", [])
    lookup = {norm(row.get("TRDAR_CD")): str(row.get("SIGNGU_CD_NM")) for row in mapping}
    exact = [row for row in sales if str(row.get("SVC_INDUTY_CD_NM", "")).strip() == "호프-간이주점"]
    contains = [row for row in sales if "호프" in str(row.get("SVC_INDUTY_CD_NM", ""))]
    mapped = [row for row in exact if norm(row.get("TRDAR_CD")) in lookup]
    target = [row for row in mapped if lookup[norm(row.get("TRDAR_CD"))] in TARGET]
    names = Counter(str(row.get("SVC_INDUTY_CD_NM")) for row in contains)
    districts = Counter(lookup[norm(row.get("TRDAR_CD"))] for row in mapped)
    lines = [
        "# 서울 구조 레이더 — 북부 야간 상권 결합 단계 추적",
        "",
        f"20261 상권 단위 매출 전체: {len(sales)}행",
        f"업종명에 '호프' 포함: {len(contains)}행",
        f"업종명 정확히 '호프-간이주점': {len(exact)}행",
        f"코드 연결표 결합 성공: {len(mapped)}행",
        f"강북·도봉·노원 결합 성공: {len(target)}행",
        "",
        "'호프' 포함 업종명:",
        "- " + (", ".join(f"{name} {count}행" for name, count in names.items()) if names else "없음"),
        "",
        "결합 성공 행의 자치구 분포:",
        "- " + (", ".join(f"{district} {count}행" for district, count in sorted(districts.items())) if districts else "없음"),
        "",
        "대상 자치구 첫 행 예시:",
    ]
    for row in target[:3]:
        lines.append(f"- 코드 {row.get('TRDAR_CD')} / 상권 {row.get('TRDAR_CD_NM')} / 업종 {row.get('SVC_INDUTY_CD_NM')}")
    if not target:
        lines.append("- 없음")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
