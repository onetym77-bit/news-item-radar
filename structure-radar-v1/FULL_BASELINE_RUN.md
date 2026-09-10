# 상권 전체 기준선 수집

이 작업은 첫 1회(또는 서울시 데이터가 새 분기를 공개했을 때)에만 실행한다. 약 8만여 행을 1,000행 단위로 나누어 가져오므로 일반 수집보다 시간이 길 수 있다.

```powershell
Set-Location -LiteralPath 'C:\Users\SKB.4154\Documents\ChatGPT\기획기사 아이템 서칭\structure-radar-v1'
py .\collector-commercial-v1.2-full-http.py
```

성공 기준:

- `stores_by_district` 수집 행과 API 보고 행이 같음
- `sales_by_district` 수집 행과 API 보고 행이 같음
- `주의: 안전 상한` 문구가 없음

작업 중 창을 닫지 않는다. 오류가 나면 생성된 텍스트 보고서의 오류 문구만 공유한다.
