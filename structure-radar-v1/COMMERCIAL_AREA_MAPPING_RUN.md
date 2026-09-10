# 상권 코드→자치구 연결표 수집

서울시 `상권영역` 공식 API의 상권 코드·자치구·행정동 연결표를 한 번 받는다.

```powershell
py .\collector_commercial_area_mapping_v1.py
```

결과:

```text
output\commercial_area_mapping\commercial_area_mapping_report.txt
```

`SEOUL_OPEN_API_KEY` 환경변수를 사용한다. API 키는 결과에 기록되지 않는다.
