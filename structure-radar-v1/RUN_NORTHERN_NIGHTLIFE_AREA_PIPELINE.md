# 북부 생활권 야간 상권 장소 선별: 실행 순서

아래 순서대로 실행한다. 모두 기존 `SEOUL_OPEN_API_KEY` 환경변수만 쓴다.

```powershell
py .\collector_commercial_area_mapping_v1.py
py .\collector_commercial_area_trend_v1.py
```

각 보고서:

```text
output\commercial_area_mapping\commercial_area_mapping_report.txt
output\commercial_area_trend\commercial_area_trend_report.txt
```

두 보고서가 모두 `ok` 또는 수집 행 수를 표시하면, 그 다음 현장 후보 선별기를 실행한다.
