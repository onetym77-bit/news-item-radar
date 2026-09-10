"""2017·2021·2026년 7월 기존 생활인구 계열의 장기 추세를 관측한다.

원칙: 기존 행정동 계열 안에서만 계산한다. 기사 후보를 만들지 않는다.
"""

from __future__ import annotations

import csv
import io
import statistics
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input" / "legacy_living_population"
OUTPUT = ROOT / "output" / "legacy_living_population"
FILES = {
    2017: "LOCAL_PEOPLE_DONG_2017_하반기.zip",
    2021: "LOCAL_PEOPLE_DONG_2021_하반기.zip",
    2026: "LOCAL_PEOPLE_DONG_202607.zip",
}
DISTRICTS = {
    "11110": "종로구", "11140": "중구", "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구", "11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구", "11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구", "11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}
TIME_BANDS = {"주간(09~17시)": range(9, 18), "저녁(18~22시)": range(18, 23), "심야·이른아침(00~05시)": range(0, 6)}
YOUNG = ("남자20세부터24세생활인구수", "남자25세부터29세생활인구수", "남자30세부터34세생활인구수", "남자35세부터39세생활인구수", "여자20세부터24세생활인구수", "여자25세부터29세생활인구수", "여자30세부터34세생활인구수", "여자35세부터39세생활인구수")
SENIOR = ("남자65세부터69세생활인구수", "남자70세이상생활인구수", "여자65세부터69세생활인구수", "여자70세이상생활인구수")


def mean_by_weekday(values):
    means = [statistics.fmean(days.values()) for days in values.values() if days]
    return statistics.fmean(means) if means else None


def read_july(path: Path, year: int):
    # district -> band -> metric -> weekday -> date -> summed population
    result = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float)))))
    target = f"{year}07"
    with zipfile.ZipFile(path) as archive:
        members = [m for m in archive.namelist() if m.lower().endswith(".csv") and target in m]
        if not members:
            raise ValueError(f"{path.name} 안에 {target} CSV가 없습니다.")
        for member in members:
            raw = archive.read(member)
            text = raw.decode("utf-8-sig")
            for row in csv.DictReader(io.StringIO(text)):
                try:
                    day = str(row["기준일ID"])
                    hour = int(float(row["시간대구분"]))
                    district = DISTRICTS.get(str(row["행정동코드"])[:5])
                    total = float(row["총생활인구수"])
                    weekday = date(int(day[:4]), int(day[4:6]), int(day[6:8])).weekday()
                    young = sum(float(row[key]) for key in YOUNG)
                    senior = sum(float(row[key]) for key in SENIOR)
                except (KeyError, ValueError, TypeError):
                    continue
                if not district:
                    continue
                for band, hours in TIME_BANDS.items():
                    if hour in hours:
                        for metric, value in (("total", total), ("young", young), ("senior", senior)):
                            result[district][band][metric][weekday][day] += value
    return result


def percent(now, old):
    return None if not old else (now / old - 1) * 100


def classify(v17, v21, v26):
    a, b = percent(v21, v17), percent(v26, v21)
    if a is None or b is None:
        return "판정 불가"
    if a >= 5 and b >= 5:
        return "지속 증가"
    if a <= -5 and b <= -5:
        return "지속 감소"
    if a <= -5 and b >= 5:
        return "감소 후 회복·반전"
    if a >= 5 and b <= -5:
        return "증가 후 감소·반전"
    return "장기 보합·혼조"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    report = OUTPUT / "legacy_living_population_longterm.txt"
    missing = [name for name in FILES.values() if not (INPUT / name).exists()]
    if missing:
        report.write_text("# 서울 구조 레이더 — 생활인구 장기 추세\n\n입력 파일 부족:\n- " + "\n- ".join(missing) + "\n", encoding="utf-8")
        print(f"완료: {report}")
        return 0
    data = {year: read_july(INPUT / name, year) for year, name in FILES.items()}
    rows = []
    for district in DISTRICTS.values():
        for band in TIME_BANDS:
            values = {year: mean_by_weekday(data[year][district][band]["total"]) for year in FILES}
            if any(value is None for value in values.values()):
                continue
            senior_share = {year: mean_by_weekday(data[year][district][band]["senior"]) / values[year] * 100 for year in FILES}
            young_share = {year: mean_by_weekday(data[year][district][band]["young"]) / values[year] * 100 for year in FILES}
            rows.append({
                "district": district, "band": band, "v17": values[2017], "v21": values[2021], "v26": values[2026],
                "p17_21": percent(values[2021], values[2017]), "p21_26": percent(values[2026], values[2021]), "p17_26": percent(values[2026], values[2017]),
                "class": classify(values[2017], values[2021], values[2026]),
                "senior_pp": senior_share[2026] - senior_share[2017], "young_pp": young_share[2026] - young_share[2017],
            })
    persistent = [r for r in rows if r["class"] in ("지속 증가", "지속 감소") and abs(r["p17_26"]) >= 12]
    persistent.sort(key=lambda r: abs(r["p17_26"]), reverse=True)
    age_shift = sorted(rows, key=lambda r: abs(r["senior_pp"]), reverse=True)
    lines = [
        "# 서울 구조 레이더 — 기존 행정동 생활인구 장기 추세 v1",
        "",
        "비교: 2017년 7월 · 2021년 7월 · 2026년 7월",
        "집계: 같은 요일별 일평균을 먼저 구한 뒤, 요일 평균을 같은 비중으로 합산",
        "단위: 자치구별 시간대 생활인구(행정동 합계). 2026년은 7월 24일 기준 제공분입니다.",
        "",
        "판정 원칙",
        "- 2017→2021과 2021→2026이 각각 ±5% 이상 같은 방향일 때만 지속 변화로 분류합니다.",
        "- 2017→2026 순변화가 ±12% 이상인 지속 변화만 아래에 기록합니다.",
        "- 코로나 시기 감소 후 회복은 구조 변화가 아니라 별도 반전으로 취급합니다.",
        "",
        f"지속 변화 관측: {len(persistent)}건",
        "",
    ]
    for r in persistent:
        lines.append(
            f"- {r['district']} · {r['band']} / {r['class']} / 9년 {r['p17_26']:+.1f}% "
            f"(2017→2021 {r['p17_21']:+.1f}%, 2021→2026 {r['p21_26']:+.1f}%)"
        )
    if not persistent:
        lines.append("- 없음. 양끝 변화나 코로나 이후 반전만으로는 장기 구조 신호로 기록하지 않습니다.")
    lines += ["", "연령구성 변화 상위 10건(관찰용)", "- 65세 이상 비중의 2017→2026 변화입니다. 인구 고령화 원인이나 기사 가치를 뜻하지 않습니다.", ""]
    for r in age_shift[:10]:
        lines.append(f"- {r['district']} · {r['band']} / 65세 이상 비중 {r['senior_pp']:+.2f}%p / 20~39세 비중 {r['young_pp']:+.2f}%p")
    lines += [
        "", "다음 편집 단계",
        "- 지속 변화도 상권의 장기 경로 또는 이동·현장 신호 중 하나가 붙기 전에는 기사 후보가 아닙니다.",
        "- 자치구 총량은 공간 내부의 차이를 가릴 수 있으므로, S2 검토 시 새 250m 자료나 상권 단위로 위치를 좁힙니다.",
        "- 보고서의 ‘반전’은 코로나19, 휴일 구성, 데이터 추정 방식 변화 가능성을 먼저 점검합니다.",
    ]
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"완료: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
