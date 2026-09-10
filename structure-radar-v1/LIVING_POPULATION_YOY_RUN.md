# 생활인구 전년 동월 관측 실행

## 준비 파일

`input/living_population` 폴더에 아래 두 ZIP이 있어야 한다.

- `250_LOCAL_RESD_ADMDONG_202507.zip`
- `250_LOCAL_RESD_ADMDONG_202607.zip`

두 파일은 서울 열린데이터광장의 `[내국인] 행정동별 서울 생활인구(250m)`에서 받을 수 있다.

## 실행

```powershell
py .\analyze_living_population_yoy_v1.py
```

결과 파일:

```text
output\living_population\living_population_yoy.txt
```

## 해석

이 보고서는 자치구별 시간대 인구의 **관측 변화**다. 소비 변화의 원인, 시민의 문제, 취재 주제를 뜻하지 않는다. 상권 변화와 독립 관심 신호 중 하나를 더 통과한 항목만 다음 단계에 올린다.
