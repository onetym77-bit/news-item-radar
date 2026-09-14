# 데일리 브리핑 v5

v5는 기존 기사 게이트를 낮추지 않고 브리핑을 세 구역으로 나눈다.

- A: 검증을 마친 S2·S3 편집 제안
- B: 오늘 4시간 안에 결론을 낼 S0·S1 검증 과제
- C: 새 질문 원석과 후속 관찰

`build_briefing.py`는 ITEM_LEDGER와 QUESTION_QUALITY_AUDIT를 읽어 우선순위, 기한 초과, 누락된 검증 필드를 표시한다. 이 프로그램은 실제 웹 검색이나 현장 확인을 수행하지 않으므로 미수행 검증을 완료로 표시하지 않는다.

## 실행

```text
python -X utf8 daily-briefing-v5/build_briefing.py
```

기본 산출물은 다음과 같다.

- `daily-briefing-v5/output/briefing_latest.md`
- `daily-briefing-v5/output/history/briefing_YYYY-MM-DD.md`
- `agent-system-v1/VERIFICATION_QUEUE.csv`

GitHub Actions의 `daily-briefing.yml`이 매일 09:30 KST에 실행하며 수동 실행도 지원한다.
