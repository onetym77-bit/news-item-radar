"""상권코드 연결표와 4개 연도 원본으로 북부 3구 야간 현장 후보를 선별한다."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAPPING = ROOT / "output" / "commercial_area_mapping" / "commercial_area_mapping.json"
TREND = ROOT / "output" / "commercial_area_trend" / "commercial_area_trend.json"
OUTPUT = ROOT / "output" / "nightlife_check"
DISTRICTS = ("강북구", "도봉구", "노원구")
INDUSTRY = "호프-간이주점"
YEARS = (2023, 2024, 2025, 2026)


def num(value):
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def change(now, old):
    return None if not old else (now / old - 1) * 100


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_nightlife_area_shortlist_v2.txt"
    if not MAPPING.exists() or not TREND.exists():
        report.write_text("# 북부 생활권 야간 상권 현장 후보 v2\n\n연결표 또는 장기 원본이 없습니다. 수집 스크립트를 먼저 실행해 주세요.\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    mapping_rows = json.loads(MAPPING.read_text(encoding="utf-8")).get("rows", [])
    trend = json.loads(TREND.read_text(encoding="utf-8")).get("datasets", {})
    code_to_district = {str(row.get("TRDAR_CD")): str(row.get("SIGNGU_CD_NM")) for row in mapping_rows}
    code_to_name = {str(row.get("TRDAR_CD")): str(row.get("TRDAR_CD_NM")) for row in mapping_rows}
    values = defaultdict(lambda: {"sales": defaultdict(float), "transactions": defaultdict(float), "stores": defaultdict(float), "night_sales": defaultdict(float), "night_transactions": defaultdict(float)})
    for year in YEARS:
        for row in trend.get("sales", {}).get(str(year), []):
            code = str(row.get("TRDAR_CD"))
            if code_to_district.get(code) in DISTRICTS and row.get("SVC_INDUTY_CD_NM") == INDUSTRY:
                item = values[(code_to_district[code], code, code_to_name.get(code, row.get("TRDAR_CD_NM", code)))]
                item["sales"][year] += num(row.get("THSMON_SELNG_AMT"))
                item["transactions"][year] += num(row.get("THSMON_SELNG_CO"))
                item["night_sales"][year] += num(row.get("TMZON_21_24_SELNG_AMT"))
                item["night_transactions"][year] += num(row.get("TMZON_21_24_SELNG_CO"))
        for row in trend.get("stores", {}).get(str(year), []):
            code = str(row.get("TRDAR_CD"))
            if code_to_district.get(code) in DISTRICTS and row.get("SVC_INDUTY_CD_NM") == INDUSTRY:
                item = values[(code_to_district[code], code, code_to_name.get(code, row.get("TRDAR_CD_NM", code)))]
                item["stores"][year] += num(row.get("STOR_CO"))
    candidates = []
    for (district, code, area), item in values.items():
        sales_ch = change(item["sales"][2026], item["sales"][2023])
        tx_ch = change(item["transactions"][2026], item["transactions"][2023])
        store_ch = change(item["stores"][2026], item["stores"][2023])
        night_tx_ch = change(item["night_transactions"][2026], item["night_transactions"][2023])
        if None in (sales_ch, tx_ch, store_ch, night_tx_ch):
            continue
        # A sizeable base and a decline both in overall and late-evening consumption are required.
        if item["stores"][2023] >= 5 and item["transactions"][2023] >= 300 and sales_ch <= -10 and tx_ch <= -10 and store_ch <= -5 and night_tx_ch <= -10:
            score = abs(sales_ch) + abs(tx_ch) + abs(store_ch) + abs(night_tx_ch)
            candidates.append((score, district, code, area, item, sales_ch, tx_ch, store_ch, night_tx_ch))
    candidates.sort(reverse=True)
    selected = []
    for district in DISTRICTS:
        selected.extend([row for row in candidates if row[1] == district][:2])
    lines = [
        "# 서울 구조 레이더 — 북부 생활권 야간 상권 현장 후보 v2",
        "",
        "가설: 강북·도봉·노원에서 심야 생활인구와 호프-간이주점의 밤 소비가 함께 줄고 있다.",
        "비교: 상권 단위 2023·2024·2025·2026년 1분기 / 기준 업종: 호프-간이주점",
        "",
        "선별 기준",
        "- 2023년 점포 5개 이상, 결제 300건 이상",
        "- 2023→2026 매출 -10%, 전체 결제 -10%, 점포 -5%, 21~24시 결제 -10%를 모두 충족",
        "- 각 자치구 상위 2곳만 표시하며, 이 목록은 취재 장소 후보이지 기사 결론이 아닙니다.",
        "",
        f"조건 충족 상권: {len(candidates)}곳 / 현장 우선 후보: {len(selected)}곳",
        "",
    ]
    for _, district, code, area, item, sales_ch, tx_ch, store_ch, night_tx_ch in selected:
        lines += [
            f"## {district} · {area}",
            f"- 상권코드: {code}",
            f"- 2023→2026: 매출 {sales_ch:+.1f}%, 전체 결제 {tx_ch:+.1f}%, 점포 {store_ch:+.1f}%, 21~24시 결제 {night_tx_ch:+.1f}%",
            "- 연도별: " + " | ".join(
                f"{year}년 매출 {item['sales'][year]:,.0f}, 전체결제 {item['transactions'][year]:,.0f}, 21~24시결제 {item['night_transactions'][year]:,.0f}, 점포 {item['stores'][year]:,.0f}" for year in YEARS
            ),
            "- 현장 검증: 목·금요일 같은 시간대(21시·23시)로 영업 점포·보행량·빈 점포를 기록",
            "- 섭외 A: 3년 이상 영업한 업주 또는 야간 배달·택시·대리운전 종사자 1명",
            "- 섭외 실패 대안: 현장 표본과 지도 영업정보를 상권 데이터·점포 수와 대조",
            "",
        ]
    if not selected:
        lines.append("- 없음. 자치구 평균은 강하지만, 현장 상권까지 좁힐 만큼 일관된 21~24시 감소는 확인되지 않았습니다.")
    lines += [
        "다음 편집 단계",
        "- 우선 후보의 인접 역 심야 승하차·막차 이후 이동을 확인해 상권 변화와 사람 이동이 맞는지 본다.",
        "- 세 자치구에서 각 1곳 이상이 현장에서도 확인될 때만 S3 취재 제안으로 올린다.",
        "- 원인은 인터뷰·현장·추가 이동 데이터가 있기 전까지 확정하지 않는다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
