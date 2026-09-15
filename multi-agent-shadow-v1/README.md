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


## 2단계: 에이전트 공통 판정 계약

`schemas/candidate_assessment.schema.json`과 `contracts.py`는 모든 전문 에이전트의 결과를 같은 구조로 제한합니다.

- 원문 인용과 출처 ID 없는 사실 주장을 거부합니다.
- 확인된 사실과 미확인 주장을 분리합니다.
- 경쟁 가설 두 개 이상과 판별 근거를 요구합니다.
- 현재 질문 품질 게이트와 같은 6개 항목·12점 점수를 사용합니다.
- PASS는 8점 이상과 시민 손실·경쟁 가설·반증 기준의 필수 점수를 요구합니다.
- 독립 교차 근거가 없는 후보는 편집 제안 단계로 보낼 수 없습니다.
- 내부 추론문 대신 800자 이하의 공개 가능한 판단 요약만 저장합니다.

다음 단계에서는 이 계약을 사용해 발굴·편집·반론 에이전트의 모의 실행과 총괄 오케스트레이터를 구현합니다.
