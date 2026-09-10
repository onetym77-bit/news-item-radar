"""상권 단위 매출 원본의 식음료 서비스업 코드값을 확인한다."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAPPING = ROOT / "output" / "commercial_area_mapping" / "commercial_area_mapping.json"
TREND = ROOT / "output" / "commercial_area_trend" / "commercial_area_trend.json"
OUTPUT = ROOT / "output" / "nightlife_check"

def norm(value):
    text = str(value).strip()
    return text[:-2] if text.endswith(".0") else text

def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "food_service_code_trace.txt"
    mapping = json.loads(MAPPING.read_text(encoding="utf-8")).get("rows", [])
    sales = json.loads(TREND.read_text(encoding="utf-8")).get("datasets", {}).get("sales", {}).get("20261", [])
    lookup = {norm(row.get("TRDAR_CD")): str(row.get("SIGNGU_CD_NM")) for row in mapping}
    targets = {"강북구", "도봉구", "노원구"}
    joined = [row for row in sales if lookup.get(norm(row.get("TRDAR_CD"))) in targets]
    codes = Counter(str(row.get("SVC_INDUTY_CD")) for row in joined)
    names = Counter(str(row.get("SVC_INDUTY_CD_NM")) for row in joined)
    cs100 = [row for row in joined if str(row.get("SVC_INDUTY_CD", "")).startswith("CS100")]
    lines = [
        "# 서울 구조 레이더 — 북부 3구 식음료 코드 추적",
        "",
        f"20261 매출 원본에서 북부 3구로 결합된 전체 업종 행: {len(joined)}",
        f"코드 CS100으로 시작하는 행: {len(cs100)}",
        "",
        "상위 서비스업 코드:",
    ]
    lines += [f"- {code}: {count}행" for code, count in codes.most_common(25)]
    lines += ["", "CS100 해당 업종명:"]
    lines += [f"- {name}: {count}행" for name, count in Counter(str(row.get("SVC_INDUTY_CD_NM")) for row in cs100).most_common(30)]
    lines += ["", "북부 3구 결합 첫 행:"]
    for row in joined[:5]:
        lines.append(f"- 코드={row.get('TRDAR_CD')} / 업종코드={row.get('SVC_INDUTY_CD')} / 업종명={row.get('SVC_INDUTY_CD_NM')}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
