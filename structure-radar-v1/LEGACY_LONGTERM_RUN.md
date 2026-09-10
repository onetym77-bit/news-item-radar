# 장기 생활인구 추세 실행

## 실행

입력 폴더에 세 ZIP이 있는 상태에서 실행한다.

```powershell
py .\analyze_legacy_living_population_longterm_v1.py
```

## 결과

```text
output\legacy_living_population\legacy_living_population_longterm.txt
```

## 읽는 법

- `지속 증가·감소`: 2017→2021과 2021→2026이 같은 방향인 관측값이다.
- `반전`: 코로나 시기와 이후 회복을 분리하기 위한 분류이며, 기사 신호가 아니다.
- 연령구성 변화: 65세 이상 또는 20~39세 비중의 변화로, 생활인구 총량 변화와 별도로 본다.
