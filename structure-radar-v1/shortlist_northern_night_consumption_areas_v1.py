"""북부 3구의 21~24시 식음료 소비 변화로 현장 상권을 선별한다.

호프·간이주점만 사용하지 않는다. CS100 계열(식음료 서비스업)을 상권별로 합산하고,
실제 21~24시 결제 비중과 변화로 ‘밤 소비’를 정의한다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAPPING = ROOT / "output" / "commercial_area_mapping" / "commercial_area_mapping.json"
TREND = ROOT / "output" / "commercial_area_trend" / "commercial_area_trend.json"
OUTPUT = ROOT / "output" / "nightlife_check"
DISTRICTS = ("강북구", "도봉구", "노원구")
YEARS = (2024, 2026)


def norm(value):
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def num(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def pct(now, old):
    return None if not old else (now / old - 1) * 100


def is_food_service(row):
    # Seoul commercial-analysis service uses CS100*** for restaurant/food-service industries.
    return str(row.get("SVC_INDUTY_CD", "")).startswith("CS100")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_night_consumption_area_shortlist.txt"
    if not MAPPING.exists() or not TREND.exists():
        report.write_text("# 북부 생활권 야간 식음료 소비 현장 후보\n\n연결표 또는 상권 경로 원본이 없습니다.\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    mapping = json.loads(MAPPING.read_text(encoding="utf-8")).get("rows", [])
    trend = json.loads(TREND.read_text(encoding="utf-8")).get("datasets", {})
    district_of = {norm(row.get("TRDAR_CD")): str(row.get("SIGNGU_CD_NM")) for row in mapping}
    name_of = {norm(row.get("TRDAR_CD")): str(row.get("TRDAR_CD_NM")) for row in mapping}
    values = defaultdict(lambda: {"sales": defaultdict(float), "tx": defaultdict(float), "night_tx": defaultdict(float), "stores": defaultdict(float), "industries": defaultdict(set)})
    joined = defaultdict(int)
    for year in YEARS:
        for row in trend.get("sales", {}).get(str(year), []):
            code = norm(row.get("TRDAR_CD")); district = district_of.get(code)
            if district in DISTRICTS and is_food_service(row):
                key = (district, code, name_of.get(code, str(row.get("TRDAR_CD_NM", code))))
                item = values[key]
                item["sales"][year] += num(row.get("THSMON_SELNG_AMT"))
                item["tx"][year] += num(row.get("THSMON_SELNG_CO"))
                item["night_tx"][year] += num(row.get("TMZON_21_24_SELNG_CO"))
                item["industries"][year].add(str(row.get("SVC_INDUTY_CD_NM")))
                joined[(year, district)] += 1
        for row in trend.get("stores", {}).get(str(year), []):
            code = norm(row.get("TRDAR_CD")); district = district_of.get(code)
            if district in DISTRICTS and is_food_service(row):
                key = (district, code, name_of.get(code, str(row.get("TRDAR_CD_NM", code))))
                values[key]["stores"][year] += num(row.get("STOR_CO"))
    candidates, all_rows = [], []
    for (district, code, area), item in values.items():
        if not all(year in item["tx"] and year in item["night_tx"] and year in item["stores"] for year in YEARS):
            continue
        night_share = item["night_tx"][2024] / item["tx"][2024] if item["tx"][2024] else 0
        total_tx_ch = pct(item["tx"][2026], item["tx"][2024])
        night_tx_ch = pct(item["night_tx"][2026], item["night_tx"][2024])
        sales_ch = pct(item["sales"][2026], item["sales"][2024])
        store_ch = pct(item["stores"][2026], item["stores"][2024])
        row = (district, code, area, item, night_share, total_tx_ch, night_tx_ch, sales_ch, store_ch)
        all_rows.append(row)
        # Broad-food baseline + empirically night-active + marked nighttime decline.
        if item["tx"][2024] >= 1000 and item["night_tx"][2024] >= 250 and night_share >= 0.18 and night_tx_ch <= -15:
            candidates.append(row)
    candidates.sort(key=lambda row: row[6])
    selected = []
    for district in DISTRICTS:
        selected.extend([row for row in candidates if row[0] == district][:2])
    lines = [
        "# 서울 구조 레이더 — 북부 생활권 야간 식음료 소비 현장 후보 v1",
        "",
        "가설: 강북·도봉·노원에서 21~24시 식음료 소비가 약해지고 있다.",
        "비교: 같은 상권 경계의 2024년 1분기 대 2026년 1분기",
        "업종 범위: 서울 상권분석서비스의 CS100 식음료 서비스업 전체를 상권별로 합산",
        "",
        "선별 기준",
        "- 2024년 식음료 전체 결제 1,000건 이상, 21~24시 결제 250건 이상",
        "- 2024년 21~24시 결제 비중 18% 이상",
        "- 2024→2026 21~24시 결제 -15% 이하",
        "- 자치구별 상위 2곳만 표시. 이는 현장 관찰 후보이지 기사 결론이 아닙니다.",
        "",
        "결합 행 수(식음료 업종 행):",
        "- " + ", ".join(f"{district} 2024년 {joined[(2024, district)]}행 / 2026년 {joined[(2026, district)]}행" for district in DISTRICTS),
        f"조건 충족 상권: {len(candidates)}곳 / 현장 우선 후보: {len(selected)}곳",
        "",
    ]
    for district, code, area, item, night_share, total_tx_ch, night_tx_ch, sales_ch, store_ch in selected:
        industries = ", ".join(sorted(item["industries"][2024]))
        lines += [
            f"## {district} · {area}",
            f"- 상권코드: {code}",
            f"- 21~24시 결제 비중(2024): {night_share * 100:.1f}%",
            f"- 2024→2026: 21~24시 결제 {night_tx_ch:+.1f}%, 전체 결제 {total_tx_ch:+.1f}%, 매출 {sales_ch:+.1f}%, 식음료 점포 {store_ch:+.1f}%",
            "- 포함 업종: " + industries,
            "- 현장 검증: 목·금요일 21시·23시에 영업 점포·보행량·대기 여부·빈 점포를 같은 방식으로 기록",
            "- 섭외 A: 야간 영업 식당·주점 업주 또는 배달·택시·대리운전 종사자 1명",
            "- 섭외 실패 대안: 현장 표본과 지도 영업시간·공개 점포 수·21~24시 결제 지표를 대조",
            "",
        ]
    if not selected:
        lines.append("- 없음. 현재 자료에서는 상권 단위로 야간 식음료 소비 감소가 집중된 장소를 특정하지 않습니다.")
    lines += [
        "다음 편집 판정",
        "- 후보가 세 자치구에 걸쳐 반복되면 ‘북부 생활권의 밤 소비 변화’ 가설을 S3 취재 제안으로 올립니다.",
        "- 한 자치구에만 집중되면 북부 전체 기사 대신 해당 생활권의 별도 현상으로 재검토합니다.",
        "- 야간 결제 감소는 영업시간·인구·경쟁·소비행태 중 무엇의 결과인지는 말해주지 않습니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
