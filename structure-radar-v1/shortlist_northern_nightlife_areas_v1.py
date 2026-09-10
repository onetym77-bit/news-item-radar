"""북부 3구 야간 소비 변화 가설의 현장 상권 후보를 좁힌다.

기존 상권 단위 원본만 재사용한다. 후보는 취재 장소일 뿐, 원인이나 기사 결론이 아니다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "nightlife_check"
TARGET_DISTRICTS = ("강북구", "도봉구", "노원구")
INDUSTRY = "호프-간이주점"
YEARS = (2023, 2026)


def walk_lists(value):
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            yield value
        for item in value:
            yield from walk_lists(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_lists(item)


def locate_area_tables():
    candidates = []
    for path in ROOT.rglob("*.json"):
        if "output" not in path.parts:
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        for rows in walk_lists(data):
            fields = set(rows[0])
            if {"SIGNGU_CD_NM", "STDR_YYQU_CD", "SVC_INDUTY_CD_NM", "TRDAR_CD"}.issubset(fields):
                candidates.append((path, fields, rows))
    stores = [item for item in candidates if "STOR_CO" in item[1]]
    sales = [item for item in candidates if "THSMON_SELNG_AMT" in item[1] and "THSMON_SELNG_CO" in item[1]]
    return (max(stores, key=lambda item: len(item[2])) if stores else None,
            max(sales, key=lambda item: len(item[2])) if sales else None)


def number(value):
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def year(value):
    text = str(value)
    return int(text[:4]) if len(text) >= 5 and text[:4].isdigit() else None


def pct(now, old):
    return None if not old else (now / old - 1) * 100


def name(row):
    return str(row.get("TRDAR_NM") or row.get("TRDAR_CD_NM") or row.get("TRDAR_CD"))


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_nightlife_area_shortlist.txt"
    store_table, sale_table = locate_area_tables()
    if not store_table or not sale_table:
        report.write_text("# 북부 생활권 야간 상권 현장 후보\n\n상권 단위 원본 테이블을 찾지 못했습니다.\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    data = defaultdict(lambda: {"sales": defaultdict(float), "transactions": defaultdict(float), "stores": defaultdict(float)})
    for row in sale_table[2]:
        district, industry, current_year = row.get("SIGNGU_CD_NM"), row.get("SVC_INDUTY_CD_NM"), year(row.get("STDR_YYQU_CD"))
        if district in TARGET_DISTRICTS and industry == INDUSTRY and current_year in YEARS and str(row.get("STDR_YYQU_CD"))[-1:] == "1":
            key = (district, str(row.get("TRDAR_CD")), name(row))
            data[key]["sales"][current_year] += number(row.get("THSMON_SELNG_AMT"))
            data[key]["transactions"][current_year] += number(row.get("THSMON_SELNG_CO"))
    for row in store_table[2]:
        district, industry, current_year = row.get("SIGNGU_CD_NM"), row.get("SVC_INDUTY_CD_NM"), year(row.get("STDR_YYQU_CD"))
        if district in TARGET_DISTRICTS and industry == INDUSTRY and current_year in YEARS and str(row.get("STDR_YYQU_CD"))[-1:] == "1":
            key = (district, str(row.get("TRDAR_CD")), name(row))
            data[key]["stores"][current_year] += number(row.get("STOR_CO"))
    candidates = []
    for (district, code, area_name), item in data.items():
        old_sales, old_tx, old_stores = item["sales"][2023], item["transactions"][2023], item["stores"][2023]
        new_sales, new_tx, new_stores = item["sales"][2026], item["transactions"][2026], item["stores"][2026]
        sales_change, tx_change, store_change = pct(new_sales, old_sales), pct(new_tx, old_tx), pct(new_stores, old_stores)
        if not all(value is not None for value in (sales_change, tx_change, store_change)):
            continue
        # Avoid very small bases and require the same three-way decline used at district level.
        if old_stores >= 5 and old_tx >= 300 and sales_change <= -10 and tx_change <= -10 and store_change <= -5:
            score = abs(sales_change) + abs(tx_change) + abs(store_change)
            candidates.append((score, district, code, area_name, old_sales, new_sales, old_tx, new_tx, old_stores, new_stores, sales_change, tx_change, store_change))
    candidates.sort(reverse=True)
    selected = []
    for district in TARGET_DISTRICTS:
        selected.extend([row for row in candidates if row[1] == district][:2])
    lines = [
        "# 서울 구조 레이더 — 북부 생활권 야간 상권 현장 후보 v1",
        "",
        "가설: 강북·도봉·노원의 심야 인구 감소와 호프-간이주점 감소가 같은 생활권에서 함께 나타난다.",
        "비교: 상권 단위 2023년 1분기 대 2026년 1분기 / 지표: 당월 매출액·결제건수·점포 수",
        "",
        "선별 기준",
        "- 2023년 점포 5개 이상, 결제 300건 이상",
        "- 매출 -10%, 결제 -10%, 점포 -5%를 모두 충족",
        "- 자치구별 상위 2곳만 표시. 큰 증감률 자체는 기사 가치가 아닙니다.",
        "",
        f"조건 충족 상권: {len(candidates)}곳 / 현장 우선 후보: {len(selected)}곳",
        "",
    ]
    for _, district, code, area_name, old_sales, new_sales, old_tx, new_tx, old_stores, new_stores, sales_change, tx_change, store_change in selected:
        lines += [
            f"## {district} · {area_name}",
            f"- 상권코드: {code}",
            f"- 매출: {old_sales:,.0f} → {new_sales:,.0f} ({sales_change:+.1f}%)",
            f"- 결제: {old_tx:,.0f} → {new_tx:,.0f} ({tx_change:+.1f}%)",
            f"- 점포: {old_stores:,.0f} → {new_stores:,.0f} ({store_change:+.1f}%)",
            "- 현장 확인: 같은 요일 21시·23시·01시에 영업 점포 수, 빈 점포, 보행량을 표본 기록",
            "- 섭외 A: 3년 이상 영업한 호프·간이주점 업주 1명 또는 야간 근무자 1명",
            "- 섭외 실패 대안: 지도 영업정보·현장 표본·점포 수 공개데이터를 같은 기준일로 대조",
            "",
        ]
    if not selected:
        lines.append("- 현장 우선 후보 없음. 현재 기준에서는 자치구 평균만으로 장소를 정하지 않습니다.")
    lines += [
        "다음 편집 단계",
        "- 후보 상권을 지도에서 확인한 뒤 인접 역의 심야 승하차 또는 막차 이후 이동 자료를 추가로 본다.",
        "- 현장 관찰은 ‘왜’가 아니라 ‘실제로 밤이 일찍 끝나는가’를 검증하는 목적이다.",
        "- 인터뷰·현장·추가 이동신호가 모두 약하면 이 가설은 S2에서 보류한다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
