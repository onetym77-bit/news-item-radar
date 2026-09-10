"""Find conservative year-on-year commercial structure observations.

Reads the latest immutable baseline snapshot. Produces S1 observations only;
no result is a story recommendation or a claim about citizens' experience.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEY_FIELDS = ("SIGNGU_CD", "SVC_INDUTY_CD")
SALES_FIELD = "THSMON_SELNG_AMT"
STORE_FIELD = "STOR_CO"


def newest_raw() -> Path:
    files = sorted((ROOT / "output" / "commercial" / "raw").glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("상권 raw 스냅샷이 없습니다.")
    return files[0]


def numeric(value) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def quarter_pair(periods: set[str]) -> tuple[str, str]:
    latest = max(periods)
    year, quarter = int(latest[:4]), latest[4:]
    previous_year = f"{year - 1}{quarter}"
    if previous_year not in periods:
        raise ValueError(f"전년 동분기 {previous_year}가 없습니다.")
    return latest, previous_year


def index_rows(rows: list[dict], period: str) -> dict[tuple[str, str], dict]:
    return {tuple(str(row.get(field, "")) for field in KEY_FIELDS): row for row in rows if str(row.get("STDR_YYQU_CD")) == period}


def pct_change(current: float, previous: float) -> float | None:
    return None if previous <= 0 else (current - previous) / previous


def main() -> int:
    raw_path = newest_raw()
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    sources = {source.get("label"): source.get("rows", []) for source in payload.get("sources", [])}
    stores, sales = sources.get("stores_by_district", []), sources.get("sales_by_district", [])
    if not stores or not sales:
        raise ValueError("점포 또는 매출 원천이 비어 있습니다.")
    periods = {str(row.get("STDR_YYQU_CD")) for row in stores} & {str(row.get("STDR_YYQU_CD")) for row in sales}
    latest, previous = quarter_pair(periods)
    store_now, store_then = index_rows(stores, latest), index_rows(stores, previous)
    sales_now, sales_then = index_rows(sales, latest), index_rows(sales, previous)
    common = set(store_now) & set(store_then) & set(sales_now) & set(sales_then)
    sales_floor = statistics.quantiles([numeric(sales_then[key].get(SALES_FIELD)) for key in common if numeric(sales_then[key].get(SALES_FIELD)) > 0], n=4)[0]
    observations = []
    for key in common:
        current_sales, prior_sales = numeric(sales_now[key].get(SALES_FIELD)), numeric(sales_then[key].get(SALES_FIELD))
        current_stores, prior_stores = numeric(store_now[key].get(STORE_FIELD)), numeric(store_then[key].get(STORE_FIELD))
        sales_change, store_change = pct_change(current_sales, prior_sales), pct_change(current_stores, prior_stores)
        if sales_change is None or store_change is None or prior_sales < sales_floor or current_stores < 10:
            continue
        district = store_now[key].get("SIGNGU_CD_NM", key[0])
        industry = store_now[key].get("SVC_INDUTY_CD_NM", key[1])
        # A signal requires material movement in both market measures. It is
        # deliberately not labeled as cause, harm, or a news recommendation.
        if abs(sales_change) < 0.20 or abs(store_change) < 0.05:
            continue
        direction = "동반 증가" if sales_change > 0 and store_change > 0 else "동반 감소" if sales_change < 0 and store_change < 0 else "매출·점포 엇갈림"
        observations.append({"district": district, "industry": industry, "sales_change": sales_change,
                             "store_change": store_change, "direction": direction,
                             "current_sales": current_sales, "current_stores": current_stores})
    by_industry: dict[str, list[dict]] = defaultdict(list)
    for item in observations:
        by_industry[item["industry"]].append(item)
    patterns = []
    for industry, items in by_industry.items():
        for direction in ("동반 증가", "동반 감소", "매출·점포 엇갈림"):
            same = [item for item in items if item["direction"] == direction]
            if len(same) >= 3:
                patterns.append({"industry": industry, "direction": direction, "districts": len(same),
                                 "median_sales_change": statistics.median(item["sales_change"] for item in same),
                                 "median_store_change": statistics.median(item["store_change"] for item in same),
                                 "examples": sorted(same, key=lambda item: abs(item["sales_change"]) + abs(item["store_change"]), reverse=True)[:4]})
    patterns.sort(key=lambda item: (item["districts"], abs(item["median_sales_change"]) + abs(item["median_store_change"])), reverse=True)
    observations.sort(key=lambda item: abs(item["sales_change"]) + abs(item["store_change"]), reverse=True)
    lines = ["서울 구조 레이더 — 상권 전년 동분기 관측", "=" * 42,
             f"원본: {raw_path.name}", f"비교: {latest} 대 {previous} (전년 동분기)",
             f"비교 가능한 자치구×업종 행: {len(common)}", f"분석 최소 매출 기준: 전년 동분기 하위 25% 초과 ({sales_floor:,.0f})", "",
             "판정 원칙", "- 매출 변화 20% 이상, 점포 수 변화 5% 이상, 현재 점포 수 10개 이상만 관찰합니다.",
             "- 아래는 S1 관측 신호입니다. 원인·시민 경험·기사 가치를 뜻하지 않습니다.", ""]
    lines.append(f"다수 자치구 패턴: {len(patterns)}건")
    if not patterns:
        lines.append("- 조건을 충족한 다수 자치구 패턴이 없습니다.")
    for item in patterns[:12]:
        lines.append(f"- {item['industry']} / {item['direction']} / {item['districts']}개 자치구 / 중앙값: 매출 {item['median_sales_change']:+.1%}, 점포 {item['median_store_change']:+.1%}")
        lines.append("  예: " + ", ".join(f"{row['district']}(매출 {row['sales_change']:+.1%}, 점포 {row['store_change']:+.1%})" for row in item["examples"]))
    lines.extend(["", f"단일 지역 관찰: {len(observations)}건 중 상위 12건"])
    for item in observations[:12]:
        lines.append(f"- {item['district']} · {item['industry']} / {item['direction']} / 매출 {item['sales_change']:+.1%}, 점포 {item['store_change']:+.1%}")
    lines.extend(["", "다음 편집 단계", "- 다수 자치구 패턴은 관심 레이더·생활인구·현장 관찰 중 하나와 교차할 때만 S2 검토로 올립니다.",
                  "- 단일 지역 관찰은 데이터 오류, 업종 분류 변경, 대형 점포 효과를 먼저 배제합니다."])
    target_dir = ROOT / "output" / "commercial" / "analysis"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (raw_path.stem + f"-yoy-{latest}.txt")
    if target.exists():
        print("이미 분석 파일이 있습니다: " + str(target))
        return 1
    target.write_text("\n".join(lines), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
