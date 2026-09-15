# 다중 에이전트 그림자 실행 v1

이 폴더는 기존 일일 브리핑을 대체하지 않고, 같은 입력자료로 다중 에이전트 결과를 비교하기 위한 시험 영역입니다.

## 1단계: 공동 입력 스냅숏

`freeze_input.py`는 `source-scout-v1/output/daily_feed_latest.json`을 읽어 다음을 포함한 불변 입력 스냅숏을 만듭니다.

- 원자료 전체의 SHA-256 지문
- 수집 시각, GitHub 실행 ID, 코드 SHA
- 후보 레인별 건수
- 기존 시스템과 그림자 시스템이 공유할 전체 피드
- 공식 장부와 브리핑 변경을 금지하는 계약

스냅숏은 GitHub Actions의 별도 artifact로만 보관합니다. 이 단계에서는 모델을 호출하거나 공식 브리핑·기사 장부를 수정하지 않습니다.

## 실행

```bash
python multi-agent-shadow-v1/freeze_input.py \
  --feed source-scout-v1/output/daily_feed_latest.json \
  --output shadow_input_latest.json \
  --run-id 12345 \
  --code-sha abcdef
python multi-agent-shadow-v1/freeze_input.py \
  --output shadow_input_latest.json \
  --verify
```

다음 단계에서는 발굴·편집 평가·반론 에이전트가 이 스냅숏만 읽도록 공통 출력 스키마와 오케스트레이터를 연결합니다.
