"""Second-pass commercial observations using sales amount, transaction count,
and store count together. Separates dominant patterns from split patterns.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEY_FIELDS = ("TRDAR_CD", "SVC_INDUTY_CD")
AMOUNT, COUNT, STORES = "THSMON_SELNG_AMT", "THSMON_SELNG_CO", "STOR_CO"


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
    item = next(row for row in source["periods"] if row["period"] == period)
    return {tuple(str(row.get(field, "")) for field in KEY_FIELDS): row for row in item["rows"]}


def change(now: float, before: float) -> float | None:
    return (now - before) / before if before > 0 else None


def main() -> int:
    raw_path = newest_raw()
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    current, previous = data["periods"]
    sources = {row["label"]: row for row in data["sources"]}
    s_now, s_then = index(sources["stores_by_area"], current), index(sources["stores_by_area"], previous)
    a_now, a_then = index(sources["sales_by_area"], current), index(sources["sales_by_area"], previous)
    common = set(s_now) & set(s_then) & set(a_now) & set(a_then)
    amount_floor = statistics.quantiles([number(a_then[key].get(AMOUNT)) for key in common if number(a_then[key].get(AMOUNT)) > 0], n=4)[0]
    count_floor = statistics.quantiles([number(a_then[key].get(COUNT)) for key in common if number(a_then[key].get(COUNT)) > 0], n=4)[0]
    signals = []
    for key in common:
        amount_now, amount_then = number(a_now[key].get(AMOUNT)), number(a_then[key].get(AMOUNT))
        count_now, count_then = number(a_now[key].get(COUNT)), number(a_then[key].get(COUNT))
        stores_now, stores_then = number(s_now[key].get(STORES)), number(s_then[key].get(STORES))
        amount_delta, count_delta, store_delta = change(amount_now, amount_then), change(count_now, count_then), change(stores_now, stores_then)
        if None in (amount_delta, count_delta, store_delta) or amount_then < amount_floor or count_then < count_floor or stores_now < 3:
            continue
        # Sales and transaction volume must point in the same direction. This
        # removes price-only changes and much of the small-base volatility.
        if amount_delta >= 0.25 and count_delta >= 0.20 and store_delta >= 0.10:
            direction = "세 지표 동반 증가"
        elif amount_delta <= -0.25 and count_delta <= -0.20 and store_delta <= -0.10:
            direction = "세 지표 동반 감소"
        else:
            continue
        signals.append({"industry": s_now[key].get("SVC_INDUTY_CD_NM", key[1]), "area": s_now[key].get("TRDAR_CD_NM", key[0]),
                        "direction": direction, "amount": amount_delta, "count": count_delta, "stores": store_delta})
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for signal in signals:
        grouped[(signal["industry"], signal["direction"])].append(signal)
    by_industry: dict[str, Counter] = defaultdict(Counter)
    for signal in signals:
        by_industry[signal["industry"]][signal["direction"]] += 1
    dominant, split = [], []
    for industry, directions in by_industry.items():
        inc, dec = directions["세 지표 동반 증가"], directions["세 지표 동반 감소"]
        if inc >= 5 and dec >= 5:
            split.append((industry, inc, dec))
        for direction, count in directions.items():
            opposite = dec if direction == "세 지표 동반 증가" else inc
            if count >= 5 and count >= max(2 * opposite, 5):
                rows = grouped[(industry, direction)]
                dominant.append({"industry": industry, "direction": direction, "areas": count,
                                 "median_amount": statistics.median(row["amount"] for row in rows),
                                 "median_count": statistics.median(row["count"] for row in rows),
                                 "median_stores": statistics.median(row["stores"] for row in rows),
                                 "examples": sorted(rows, key=lambda row: abs(row["amount"]) + abs(row["count"]) + abs(row["stores"]), reverse=True)[:5]})
    dominant.sort(key=lambda row: (row["areas"], abs(row["median_amount"]) + abs(row["median_count"]) + abs(row["median_stores"])), reverse=True)
    split.sort(key=lambda row: row[1] + row[2], reverse=True)
    lines = ["서울 구조 레이더 — 상권 행동 교차 관측 v2", "=" * 45, f"원본: {raw_path.name}", f"비교: {current} 대 {previous} (전년 동분기)",
             f"비교 가능 행: {len(common)}", f"최소 기준: 매출 {amount_floor:,.0f}, 결제 건수 {count_floor:,.0f} (전년 동분기 하위 25% 초과)", "",
             "판정 원칙", "- 매출액·결제 건수·점포 수가 모두 같은 방향으로 각각 +25%/+20%/+10% 또는 그 이하로 변한 경우만 봅니다.",
             "- 5개 이상 상권에서 나타나도, 반대 방향 신호가 비슷하면 ‘지역 분화’로만 기록합니다.", "",
             f"우세 패턴(S1 우선 관찰): {len(dominant)}건"]
    if not dominant:
        lines.append("- 우세 패턴 없음. 현재 데이터만으로는 S2 검토 대상이 없습니다.")
    for item in dominant[:12]:
        lines.append(f"- {item['industry']} / {item['direction']} / {item['areas']}개 상권 / 중앙값: 매출 {item['median_amount']:+.1%}, 결제 {item['median_count']:+.1%}, 점포 {item['median_stores']:+.1%}")
        lines.append("  예: " + ", ".join(f"{row['area']}(매출 {row['amount']:+.1%}, 결제 {row['count']:+.1%}, 점포 {row['stores']:+.1%})" for row in item["examples"]))
    lines.extend(["", f"지역 분화 경고(기사 후보 아님): {len(split)}건"])
    for industry, inc, dec in split[:12]:
        lines.append(f"- {industry}: 세 지표 동반 증가 {inc}개 상권 / 동반 감소 {dec}개 상권")
    lines.extend(["", "편집 규칙", "- 우세 패턴도 생활인구·관심 신호·현장 관찰 중 하나가 더해지기 전에는 S1입니다.",
                  "- 지역 분화 경고는 지도상 인접성·주거/유동인구·상권 유형을 확인하기 전에는 기사 프레임으로 쓰지 않습니다."])
    output = ROOT / "output" / "area" / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    target = output / (raw_path.stem + f"-behavior-v2-{current}.txt")
    if target.exists():
        print("이미 분석 파일이 있습니다: " + str(target))
        return 1
    target.write_text("\n".join(lines), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
