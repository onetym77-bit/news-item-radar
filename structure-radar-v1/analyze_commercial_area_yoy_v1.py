"""Conservative commercial-area year-on-year observations (S1 only)."""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SALES_FIELD, STORE_FIELD = "THSMON_SELNG_AMT", "STOR_CO"
KEY_FIELDS = ("TRDAR_CD", "SVC_INDUTY_CD")


def newest_raw() -> Path:
    files = sorted((ROOT / "output" / "area" / "raw").glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("상권 단위 raw 스냅샷이 없습니다.")
    return files[0]


def number(value) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def index(source: dict, period: str) -> dict[tuple[str, str], dict]:
    period_data = next((item for item in source["periods"] if item["period"] == period), {})
    return {tuple(str(row.get(field, "")) for field in KEY_FIELDS): row for row in period_data.get("rows", [])}


def pct(current: float, previous: float) -> float | None:
    return (current - previous) / previous if previous > 0 else None


def main() -> int:
    raw_path = newest_raw()
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    current, prior = payload["periods"]
    sources = {item["label"]: item for item in payload["sources"]}
    stores, sales = sources["stores_by_area"], sources["sales_by_area"]
    store_now, store_then = index(stores, current), index(stores, prior)
    sale_now, sale_then = index(sales, current), index(sales, prior)
    common = set(store_now) & set(store_then) & set(sale_now) & set(sale_then)
    previous_sales = [number(sale_then[key].get(SALES_FIELD)) for key in common if number(sale_then[key].get(SALES_FIELD)) > 0]
    floor = statistics.quantiles(previous_sales, n=4)[0]
    observations = []
    for key in common:
        sales_now, sales_prior = number(sale_now[key].get(SALES_FIELD)), number(sale_then[key].get(SALES_FIELD))
        stores_now, stores_prior = number(store_now[key].get(STORE_FIELD)), number(store_then[key].get(STORE_FIELD))
        sales_change, store_change = pct(sales_now, sales_prior), pct(stores_now, stores_prior)
        if sales_change is None or store_change is None or sales_prior < floor or stores_now < 3:
            continue
        if abs(sales_change) < 0.30 or abs(store_change) < 0.10:
            continue
        if sales_change > 0 and store_change > 0:
            direction = "동반 증가"
        elif sales_change < 0 and store_change < 0:
            direction = "동반 감소"
        else:
            direction = "매출·점포 엇갈림"
        observations.append({
            "area": store_now[key].get("TRDAR_CD_NM", key[0]), "industry": store_now[key].get("SVC_INDUTY_CD_NM", key[1]),
            "sales_change": sales_change, "store_change": store_change, "direction": direction,
            "current_stores": stores_now, "current_sales": sales_now,
        })
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in observations:
        grouped[(item["industry"], item["direction"])].append(item)
    patterns = []
    for (industry, direction), items in grouped.items():
        if len(items) >= 5:
            patterns.append({"industry": industry, "direction": direction, "area_count": len(items),
                             "median_sales": statistics.median(row["sales_change"] for row in items),
                             "median_stores": statistics.median(row["store_change"] for row in items),
                             "examples": sorted(items, key=lambda row: abs(row["sales_change"]) + abs(row["store_change"]), reverse=True)[:5]})
    patterns.sort(key=lambda row: (row["area_count"], abs(row["median_sales"]) + abs(row["median_stores"])), reverse=True)
    observations.sort(key=lambda row: abs(row["sales_change"]) + abs(row["store_change"]), reverse=True)
    lines = ["서울 구조 레이더 — 상권 단위 전년 동분기 관측", "=" * 44, f"원본: {raw_path.name}",
             f"비교: {current} 대 {prior} (전년 동분기)", f"비교 가능한 상권×업종 행: {len(common)}",
             f"분석 최소 매출 기준: 전년 동분기 하위 25% 초과 ({floor:,.0f})", "",
             "판정 원칙", "- 매출 30% 이상, 점포 수 10% 이상 변화와 현재 점포 3개 이상을 함께 요구합니다.",
             "- 아래는 S1 관측입니다. 개별 상권의 수치 변화는 시민 경험이나 원인을 증명하지 않습니다.", "",
             f"반복 상권 패턴: {len(patterns)}건"]
    if not patterns:
        lines.append("- 조건을 통과한 반복 상권 패턴이 없습니다.")
    for item in patterns[:15]:
        lines.append(f"- {item['industry']} / {item['direction']} / {item['area_count']}개 상권 / 중앙값: 매출 {item['median_sales']:+.1%}, 점포 {item['median_stores']:+.1%}")
        lines.append("  예: " + ", ".join(f"{row['area']}(매출 {row['sales_change']:+.1%}, 점포 {row['store_change']:+.1%})" for row in item["examples"]))
    lines.extend(["", f"단일 상권 관찰: {len(observations)}건 중 상위 15건"])
    for item in observations[:15]:
        lines.append(f"- {item['area']} · {item['industry']} / {item['direction']} / 매출 {item['sales_change']:+.1%}, 점포 {item['store_change']:+.1%}")
    lines.extend(["", "다음 편집 단계", "- 반복 패턴은 지도·생활인구·유튜브·현장 관찰 중 하나와 교차한 뒤에만 S2 검토로 올립니다.",
                  "- 단일 상권 관찰은 대형 점포, 상권 경계·분류 변경, 카드 매출 포착 범위를 우선 배제합니다."])
    report_dir = ROOT / "output" / "area" / "analysis"
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / (raw_path.stem + f"-yoy-{current}.txt")
    if target.exists():
        print("이미 분석 파일이 있습니다: " + str(target))
        return 1
    target.write_text("\n".join(lines), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
