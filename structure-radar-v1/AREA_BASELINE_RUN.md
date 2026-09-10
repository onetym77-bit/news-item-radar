# 상권 단위 기준선 수집

```powershell
Set-Location -LiteralPath 'C:\Users\SKB.4154\Documents\ChatGPT\기획기사 아이템 서칭\structure-radar-v1'
py .\collector-commercial-area-v1.py
```

이 수집기는 상권 단위 점포·추정매출 데이터를 2026년 1분기와 2025년 1분기로 한정해 내려받는다. HTTP 전용 서울 OpenAPI 호출이므로 전용 키 사용 원칙은 `HTTP_ENDPOINT_NOTICE.md`를 따른다.

완료 후 `output\area\report`의 텍스트 보고서를 확인한다. 각 원천·분기에서 API 행과 수집 행이 같고 상한 경고가 없어야 다음 분석으로 진행한다.
