"""북부 생활권의 심야 생활인구 감소와 야간 상권의 장기 경로를 교차 확인한다.

기존 상권 원본 JSON을 읽어 호프-간이주점·노래방만 좁혀 본다.
이 스크립트는 기사 결론이 아닌 데이터 교차 관측을 출력한다.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "nightlife_check"
TARGET_DISTRICTS = {"강북구", "도봉구", "노원구"}
TARGET_INDUSTRIES = {"호프-간이주점", "노래방"}
YEARS = (2021, 2022, 2023, 2024, 2025, 2026)


def walk_lists(value):
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            yield value
        for item in value:
            yield from walk_lists(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_lists(item)


def locate_tables():
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
            if {"SIGNGU_CD_NM", "STDR_YYQU_CD", "SVC_INDUTY_CD_NM"}.issubset(fields):
                candidates.append((path, fields, rows))
    stores = [item for item in candidates if "STOR_CO" in item[1]]
    sales = [item for item in candidates if "THSMON_SELNG_AMT" in item[1] and "THSMON_SELNG_CO" in item[1]]
    # Pick the largest relevant table so partial debug samples are not selected.
    return (max(stores, key=lambda item: len(item[2])) if stores else None,
            max(sales, key=lambda item: len(item[2])) if sales else None,
            candidates)


def number(value):
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def year_from_quarter(value):
    text = str(value)
    return int(text[:4]) if len(text) >= 5 and text[:4].isdigit() else None


def pct(now, old):
    return None if not old else (now / old - 1) * 100


def direction(metrics, start, end):
    changes = [pct(metrics[name].get(end, 0), metrics[name].get(start, 0)) for name in ("sales", "transactions", "stores")]
    if any(change is None for change in changes):
        return "비교 불가", changes
    if changes[0] <= -10 and changes[1] <= -10 and changes[2] <= -5:
        return "세 지표 동반 감소", changes
    if changes[0] >= 10 and changes[1] >= 10 and changes[2] >= 5:
        return "세 지표 동반 증가", changes
    return "엇갈림·보합", changes


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_nightlife_longterm.txt"
    stores_table, sales_table, all_tables = locate_tables()
    if not stores_table or not sales_table:
        report.write_text(
            "# 북부 생활권 심야 인구×야간 상권 장기 교차\n\n"
            "상권 원본 테이블을 찾지 못했습니다.\n"
            "필요 필드: SIGNGU_CD_NM, STDR_YYQU_CD, SVC_INDUTY_CD_NM, STOR_CO, THSMON_SELNG_AMT, THSMON_SELNG_CO\n"
            f"발견한 유사 테이블: {len(all_tables)}개\n",
            encoding="utf-8",
        )
        print(f"완료: {report}")
        return 0

    store_rows, sale_rows = stores_table[2], sales_table[2]
    available = sorted({str(row.get("SVC_INDUTY_CD_NM", "")) for row in store_rows + sale_rows})
    found_industries = sorted(TARGET_INDUSTRIES.intersection(available))
    metrics = defaultdict(lambda: defaultdict(lambda: {"sales": defaultdict(float), "transactions": defaultdict(float), "stores": defaultdict(float)}))
    for row in sale_rows:
        district, industry, year = row.get("SIGNGU_CD_NM"), row.get("SVC_INDUTY_CD_NM"), year_from_quarter(row.get("STDR_YYQU_CD"))
        if district in TARGET_DISTRICTS and industry in found_industries and year in YEARS and str(row.get("STDR_YYQU_CD", ""))[-1:] == "1":
            metrics[district][industry]["sales"][year] += number(row.get("THSMON_SELNG_AMT"))
            metrics[district][industry]["transactions"][year] += number(row.get("THSMON_SELNG_CO"))
    for row in store_rows:
        district, industry, year = row.get("SIGNGU_CD_NM"), row.get("SVC_INDUTY_CD_NM"), year_from_quarter(row.get("STDR_YYQU_CD"))
        if district in TARGET_DISTRICTS and industry in found_industries and year in YEARS and str(row.get("STDR_YYQU_CD", ""))[-1:] == "1":
            metrics[district][industry]["stores"][year] += number(row.get("STOR_CO"))
    lines = [
        "# 서울 구조 레이더 — 북부 생활권 심야 인구×야간 상권 장기 교차 v1",
        "",
        "대상: 강북구·도봉구·노원구 / 업종: 호프-간이주점, 노래방",
        "상권 비교: 같은 분기(1분기)의 2021~2026. 매출액·결제 건수는 서울시 데이터의 ‘당월’ 지표 합계입니다.",
        "생활인구 비교: 이미 확인한 2017년 7월→2026년 7월 심야 인구 지속 감소 관측을 별도 입력으로 둡니다.",
        "",
        "판정 원칙",
        "- 코로나 영향이 큰 2021 대비 수치만으로 장기 쇠퇴를 선언하지 않습니다.",
        "- 2023→2026에 매출 -10%, 결제 -10%, 점포 -5%가 함께 나타날 때만 ‘최근 동반 감소’로 기록합니다.",
        "- 이 결과가 생활인구 감소와 맞아도 원인·기사 가치를 증명하지 않습니다.",
        "",
        f"원본: 점포 {stores_table[0].name} / 매출 {sales_table[0].name}",
        "발견 업종: " + (", ".join(found_industries) if found_industries else "없음"),
        "",
    ]
    if not found_industries:
        lines += [
            "대상 업종을 원본에서 찾지 못했습니다.",
            "유사 업종명 후보: " + ", ".join(name for name in available if "호프" in name or "노래" in name),
        ]
    else:
        for district in sorted(TARGET_DISTRICTS):
            for industry in found_industries:
                item = metrics[district][industry]
                recent_label, recent_changes = direction(item, 2023, 2026)
                all_label, all_changes = direction(item, 2021, 2026)
                lines += [
                    f"## {district} · {industry}",
                    f"- 2023→2026: {recent_label} / 매출 {recent_changes[0]:+.1f}%, 결제 {recent_changes[1]:+.1f}%, 점포 {recent_changes[2]:+.1f}%",
                    f"- 2021→2026: {all_label} / 매출 {all_changes[0]:+.1f}%, 결제 {all_changes[1]:+.1f}%, 점포 {all_changes[2]:+.1f}%",
                    "- 연도별: " + " | ".join(
                        f"{year}년 매출 {item['sales'][year]:,.0f}, 결제 {item['transactions'][year]:,.0f}, 점포 {item['stores'][year]:,.0f}" for year in YEARS
                    ),
                    "",
                ]
    lines += [
        "다음 편집 판정",
        "- 세 지역에서 동일 업종의 최근 동반 감소가 반복되고 심야 인구 감소와 맞을 때만 ‘북부 생활권 밤 상권’ 가설을 S2 검토로 올립니다.",
        "- 한 지역 또는 한 업종만 감소하면 ‘지역·업종 개별 변화’로 보류합니다.",
        "- S2가 되어도 현장 인터뷰가 불발되면 같은 요일·시간대 영업 종료 시각·보행량·빈 점포 표본 관찰을 대안으로 둡니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
