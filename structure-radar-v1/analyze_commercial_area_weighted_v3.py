"""Weighted citywide validation for commercial-area observations.

Counts of changing areas can mislead. This pass sums sales, transactions, and
stores by industry before comparing matched year-on-year quarters.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEYS = ("TRDAR_CD", "SVC_INDUTY_CD")
AMOUNT, COUNT, STORES = "THSMON_SELNG_AMT", "THSMON_SELNG_CO", "STOR_CO"


def latest_raw() -> Path:
    files = sorted((ROOT / "output" / "area" / "raw").glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("상권 단위 raw 스냅샷이 없습니다.")
    return files[0]


def num(value) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def rows(source: dict, period: str) -> dict[tuple[str, str], dict]:
    item = next(value for value in source["periods"] if value["period"] == period)
    return {tuple(str(row.get(key, "")) for key in KEYS): row for row in item["rows"]}


def pct(now: float, then: float) -> float | None:
    return (now - then) / then if then else None


def main() -> int:
    raw_path = latest_raw()
    data = json.loads(raw_path.read_text(encoding="utf-8"))
    current, previous = data["periods"]
    sources = {source["label"]: source for source in data["sources"]}
    store_now, store_then = rows(sources["stores_by_area"], current), rows(sources["stores_by_area"], previous)
    sale_now, sale_then = rows(sources["sales_by_area"], current), rows(sources["sales_by_area"], previous)
    common = set(store_now) & set(store_then) & set(sale_now) & set(sale_then)
    totals = defaultdict(lambda: {"now_amount": 0.0, "then_amount": 0.0, "now_count": 0.0, "then_count": 0.0, "now_stores": 0.0, "then_stores": 0.0, "up": 0, "down": 0})
    for key in common:
        industry = store_now[key].get("SVC_INDUTY_CD_NM", key[1])
        bucket = totals[industry]
        values = {
            "now_amount": num(sale_now[key].get(AMOUNT)), "then_amount": num(sale_then[key].get(AMOUNT)),
            "now_count": num(sale_now[key].get(COUNT)), "then_count": num(sale_then[key].get(COUNT)),
            "now_stores": num(store_now[key].get(STORES)), "then_stores": num(store_then[key].get(STORES)),
        }
        for name, value in values.items():
            bucket[name] += value
        a, c, s = pct(values["now_amount"], values["then_amount"]), pct(values["now_count"], values["then_count"]), pct(values["now_stores"], values["then_stores"])
        if None not in (a, c, s) and a >= .25 and c >= .20 and s >= .10:
            bucket["up"] += 1
        elif None not in (a, c, s) and a <= -.25 and c <= -.20 and s <= -.10:
            bucket["down"] += 1
    summary = []
    for industry, item in totals.items():
        a, c, s = pct(item["now_amount"], item["then_amount"]), pct(item["now_count"], item["then_count"]), pct(item["now_stores"], item["then_stores"])
        if None in (a, c, s) or item["then_amount"] <= 0:
            continue
        if a >= .10 and c >= .10 and s >= .03:
            direction = "서울 합계 동반 증가"
        elif a <= -.10 and c <= -.10 and s <= -.03:
            direction = "서울 합계 동반 감소"
        else:
            direction = "합계 엇갈림"
        item.update({"industry": industry, "amount_change": a, "count_change": c, "store_change": s, "direction": direction})
        summary.append(item)
    priority = [row for row in summary if row["direction"] != "합계 엇갈림" and max(row["up"], row["down"]) >= 5]
    priority.sort(key=lambda row: row["then_amount"], reverse=True)
    split = [row for row in summary if row["up"] >= 5 and row["down"] >= 5]
    split.sort(key=lambda row: row["then_amount"], reverse=True)
    lines = ["서울 구조 레이더 — 상권 가중 합계 검증 v3", "=" * 45, f"원본: {raw_path.name}", f"비교: {current} 대 {previous} (전년 동분기)",
             "", "해석 규칙", "- 상권 수가 아니라 업종별 서울 합계(매출·결제·점포)를 비교합니다.", "- 합계 방향과 상권 신호 방향이 함께 있을 때만 S1 우선 관찰입니다.", "",
             f"합계와 상권 신호가 함께 있는 우선 관찰: {len(priority)}건"]
    if not priority:
        lines.append("- 없음. 현재 데이터만으로는 서울 전체의 우세 방향을 말할 수 없습니다.")
    for row in priority[:20]:
        lines.append(f"- {row['industry']} / {row['direction']} / 합계: 매출 {row['amount_change']:+.1%}, 결제 {row['count_change']:+.1%}, 점포 {row['store_change']:+.1%} / 강한 증가 상권 {row['up']}개, 감소 상권 {row['down']}개")
    lines.extend(["", f"지역 분화 재확인(기사 후보 아님): {len(split)}건"])
    for row in split[:20]:
        lines.append(f"- {row['industry']} / 합계 방향: {row['direction']} (매출 {row['amount_change']:+.1%}, 결제 {row['count_change']:+.1%}, 점포 {row['store_change']:+.1%}) / 증가 {row['up']}개, 감소 {row['down']}개")
    lines.extend(["", "주의", "- 추정매출과 결제 건수는 카드 포착 범위 및 업종 분류의 영향을 받습니다.", "- 이 결과는 원인·시민 경험·기사 가치를 증명하지 않습니다. 관심 레이더 또는 현장 검증이 있어야 S2입니다."])
    out = ROOT / "output" / "area" / "analysis"
    out.mkdir(parents=True, exist_ok=True)
    target = out / (raw_path.stem + f"-weighted-v3-{current}.txt")
    if target.exists():
        print("이미 분석 파일이 있습니다: " + str(target))
        return 1
    target.write_text("\n".join(lines), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
