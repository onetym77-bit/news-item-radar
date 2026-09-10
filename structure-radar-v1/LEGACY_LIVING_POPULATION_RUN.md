# 장기 생활인구 추세: 1단계 실행

## 목적

기존 행정동 생활인구 계열로 자치구의 5년·9년 변화를 본다. 이 계열은 2026년 7월까지이며, 새 250m 격자 기반 자료와 합산하거나 직접 증감률을 계산하지 않는다.

## 준비

서울 열린데이터광장 기존 `행정동 단위 서울 생활인구(내국인)` 아카이브에서 아래 ZIP을 내려받는다.

- `LOCAL_PEOPLE_DONG_201707.zip` — 9년 기준점
- `LOCAL_PEOPLE_DONG_202107.zip` — 5년 기준점
- `LOCAL_PEOPLE_DONG_202607.zip` — 최신 기준점

다음 폴더를 만들고, 세 파일을 넣는다.

```powershell
New-Item -ItemType Directory -Force ".\input\legacy_living_population"
```

## 실행

```powershell
py .\profile_legacy_living_population_zip.py
```

공유할 결과 파일:

```text
output\legacy_living_population\legacy_living_population_profile.txt
```

## 편집 원칙

- 5년 변화는 구조 신호, 9년 변화는 배경선이다.
- 인구 추정치의 장기 변화는 원인을 뜻하지 않는다.
- 상권·교통·현장 관찰이 붙기 전에는 기사 후보로 만들지 않는다.
