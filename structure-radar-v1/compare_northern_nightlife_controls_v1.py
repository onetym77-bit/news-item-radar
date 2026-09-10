"""북부 3구에서 호프-간이주점 감소가 생활 업종 대비 두드러지는지 확인한다."""

from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "nightlife_check"
TARGET_DISTRICTS = ("강북구", "도봉구", "노원구")
GROUPS = {
    "야간 기준업종": ("호프-간이주점",),
    "비교 생활업종": ("커피-음료", "한식음식점", "편의점"),
}
YEARS = (2023, 2024, 2025, 2026)


def load_base():
    path = ROOT / "check_northern_nightlife_longterm_v1.py"
    spec = importlib.util.spec_from_file_location("nightlife_base", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def locate_district_tables(base):
    import json
    candidates = []
    for path in ROOT.rglob("*.json"):
        if "output" not in path.parts:
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        for rows in base.walk_lists(data):
            fields = set(rows[0])
            if {"SIGNGU_CD_NM", "STDR_YYQU_CD", "SVC_INDUTY_CD_NM"}.issubset(fields) and not any(
                key in fields for key in ("TRDAR_CD", "TRDAR_NM", "TRDAR_SE_CD", "TRDAR_SE_NM")
            ):
                candidates.append((path, fields, rows))
    stores = [item for item in candidates if "STOR_CO" in item[1]]
    sales = [item for item in candidates if "THSMON_SELNG_AMT" in item[1] and "THSMON_SELNG_CO" in item[1]]
    return max(stores, key=lambda item: len(item[2])), max(sales, key=lambda item: len(item[2]))


def main() -> int:
    base = load_base()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_nightlife_controls.txt"
    try:
        store_table, sale_table = locate_district_tables(base)
    except ValueError:
        report.write_text("# 북부 생활권 야간업종 대조\n\n자치구 단위 상권 원본을 찾지 못했습니다.\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    all_industries = {industry for values in GROUPS.values() for industry in values}
    available = {str(row.get("SVC_INDUTY_CD_NM", "")) for row in store_table[2] + sale_table[2]}
    found = sorted(all_industries & available)
    metrics = defaultdict(lambda: defaultdict(lambda: {"sales": defaultdict(float), "transactions": defaultdict(float), "stores": defaultdict(float)}))
    for row in sale_table[2]:
        district, industry = row.get("SIGNGU_CD_NM"), row.get("SVC_INDUTY_CD_NM")
        year = base.year_from_quarter(row.get("STDR_YYQU_CD"))
        if district in TARGET_DISTRICTS and industry in found and year in YEARS and str(row.get("STDR_YYQU_CD"))[-1:] == "1":
            metrics[district][industry]["sales"][year] += base.number(row.get("THSMON_SELNG_AMT"))
            metrics[district][industry]["transactions"][year] += base.number(row.get("THSMON_SELNG_CO"))
    for row in store_table[2]:
        district, industry = row.get("SIGNGU_CD_NM"), row.get("SVC_INDUTY_CD_NM")
        year = base.year_from_quarter(row.get("STDR_YYQU_CD"))
        if district in TARGET_DISTRICTS and industry in found and year in YEARS and str(row.get("STDR_YYQU_CD"))[-1:] == "1":
            metrics[district][industry]["stores"][year] += base.number(row.get("STOR_CO"))

    results = []
    for industry in found:
        for district in TARGET_DISTRICTS:
            item = metrics[district][industry]
            label, changes = base.direction(item, 2023, 2026)
            results.append((industry, district, label, changes))
    nightlife_all = all(label == "세 지표 동반 감소" for industry, _, label, _ in results if industry == "호프-간이주점")
    control_results = [row for row in results if row[0] != "호프-간이주점"]
    controls_all_declining = sum(label == "세 지표 동반 감소" for _, _, label, _ in control_results)
    lines = [
        "# 서울 구조 레이더 — 북부 생활권 야간업종 대조 v1",
        "",
        "대상: 강북구·도봉구·노원구 / 비교: 2023년 1분기 대 2026년 1분기",
        "기준업종: 호프-간이주점 / 비교업종: 커피-음료, 한식음식점, 편의점",
        "",
        "판정 원칙",
        "- 매출 -10%, 결제 -10%, 점포 -5%를 모두 충족할 때 ‘세 지표 동반 감소’입니다.",
        "- 비교업종도 넓게 동반 감소하면 ‘야간 소비 특화 변화’가 아니라 지역 상권 전반 축소로 해석합니다.",
        "- 비교업종이 혼조인데 호프-간이주점만 세 지역에서 동반 감소하면 야간 소비 변화 가설을 강화합니다.",
        "",
        "업종·지역별 결과",
        "",
    ]
    for industry in found:
        lines.append(f"## {industry}")
        for _, district, label, changes in [row for row in results if row[0] == industry]:
            lines.append(f"- {district}: {label} / 매출 {changes[0]:+.1f}%, 결제 {changes[1]:+.1f}%, 점포 {changes[2]:+.1f}%")
        lines.append("")
    lines += ["대조 판정", ""]
    if nightlife_all and controls_all_declining <= max(1, len(control_results) // 3):
        lines.append("- 야간 소비 변화 가설 강화: 호프-간이주점은 세 지역에서 동반 감소했지만, 비교 생활업종의 동반 감소는 제한적입니다.")
    elif nightlife_all and controls_all_declining >= (len(control_results) * 2) // 3:
        lines.append("- 지역 상권 전반 축소 가능성: 호프-간이주점뿐 아니라 비교 생활업종도 다수 지역에서 동반 감소합니다.")
    else:
        lines.append("- 혼조: 야간업종 특화 변화와 지역 상권 전반 축소를 아직 구분할 수 없습니다.")
    lines += [
        "", "다음 단계",
        "- ‘야간 소비 변화 가설 강화’일 때만 역별 심야 승하차·영업 종료 시각 표본 관찰로 공간을 좁힙니다.",
        "- ‘지역 상권 전반 축소’면 주거인구·연령구성·공실·생활서비스 접근성으로 기사 가설을 다시 잡습니다.",
        "- 어느 경우에도 이 결과만으로 원인이나 정책 효과를 단정하지 않습니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
