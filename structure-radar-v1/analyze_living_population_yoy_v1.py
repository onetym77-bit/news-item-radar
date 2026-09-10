"""행정동 생활인구 월별 ZIP 두 개를 자치구·시간대별로 전년 비교한다.

이 스크립트는 생활인구 관측만 한다. 상권·관심 신호·정책자료를 섞지 않으며,
출력은 회사 환경에서 열 수 있는 TXT 파일이다.
"""

from __future__ import annotations

import csv
import io
import statistics
import sys
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input" / "living_population"
OUTPUT = ROOT / "output" / "living_population"

# 법정·행정동 코드는 앞 다섯 자리로 자치구를 식별한다.
DISTRICTS = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}
TIME_BANDS = {
    "주간(09~17시)": range(9, 18),
    "저녁(18~22시)": range(18, 23),
    "심야·이른아침(00~05시)": range(0, 6),
}


def read_month(path: Path):
    # district -> band -> weekday -> day -> sum of all administrative-dong population
    values = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float))))
    with zipfile.ZipFile(path) as archive:
        members = sorted(m for m in archive.namelist() if m.lower().endswith(".csv"))
        if not members:
            raise ValueError("ZIP 안에 CSV 파일이 없습니다.")
        for member in members:
            raw = archive.read(member)
            text = None
            for encoding in ("utf-8-sig", "cp949", "euc-kr"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if text is None:
                raise ValueError(f"인코딩을 읽을 수 없습니다: {member}")
            for row in csv.DictReader(io.StringIO(text)):
                try:
                    day = str(row["일자"])
                    hour = int(float(str(row["시간"])))
                    district = DISTRICTS.get(str(row["행정동코드"])[:5])
                    population = float(str(row["생활인구합계"]).replace(",", ""))
                    weekday = date(int(day[:4]), int(day[4:6]), int(day[6:8])).weekday()
                except (KeyError, ValueError, TypeError):
                    continue
                if not district:
                    continue
                for band, hours in TIME_BANDS.items():
                    if hour in hours:
                        values[district][band][weekday][day] += population
    return values


def comparable_average(per_weekday):
    # Month calendars differ. Each weekday's daily sums are averaged first, then weekdays receive equal weight.
    weekday_means = [statistics.fmean(days.values()) for days in per_weekday.values() if days]
    return statistics.fmean(weekday_means) if weekday_means else None


def pct(current, previous):
    return None if not previous else (current / previous - 1) * 100


def main() -> int:
    files = sorted(INPUT.glob("250_LOCAL_RESD_ADMDONG_*.zip"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "living_population_yoy.txt"
    if len(files) < 2:
        report.write_text(
            "# 서울 구조 레이더 — 생활인구 전년 비교\n\n"
            "입력 파일이 부족합니다. 아래 두 파일을 input\\living_population 폴더에 넣어 주세요.\n"
            "- 250_LOCAL_RESD_ADMDONG_202507.zip\n"
            "- 250_LOCAL_RESD_ADMDONG_202607.zip\n",
            encoding="utf-8",
        )
        print(f"완료: {report}")
        return 0

    by_month = {path.stem[-6:]: path for path in files}
    current = by_month.get("202607")
    previous = by_month.get("202507")
    if not current or not previous:
        report.write_text(
            "# 서울 구조 레이더 — 생활인구 전년 비교\n\n"
            "현재는 2026년 7월과 2025년 7월 ZIP만 비교하도록 설정돼 있습니다.\n"
            f"발견한 파일: {', '.join(p.name for p in files)}\n",
            encoding="utf-8",
        )
        print(f"완료: {report}")
        return 0

    current_data = read_month(current)
    previous_data = read_month(previous)
    observations = []
    for district in DISTRICTS.values():
        for band in TIME_BANDS:
            now = comparable_average(current_data[district][band])
            then = comparable_average(previous_data[district][band])
            if now is None or then is None:
                continue
            change = pct(now, then)
            observations.append((abs(change), district, band, now, then, change))

    # This threshold controls report length only. It is intentionally lower than a story threshold.
    signals = [row for row in observations if abs(row[5]) >= 8 and row[4] >= 20000]
    signals.sort(reverse=True)
    lines = [
        "# 서울 구조 레이더 — 생활인구 전년 동월 관측 v1",
        "",
        f"비교: {current.name} 대 {previous.name}",
        "집계: 같은 요일별 일평균을 먼저 구한 뒤, 요일 평균을 같은 비중으로 합산",
        "시간대: 주간(09~17시), 저녁(18~22시), 심야·이른아침(00~05시)",
        "",
        "판정 원칙",
        "- 생활인구 변화 ±8%, 전년 시간대 일평균 2만명 이상을 관측 신호로 기록합니다.",
        "- 이는 공간에서의 사람 수 변화일 뿐 소비·원인·기사 가치를 뜻하지 않습니다.",
        "- 상권의 매출·결제·점포 변화 또는 독립 관심 신호가 하나 더 있어야 S2 검토입니다.",
        "",
        f"관측 신호: {len(signals)}건",
        "",
    ]
    if signals:
        for _, district, band, now, then, change in signals:
            direction = "증가" if change > 0 else "감소"
            lines.append(
                f"- {district} · {band} / {direction} {change:+.1f}% "
                f"(일평균 {then:,.0f}명 → {now:,.0f}명)"
            )
    else:
        lines.append("- 기준을 충족한 관측 신호가 없습니다.")
    lines += [
        "",
        "다음 편집 단계",
        "- 이 목록에서 상권 전년 동분기 변화가 같은 방향인 자치구×업종만 교차 검토합니다.",
        "- 휴일·폭염·행사·행정동 경계 변경 가능성을 먼저 확인합니다.",
        "- 교차 결과도 현장 관찰 또는 독립 관심 신호 전에는 기사 후보가 아닙니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
