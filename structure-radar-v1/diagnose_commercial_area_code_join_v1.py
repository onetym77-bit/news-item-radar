"""상권 단위 매출 원본과 상권영역 연결표의 코드 결합 가능 여부를 진단한다."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAPPING = ROOT / "output" / "commercial_area_mapping" / "commercial_area_mapping.json"
TREND = ROOT / "output" / "commercial_area_trend" / "commercial_area_trend.json"
OUTPUT = ROOT / "output" / "nightlife_check"


def norm(value):
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "commercial_area_code_join_diagnostic.txt"
    if not MAPPING.exists() or not TREND.exists():
        report.write_text("# 상권 코드 결합 진단\n\n필수 원본이 없습니다.\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    mapping_rows = json.loads(MAPPING.read_text(encoding="utf-8")).get("rows", [])
    trend = json.loads(TREND.read_text(encoding="utf-8")).get("datasets", {})
    mapped = {norm(row.get("TRDAR_CD")): row for row in mapping_rows}
    sales_rows = trend.get("sales", {}).get("20261", [])
    bar_rows = [row for row in sales_rows if row.get("SVC_INDUTY_CD_NM") == "호프-간이주점"]
    bar_codes = {norm(row.get("TRDAR_CD")) for row in bar_rows}
    overlap = bar_codes & set(mapped)
    district_count = Counter(str(mapped[code].get("SIGNGU_CD_NM")) for code in overlap)
    unmatched = [row for row in bar_rows if norm(row.get("TRDAR_CD")) not in mapped]
    lines = [
        "# 서울 구조 레이더 — 상권 코드 결합 진단",
        "",
        f"상권영역 연결표 코드: {len(mapped)}개",
        f"20261 호프-간이주점 상권 코드: {len(bar_codes)}개",
        f"코드 일치: {len(overlap)}개",
        "",
        "일치 코드 자치구별 건수:",
        "- " + (", ".join(f"{district} {count}개" for district, count in sorted(district_count.items())) if district_count else "없음"),
        "",
        "결합되지 않은 호프-간이주점 상권 예시(최대 10):",
    ]
    for row in unmatched[:10]:
        lines.append(f"- 코드 {row.get('TRDAR_CD')} / 명칭 {row.get('TRDAR_CD_NM')}")
    if not unmatched:
        lines.append("- 없음")
    lines += [
        "", "판정",
        "- 일치 코드가 매우 적으면 상권영역 연결표와 추정매출·점포 원본의 상권 경계 시점 또는 코드 체계가 다릅니다.",
        "- 이 경우 코드 결합을 억지로 보정하지 않고, 같은 기준시점의 공식 영역 파일 또는 상권명·좌표 기반 공간 결합을 사용해야 합니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
