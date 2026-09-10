# 생활인구 교차 단계

## 왜 새 자료를 쓰는가

기존 `행정동 단위 서울 생활인구(내국인)`은 2026년 7월 31일 이후 제공 방식이 250m 격자 기반으로 바뀌었다. 구조 레이더는 종료·전환된 자료에 의존하지 않고, 새 `[내국인] 행정동별 서울 생활인구(250m)`를 기준으로 삼는다.

- 공식 데이터셋: <https://data.seoul.go.kr/dataList/OA-23016/S/1/datasetView.do>
- 갱신: 매일 1회. Sheet/OpenAPI는 최근 2개월만 제공된다.
- 월별 ZIP은 장기 비교에 쓸 수 있다.

## 첫 실행 준비

1. 위 공식 페이지에서 `250_LOCAL_RESD_ADMDONG_202607.zip`을 내려받는다.
2. 다음 폴더를 만들고 ZIP을 이동한다. ZIP의 이름은 바꾸지 않는다.

```powershell
New-Item -ItemType Directory -Force ".\input\living_population"
```

3. 같은 터미널에서 구조를 진단한다.

```powershell
py .\profile_living_population_zip.py
```

4. 아래 TXT 파일의 내용을 공유한다.

```text
output\living_population\living_population_profile.txt
```

## 그 다음 분석의 원칙

- 첫 교차는 상권과 직접 억지로 맞추지 않고 **자치구 단위**에서 한다.
- 월별·요일별·시간대별 계절성을 분리한다.
- 생활인구와 상권 지표가 함께 움직여도 ‘원인’으로 단정하지 않는다.
- 생활인구 증가 지역은 현장 관찰·독립 관심 신호 중 하나를 통과해야 S2가 된다.
