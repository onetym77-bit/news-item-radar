"""아카이브된 기존 행정동 생활인구 ZIP의 필드와 기간을 진단한다.

장기 추세용 입력만 다룬다. 2026년 8월 이후 250m 격자 계열과 섞지 않는다.
"""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input" / "legacy_living_population"
OUTPUT = ROOT / "output" / "legacy_living_population"


def decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeError("지원하지 않는 인코딩")


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "legacy_living_population_profile.txt"
    files = sorted(INPUT.glob("LOCAL_PEOPLE_DONG_*.zip"))
    lines = [
        "# 서울 구조 레이더 — 기존 행정동 생활인구 장기추세 원본 진단",
        "",
        "원칙: 2017~2026-07 기존 계열 안에서만 장기 비교한다.",
        "새 250m 격자 계열과 수치를 이어 붙이지 않는다.",
        "",
    ]
    if not files:
        lines += [
            "입력 파일 없음",
            f"아래 폴더에 ZIP을 넣어 주세요: {INPUT}",
            "권장 파일: LOCAL_PEOPLE_DONG_201707.zip, LOCAL_PEOPLE_DONG_202107.zip, LOCAL_PEOPLE_DONG_202607.zip",
        ]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0

    for path in files:
        lines += [f"## {path.name}", ""]
        try:
            with zipfile.ZipFile(path) as archive:
                members = sorted(m for m in archive.namelist() if m.lower().endswith(".csv"))
                lines.append(f"CSV 수: {len(members)} / 첫 파일: {members[0] if members else '없음'}")
                if not members:
                    lines += ["오류: CSV를 찾지 못했습니다.", ""]
                    continue
                text, encoding = decode(archive.read(members[0]))
                reader = csv.DictReader(io.StringIO(text))
                fields = reader.fieldnames or []
                first = next(reader, None)
                lines += [
                    f"인코딩: {encoding}",
                    f"필드({len(fields)}): " + ", ".join(fields),
                    "첫 행 예시: " + (" | ".join(f"{key}={first.get(key, '')}" for key in fields[:18]) if first else "없음"),
                    "",
                ]
        except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
            lines += [f"오류: {exc}", ""]
    lines += [
        "다음 단계",
        "- 2017·2021·2026년 7월의 공통 필드·행정동 코드가 확인되면 5년·9년 추세를 별도 계산합니다.",
        "- 장기 추세는 자치구 단위에서 우선 집계하며, 작은 행정동 단위 해석은 현장 검증 전에는 쓰지 않습니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
