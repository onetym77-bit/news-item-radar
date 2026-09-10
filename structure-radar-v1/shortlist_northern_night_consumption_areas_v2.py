"""v2: 북부 3구 상권별 21~24시 식음료 결제 변화만으로 현장 후보를 찾는다.

CS100 식음료 서비스업을 합산한다. 업종명이나 점포 수를 야간성의 대리값으로 쓰지 않는다.
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
    try: return float(str(value).replace(",", ""))
    except (TypeError, ValueError): return 0.0

def pct(now, old): return None if not old else (now / old - 1) * 100

def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_night_consumption_area_shortlist_v2.txt"
    mapping = json.loads(MAPPING.read_text(encoding="utf-8")).get("rows", [])
    sales_by_year = json.loads(TREND.read_text(encoding="utf-8")).get("datasets", {}).get("sales", {})
    lookup = {norm(row.get("TRDAR_CD")): (str(row.get("SIGNGU_CD_NM")), str(row.get("TRDAR_CD_NM"))) for row in mapping}
    data = defaultdict(lambda: {"total": defaultdict(float), "night": defaultdict(float), "names": defaultdict(set)})
    joined = defaultdict(int)
    for year in YEARS:
        for row in sales_by_year.get(str(year), []):
            code = norm(row.get("TRDAR_CD")); meta = lookup.get(code)
            if not meta or meta[0] not in DISTRICTS or not str(row.get("SVC_INDUTY_CD", "")).startswith("CS100"):
                continue
            key = (meta[0], code, meta[1]); item = data[key]
            item["total"][year] += num(row.get("THSMON_SELNG_CO"))
            item["night"][year] += num(row.get("TMZON_21_24_SELNG_CO"))
            item["names"][year].add(str(row.get("SVC_INDUTY_CD_NM")))
            joined[(year, meta[0])] += 1
    rows, candidates = [], []
    for (district, code, area), item in data.items():
        if 2024 not in item["total"] or 2026 not in item["total"]:
            continue
        share = item["night"][2024] / item["total"][2024] if item["total"][2024] else 0
        night_change = pct(item["night"][2026], item["night"][2024])
        total_change = pct(item["total"][2026], item["total"][2024])
        row = (district, code, area, item, share, night_change, total_change)
        rows.append(row)
        if item["total"][2024] >= 1000 and item["night"][2024] >= 250 and share >= 0.18 and night_change <= -15:
            candidates.append(row)
    candidates.sort(key=lambda row: row[5])
    selected = []
    for district in DISTRICTS:
        selected.extend([row for row in candidates if row[0] == district][:2])
    lines = [
        "# 서울 구조 레이더 — 북부 생활권 야간 식음료 소비 현장 후보 v2",
        "",
        "비교: 동일 상권 코드의 2024년 1분기 대 2026년 1분기",
        "범위: CS100 식음료 서비스업 전체를 상권별로 합산한 21~24시 결제건수",
        "",
        "결합된 식음료 업종 행:",
        "- " + ", ".join(f"{district}: 2024년 {joined[(2024, district)]}행 / 2026년 {joined[(2026, district)]}행" for district in DISTRICTS),
        f"두 연도 모두 비교 가능한 상권: {len(rows)}곳",
        "",
        "선별 기준",
        "- 2024년 전체 결제 1,000건 이상, 21~24시 결제 250건 이상, 야간 결제 비중 18% 이상",
        "- 2024→2026 21~24시 결제 -15% 이하",
        "- 자치구별 상위 2곳만 표시. 현장 관찰 후보이지 기사 결론이 아닙니다.",
        "",
        f"조건 충족 상권: {len(candidates)}곳 / 현장 우선 후보: {len(selected)}곳",
        "",
    ]
    for district, code, area, item, share, night_change, total_change in selected:
        lines += [
            f"## {district} · {area}",
            f"- 상권코드: {code}",
            f"- 2024 야간 결제 비중: {share * 100:.1f}%",
            f"- 2024→2026: 21~24시 결제 {night_change:+.1f}%, 전체 결제 {total_change:+.1f}%",
            "- 포함 식음료 업종: " + ", ".join(sorted(item["names"][2024])),
            "- 현장 확인: 목·금요일 21시·23시 영업 점포·보행량·대기 여부를 같은 방식으로 기록",
            "- 섭외 실패 대안: 지도 영업시간·현장 표본·21~24시 결제 지표를 같은 상권 코드로 대조",
            "",
        ]
    if not selected:
        lines.append("- 없음. 상권 단위로 2024→2026 야간 식음료 결제가 집중 감소한 장소는 현재 기준에서 확인되지 않았습니다.")
    lines += ["", "해석", "- 이 분석은 매출이 아닌 이용 건수로 밤 소비를 본다.", "- 감소 원인은 영업시간·유동인구·경쟁·소비행태 중 무엇인지 이 자료만으로 말할 수 없다."]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
