"""정규화된 상권코드 결합 뒤, 북부 3구 야간 상권의 실제 행 수와 필터 탈락을 진단한다."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAPPING = ROOT / "output" / "commercial_area_mapping" / "commercial_area_mapping.json"
TREND = ROOT / "output" / "commercial_area_trend" / "commercial_area_trend.json"
OUTPUT = ROOT / "output" / "nightlife_check"
DISTRICTS = ("강북구", "도봉구", "노원구")
YEARS = (2023, 2026)


def norm(value):
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text


def num(value):
    try: return float(str(value).replace(",", ""))
    except (TypeError, ValueError): return 0.0


def pct(now, old): return None if not old else (now / old - 1) * 100


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "northern_nightlife_area_join_diagnostic_v2.txt"
    mapping = json.loads(MAPPING.read_text(encoding="utf-8")).get("rows", [])
    trend = json.loads(TREND.read_text(encoding="utf-8")).get("datasets", {})
    lookup = {norm(row.get("TRDAR_CD")): (str(row.get("SIGNGU_CD_NM")), str(row.get("TRDAR_CD_NM"))) for row in mapping}
    values = defaultdict(lambda: {"sales": {}, "tx": {}, "stores": {}, "night": {}})
    joined_counts = Counter()
    for year in YEARS:
        for row in trend.get("sales", {}).get(str(year), []):
            code = norm(row.get("TRDAR_CD")); meta = lookup.get(code)
            if meta and meta[0] in DISTRICTS and row.get("SVC_INDUTY_CD_NM") == "호프-간이주점":
                key = (meta[0], code, meta[1]); joined_counts[("sales", year, meta[0])] += 1
                values[key]["sales"][year] = num(row.get("THSMON_SELNG_AMT")); values[key]["tx"][year] = num(row.get("THSMON_SELNG_CO")); values[key]["night"][year] = num(row.get("TMZON_21_24_SELNG_CO"))
        for row in trend.get("stores", {}).get(str(year), []):
            code = norm(row.get("TRDAR_CD")); meta = lookup.get(code)
            if meta and meta[0] in DISTRICTS and row.get("SVC_INDUTY_CD_NM") == "호프-간이주점":
                key = (meta[0], code, meta[1]); joined_counts[("stores", year, meta[0])] += 1
                values[key]["stores"][year] = num(row.get("STOR_CO"))
    rows = []
    for (district, code, name), v in values.items():
        if not all(year in v[metric] for year in YEARS for metric in ("sales", "tx", "stores", "night")):
            continue
        changes = (pct(v["sales"][2026], v["sales"][2023]), pct(v["tx"][2026], v["tx"][2023]), pct(v["stores"][2026], v["stores"][2023]), pct(v["night"][2026], v["night"][2023]))
        checks = (v["stores"][2023] >= 5 and v["tx"][2023] >= 300, changes[0] <= -10, changes[1] <= -10, changes[2] <= -5, changes[3] <= -10)
        rows.append((sum(checks), district, name, changes, checks))
    lines = ["# 서울 구조 레이더 — 북부 야간 상권 정규화 결합 진단 v2", "", "결합 행 수", ""]
    for district in DISTRICTS:
        lines.append(f"- {district}: 2023 매출 {joined_counts[('sales', 2023, district)]}행 / 점포 {joined_counts[('stores', 2023, district)]}행 / 2026 매출 {joined_counts[('sales', 2026, district)]}행 / 점포 {joined_counts[('stores', 2026, district)]}행")
    lines += ["", f"두 연도·두 원본이 모두 결합된 상권: {len(rows)}곳", ""]
    for district in DISTRICTS:
        lines += [f"## {district} 근접 상권", ""]
        for passed, _, name, changes, checks in sorted([row for row in rows if row[1] == district], reverse=True)[:5]:
            fails = ", ".join(label for label, ok in zip(("규모", "매출", "전체결제", "점포", "21~24시결제"), checks) if not ok)
            lines.append(f"- {name} / 통과 {passed}/5 / 매출 {changes[0]:+.1f}%, 전체결제 {changes[1]:+.1f}%, 점포 {changes[2]:+.1f}%, 21~24시결제 {changes[3]:+.1f}% / 미충족: {fails or '없음'}")
        if not [row for row in rows if row[1] == district]: lines.append("- 없음")
        lines.append("")
    lines += ["해석", "- 결합 행 수가 충분하면 0건은 데이터 연결 문제가 아니라 필터·공간 분산 문제입니다.", "- 이 진단은 기준 변경을 위한 것이 아니라, 현장 단위를 지정할 근거가 있는지 판단하기 위한 것입니다."]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
