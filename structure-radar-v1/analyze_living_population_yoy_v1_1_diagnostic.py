"""v1 생활인구 전년 비교의 진단판.

기존 분석기와 같은 산식으로 계산하되, 신호가 0건일 때도 기준 미달 상위 변화를 보여준다.
원본 데이터, 기존 분석기, API 키를 변경하지 않는다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASE = ROOT / "analyze_living_population_yoy_v1.py"
OUTPUT = ROOT / "output" / "living_population"


def load_base():
    spec = importlib.util.spec_from_file_location("living_base", BASE)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> int:
    base = load_base()
    files = sorted(base.INPUT.glob("250_LOCAL_RESD_ADMDONG_*.zip"))
    by_month = {path.stem[-6:]: path for path in files}
    current, previous = by_month.get("202607"), by_month.get("202507")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "living_population_yoy_diagnostic.txt"
    if not current or not previous:
        report.write_text(
            "# 서울 구조 레이더 — 생활인구 전년 동월 진단\n\n"
            "202507·202607 ZIP을 모두 찾지 못했습니다.\n",
            encoding="utf-8",
        )
        print(f"완료: {report}")
        return 0

    current_data = base.read_month(current)
    previous_data = base.read_month(previous)
    rows = []
    for district in base.DISTRICTS.values():
        for band in base.TIME_BANDS:
            now = base.comparable_average(current_data[district][band])
            then = base.comparable_average(previous_data[district][band])
            if now is None or then is None:
                continue
            change = base.pct(now, then)
            # Number of distinct dates is shown; weekday balancing happens inside the main calculation.
            current_days = len({day for days in current_data[district][band].values() for day in days})
            previous_days = len({day for days in previous_data[district][band].values() for day in days})
            rows.append((abs(change), district, band, now, then, change, current_days, previous_days))
    rows.sort(reverse=True)
    signal_count = sum(abs(change) >= 8 and then >= 20000 for _, _, _, _, then, change, _, _ in rows)
    lines = [
        "# 서울 구조 레이더 — 생활인구 전년 동월 진단 v1.1",
        "",
        f"비교: {current.name} 대 {previous.name}",
        f"관측 신호 기준 충족: {signal_count}건 (±8%, 전년 시간대 일평균 2만명 이상)",
        "",
        "기준 미달을 포함한 변화폭 상위 15건",
        "- 아래 항목은 기사 후보가 아니며, 기준을 조정하기 위한 진단값입니다.",
        "",
    ]
    for _, district, band, now, then, change, now_days, then_days in rows[:15]:
        lines.append(
            f"- {district} · {band} / {change:+.2f}% "
            f"({then:,.0f} → {now:,.0f}; 비교 일수 {then_days}일→{now_days}일)"
        )
    lines += [
        "",
        "해석",
        "- 상위 변화도 ±8%에 못 미치면, 이번 월 비교에서 생활인구는 상권 신호를 강화할 근거가 아닙니다.",
        "- 한 달 비교의 작은 차이는 날씨·휴일·행사·표본 변동일 수 있어 기준을 낮춰 기사화하지 않습니다.",
        "- 이 경우 구조 레이더는 상권 데이터 단독 S1을 유지하고, 다음 유효한 외부 신호를 기다립니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
