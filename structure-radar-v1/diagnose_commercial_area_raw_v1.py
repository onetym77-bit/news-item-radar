"""기존 상권 단위 원본 JSON에서 실제 필드 구조를 TXT로 진단한다."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output" / "nightlife_check"


def walk_lists(value):
    if isinstance(value, list):
        if value and isinstance(value[0], dict):
            yield value
        for item in value:
            yield from walk_lists(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from walk_lists(item)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "commercial_area_raw_diagnostic.txt"
    matches = []
    for path in ROOT.rglob("*.json"):
        if "output" not in path.parts:
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        for rows in walk_lists(data):
            fields = set(rows[0])
            if "STDR_YYQU_CD" in fields and "SVC_INDUTY_CD_NM" in fields and any("TRDAR" in field for field in fields):
                matches.append((path, rows, fields))
    lines = ["# 서울 구조 레이더 — 상권 단위 원본 구조 진단", "", f"발견 테이블: {len(matches)}개", ""]
    for path, rows, fields in matches:
        first = rows[0]
        lines += [
            f"## {path.name}",
            f"행 수: {len(rows)}",
            "필드: " + ", ".join(sorted(fields)),
            "첫 행: " + " | ".join(f"{key}={first.get(key, '')}" for key in sorted(fields)[:30]),
            "",
        ]
    if not matches:
        lines += ["상권 단위 필드를 가진 JSON을 찾지 못했습니다.", "원본 수집 파일의 위치 또는 파일명을 확인해 주세요."]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
