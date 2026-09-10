"""장기 생활인구 입력을 확인한 뒤 기존 구조 진단을 실행한다."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input" / "legacy_living_population"
OUTPUT = ROOT / "output" / "legacy_living_population"
REQUIRED = (
    "LOCAL_PEOPLE_DONG_2017_하반기.zip",
    "LOCAL_PEOPLE_DONG_2021_하반기.zip",
    "LOCAL_PEOPLE_DONG_202607.zip",
)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    missing = [name for name in REQUIRED if not (INPUT / name).exists()]
    if missing:
        report = OUTPUT / "legacy_living_population_profile.txt"
        report.write_text(
            "# 서울 구조 레이더 — 기존 행정동 생활인구 장기추세 원본 진단\n\n"
            "입력 파일이 부족합니다. 아래 폴더에 다음 파일을 넣어 주세요.\n\n"
            f"폴더: {INPUT}\n\n"
            "필수 파일:\n"
            "- LOCAL_PEOPLE_DONG_2017_하반기.zip\n"
            "- LOCAL_PEOPLE_DONG_2021_하반기.zip\n"
            "- LOCAL_PEOPLE_DONG_202607.zip\n\n"
            "2022년까지는 반기 ZIP, 2023년부터는 월별 ZIP입니다.\n"
            "이후 분석은 각 ZIP 안의 7월 일별 CSV만 골라 비교합니다.\n\n"
            "현재 없는 파일:\n- " + "\n- ".join(missing) + "\n",
            encoding="utf-8",
        )
        print(f"완료: {report}")
        return 0
    runpy.run_path(str(ROOT / "profile_legacy_living_population_zip.py"), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
