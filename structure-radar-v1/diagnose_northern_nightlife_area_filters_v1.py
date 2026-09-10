"""북부 야간 상권 현장 후보가 0건일 때 탈락 조건을 진단한다."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE_PATH = ROOT / "shortlist_northern_nightlife_areas_v2.py"


def load_base():
    spec = importlib.util.spec_from_file_location("area_shortlist", BASE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    base = load_base()
    base.OUTPUT.mkdir(parents=True, exist_ok=True)
    report = base.OUTPUT / "northern_nightlife_area_filter_diagnostic.txt"
    if not base.MAPPING.exists() or not base.TREND.exists():
        report.write_text("# 북부 야간 상권 필터 진단\n\n입력 원본이 없습니다.\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    import json
    mapping_rows = json.loads(base.MAPPING.read_text(encoding="utf-8")).get("rows", [])
    trend = json.loads(base.TREND.read_text(encoding="utf-8")).get("datasets", {})
    district_of = {str(row.get("TRDAR_CD")): str(row.get("SIGNGU_CD_NM")) for row in mapping_rows}
    name_of = {str(row.get("TRDAR_CD")): str(row.get("TRDAR_CD_NM")) for row in mapping_rows}
    values = {}
    for year in base.YEARS:
        for row in trend.get("sales", {}).get(str(year), []):
            code = str(row.get("TRDAR_CD")); district = district_of.get(code)
            if district in base.DISTRICTS and row.get("SVC_INDUTY_CD_NM") == base.INDUSTRY:
                item = values.setdefault((district, code, name_of.get(code, row.get("TRDAR_CD_NM", code))), {"sales": {}, "tx": {}, "stores": {}, "night_tx": {}})
                item["sales"][year] = base.num(row.get("THSMON_SELNG_AMT"))
                item["tx"][year] = base.num(row.get("THSMON_SELNG_CO"))
                item["night_tx"][year] = base.num(row.get("TMZON_21_24_SELNG_CO"))
        for row in trend.get("stores", {}).get(str(year), []):
            code = str(row.get("TRDAR_CD")); district = district_of.get(code)
            if district in base.DISTRICTS and row.get("SVC_INDUTY_CD_NM") == base.INDUSTRY:
                item = values.setdefault((district, code, name_of.get(code, row.get("TRDAR_CD_NM", code))), {"sales": {}, "tx": {}, "stores": {}, "night_tx": {}})
                item["stores"][year] = base.num(row.get("STOR_CO"))
    rows = []
    for (district, code, area), item in values.items():
        sales = base.change(item["sales"].get(2026, 0), item["sales"].get(2023, 0))
        tx = base.change(item["tx"].get(2026, 0), item["tx"].get(2023, 0))
        stores = base.change(item["stores"].get(2026, 0), item["stores"].get(2023, 0))
        night = base.change(item["night_tx"].get(2026, 0), item["night_tx"].get(2023, 0))
        if None in (sales, tx, stores, night):
            continue
        checks = {
            "규모": item["stores"].get(2023, 0) >= 5 and item["tx"].get(2023, 0) >= 300,
            "매출": sales <= -10, "전체결제": tx <= -10, "점포": stores <= -5, "21~24시결제": night <= -10,
        }
        rows.append((sum(checks.values()), district, area, sales, tx, stores, night, checks, item))
    lines = [
        "# 서울 구조 레이더 — 북부 야간 상권 현장 후보 필터 진단",
        "",
        f"연결된 대상 상권: {len(rows)}곳 (강북·도봉·노원, 호프-간이주점)",
        "0건의 원인을 보기 위한 진단이며, 기준을 완화하거나 기사 후보를 새로 만들지 않습니다.",
        "",
    ]
    for district in base.DISTRICTS:
        selected = sorted([row for row in rows if row[1] == district], reverse=True)[:5]
        lines += [f"## {district} 근접 상권", ""]
        if not selected:
            lines.append("- 연결된 상권 없음")
        for passed, _, area, sales, tx, stores, night, checks, item in selected:
            failed = ", ".join(name for name, passed_check in checks.items() if not passed_check)
            lines.append(f"- {area} / 통과 {passed}/5 / 매출 {sales:+.1f}%, 전체결제 {tx:+.1f}%, 점포 {stores:+.1f}%, 21~24시결제 {night:+.1f}% / 미충족: {failed or '없음'}")
        lines.append("")
    counts = {name: sum(row[7][name] for row in rows) for name in ("규모", "매출", "전체결제", "점포", "21~24시결제")}
    lines += ["필터별 통과 수", ""]
    lines += [f"- {name}: {count}/{len(rows)}곳" for name, count in counts.items()]
    lines += [
        "", "판정",
        "- 21~24시 결제가 가장 자주 탈락하면, 상권 단위에서 ‘밤 소비 감소’가 집중되지 않은 것입니다.",
        "- 규모 기준이 가장 자주 탈락하면, 자치구 합계 감소가 소규모 상권 다수에 분산됐을 가능성이 큽니다.",
        "- 매출·전체결제·점포가 모두 탈락하면 자치구 합계와 상권 단위의 공간 구성 차이 또는 경계 변화를 점검합니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
