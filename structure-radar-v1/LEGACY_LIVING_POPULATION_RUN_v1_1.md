# 장기 생활인구 추세: 입력 파일 정정

## 반기·월별 혼재 처리

기존 행정동 생활인구 파일은 2022년까지 반기 단위이며, 2023년부터 월 단위다. 장기 비교 때 반기 평균과 월 평균을 직접 비교하지 않는다. 각 ZIP 안의 **7월 일별 CSV만** 추출해 같은 달을 비교한다.

## 준비 파일

`input/legacy_living_population` 폴더에 아래 세 파일을 넣는다.

- `LOCAL_PEOPLE_DONG_2017_하반기.zip`
- `LOCAL_PEOPLE_DONG_2021_하반기.zip`
- `LOCAL_PEOPLE_DONG_202607.zip`

## 지금 실행할 진단

기존 진단 스크립트는 반기 파일도 읽을 수 있다. 파일 내부의 첫 CSV와 필드를 확인한다.

```powershell
py .\profile_legacy_living_population_zip.py
```

결과:

```text
output\legacy_living_population\legacy_living_population_profile.txt
```

다음 분석기에서는 파일명과 CSV의 일자 필드를 함께 써서 2017년 7월·2021년 7월·2026년 7월만 비교한다.
