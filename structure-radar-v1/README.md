# 상권 구조 기준선 수집 — 실행 안내

`SEOUL_OPEN_API_KEY`가 시스템 환경변수에 등록된 새 PowerShell 창에서 실행한다.

```powershell
Set-Location -LiteralPath 'C:\Users\SKB.4154\Documents\ChatGPT\기획기사 아이템 서칭\structure-radar-v1'
py .\collector-commercial-v1.py
```

성공하면 아래 폴더에 새 텍스트 보고서가 생성된다.

```text
output\commercial\report
```

이 단계는 기사 추천을 하지 않는다. API가 어떤 기준기간과 필드를 반환하는지 확인하고, 다음 분기 비교에 필요한 기준선을 새 파일로 보관하는 단계다.

오류가 나면 결과 `.txt`의 오류 문구만 공유한다. 키는 공유하지 않는다.
