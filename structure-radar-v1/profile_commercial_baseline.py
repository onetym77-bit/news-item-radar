"""Render schema and period coverage from the newest commercial raw snapshot."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def newest_raw() -> Path:
    files = sorted((ROOT / "output" / "commercial" / "raw").glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("상권 raw 스냅샷이 없습니다. 전체 기준선 수집을 먼저 실행하세요.")
    return files[0]


def profile(source: dict) -> list[str]:
    label = source.get("label", "unknown")
    rows = source.get("rows", [])
    lines = [f"[{label}] 상태: {source.get('status')}", f"- 행 수: {len(rows)}"]
    if not rows:
        return lines
    fields = sorted(rows[0])
    period_field = next((field for field in fields if field == "STDR_YYQU_CD"), None)
    if period_field:
        periods = Counter(str(row.get(period_field, "")) for row in rows)
        lines.append("- 기준분기(행 수): " + ", ".join(f"{period}={count}" for period, count in sorted(periods.items())))
    id_fields = [field for field in fields if field.endswith("_CD") or field.endswith("_NM")]
    measure_fields = [field for field in fields if field.endswith("_AMT") or field.endswith("_CO") or field.endswith("_RT")]
    lines.append("- 식별·분류 필드: " + ", ".join(id_fields))
    lines.append("- 수치 후보 필드: " + ", ".join(measure_fields))
    return lines


def main() -> int:
    raw_path = newest_raw()
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    lines = ["서울 구조 레이더 — 상권 기준선 프로파일", "=" * 40,
             f"원본 스냅샷: {raw_path.name}", f"수집 시각: {payload.get('collected_at', '')}", ""]
    for source in payload.get("sources", []):
        lines.extend(profile(source))
        lines.append("")
    lines.extend(["다음 단계", "- 최신 분기와 직전·전년 동분기의 교집합 행만 비교합니다.", "- 매출·점포 변화는 기사 결론이 아니라 관찰 신호로만 사용합니다."])
    target_dir = ROOT / "output" / "commercial" / "profile"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (raw_path.stem + "-profile.txt")
    if target.exists():
        print("이미 프로파일이 있습니다: " + str(target))
        return 1
    target.write_text("\n".join(lines), encoding="utf-8")
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
