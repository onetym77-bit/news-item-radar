"""서울 생활인구 월별 ZIP의 구조를 안전하게 진단한다.

입력 ZIP은 서울 열린데이터광장에서 내려받은
250_LOCAL_RESD_ADMDONG_YYYYMM.zip 형식의 [내국인] 행정동별 서울 생활인구(250m) 파일이다.
원본을 수정하거나 API 키를 사용하지 않는다. 결과는 회사 보안 정책에서 열 수 있는 TXT다.
"""

from __future__ import annotations

import csv
import io
import sys
import zipfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input" / "living_population"
OUTPUT = ROOT / "output" / "living_population"


def open_text_from_zip(archive: zipfile.ZipFile, member: str):
    raw = archive.read(member)
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return io.StringIO(raw.decode(encoding)), encoding
        except UnicodeDecodeError:
            pass
    raise UnicodeDecodeError("unknown", b"", 0, 1, "지원하지 않는 인코딩")


def choose_delimiter(header: str) -> str:
    return "\t" if header.count("\t") > header.count(",") else ","


def main() -> int:
    archives = sorted(INPUT.glob("250_LOCAL_RESD_ADMDONG_*.zip"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "living_population_profile.txt"
    lines = [
        "# 서울 구조 레이더 — 생활인구 원본 구조 진단",
        "",
        "목적: 파일 구조·시간 범위·집계 가능 단위를 확인한다.",
        "이 단계는 기사 후보나 증감 결론을 만들지 않는다.",
        "",
    ]

    if not archives:
        lines += [
            "입력 파일 없음",
            "",
            f"아래 폴더에 서울 열린데이터광장 ZIP 파일을 넣어 주세요:",
            str(INPUT),
            "",
            "필요 파일(첫 진단은 하나만으로 충분):",
            "- 250_LOCAL_RESD_ADMDONG_202607.zip",
        ]
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0

    for path in archives:
        lines += [f"## {path.name}", ""]
        try:
            with zipfile.ZipFile(path) as archive:
                members = [m for m in archive.namelist() if not m.endswith("/")]
                lines.append("압축 내부 파일: " + ", ".join(members[:10]))
                csv_members = [m for m in members if m.lower().endswith((".csv", ".txt"))]
                if not csv_members:
                    lines += ["오류: CSV 또는 TXT 파일을 찾지 못했습니다.", ""]
                    continue
                member = csv_members[0]
                text_stream, encoding = open_text_from_zip(archive, member)
                header_line = text_stream.readline().rstrip("\r\n")
                delimiter = choose_delimiter(header_line)
                fields = next(csv.reader([header_line], delimiter=delimiter))
                reader = csv.DictReader(text_stream, fieldnames=fields, delimiter=delimiter)
                sample = []
                nonempty = Counter()
                numeric = Counter()
                for row_number, row in enumerate(reader, start=1):
                    if row_number > 2000:
                        break
                    if len(sample) < 2:
                        sample.append(row)
                    for key, value in row.items():
                        value = (value or "").strip()
                        if not value:
                            continue
                        nonempty[key] += 1
                        try:
                            float(value.replace(",", ""))
                            numeric[key] += 1
                        except ValueError:
                            pass
                lines += [
                    f"원본: {member}",
                    f"인코딩: {encoding} / 구분자: {'TAB' if delimiter == chr(9) else 'comma'}",
                    f"필드({len(fields)}): " + ", ".join(fields),
                    "표본 2,000행 기준 수치형 후보: "
                    + ", ".join(
                        key for key in fields if nonempty[key] and numeric[key] / nonempty[key] >= 0.98
                    ),
                    "",
                    "첫 행 예시:",
                ]
                if sample:
                    lines += [
                        " | ".join(f"{key}={sample[0].get(key, '')}" for key in fields[:20]),
                    ]
                lines += ["", ""]
        except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
            lines += [f"오류: {exc}", ""]

    lines += [
        "다음 단계",
        "- 진단 결과의 날짜·시간·행정동·생활인구 필드를 기준으로 집계 규칙을 고정합니다.",
        "- 월별 동일 요일·시간대 비교 후, 상권의 매출·결제·점포 변화와는 자치구 단위에서 먼저 교차합니다.",
        "- 생활인구 증감 자체는 원인이나 기사 가치를 뜻하지 않습니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
