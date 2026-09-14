# 서울 기획 아이템 발굴 시스템 v1.8 — 활성 구성

기준일: 2026-09-14

이 문서는 예약 실행과 수동 실행이 참조할 단일 활성 구성을 지정한다. 아래에 없는 초안·스냅숏·구버전 수집기는 참고 자료이며 자동 실행에 사용하지 않는다.

## 활성 구성

| 역할 | 활성 파일 |
|---|---|
| 공통 정책 | agent-system-v1/AGENT_POLICY.md |
| 질문 품질 게이트 | agent-system-v1/QUESTION_QUALITY_GATE.md |
| 질문 독창성·최소 검증 게이트 | agent-system-v1/ORIGINALITY_AND_TEST_GATE.md |
| 질문 품질 재심사 장부 | agent-system-v1/QUESTION_QUALITY_AUDIT.csv |
| 상태 장부 | agent-system-v1/ITEM_LEDGER.csv |\n| 후속검증 대기열 | agent-system-v1/VERIFICATION_QUEUE.csv |
| 편집자 결정 | agent-system-v1/EDITOR_FEEDBACK.md |
| 실행 계측 | agent-system-v1/RUN_METRICS_TEMPLATE.md |
| 출처군·독립성 | agent-system-v1/SOURCE_FAMILY_REGISTRY.md |
| 운영 소스 역할 | source-scout-v1/SOURCE_ROLE_REGISTRY.md |
| 자치구의회 25곳 연결 등록(수동 점검, 핵심소스 승인 전) | district-council-pilot/sources_25.json |
| 자치구의회 연결 점검기 | district-council-pilot/collect_pilot.py |
| 비회기 보완소스 시험안(미편입) | district-council-pilot/OFF_SESSION_SOURCE_PLAN.md |
| 역할 분리형 신규 소스 수집 | source-scout-v1/collect_daily_feed.py |
| 신규 소스 사람 판정 대기열 | source-scout-v1/HUMAN_REVIEW_QUEUE.csv |
| 7일 정밀도 평가 | source-scout-v1/evaluate_human_review.py |
| 관심 신호 설계(v2.3) | interest-radar-v2/DESIGN.md |
| 관심 신호 설정 | interest-radar-v2/config/editorial_lenses.json |
| API 수집기(v2.3, 예약 호환 파일명 유지) | interest-radar-v2/collect_source_material_v2_1.py |
| 브리핑 핵심 지침 | briefing-v3.0-draft/SKILL.md |
| 시장 우선 발견 | briefing-v3.0-draft/MARKET_FIRST_DISCOVERY.md |
| 편집 매력도 | briefing-v3.0-draft/EDITORIAL_ATTRACTIVENESS.md |
| 모델 운영 | briefing-v3.0-draft/RUNBOOK.md |
| 편집 게이트 | daily-briefing-v5/EDITORIAL_GATE.md |
| 브리핑 형식 | daily-briefing-v5/OUTPUT_TEMPLATE.md |
| 자동 검증 | agent-system-v1/validate_discovery_system.py |

## 예약 흐름

1. 관심 레이더: 매일 08:00, 12:00, 17:30 KST
2. 역할 분리형 신규 소스 입력과 일일 브리핑: 매일 09:30 KST
3. 주간 감사: 매주 월요일 09:00 KST

예약 작업은 `D:\Codex-Data\.codex\automations`의 Codex cron으로 운영한다. Windows 작업 스케줄러를 별도 실행기로 사용하지 않는다.

## 판정 원칙

- 사업명·정책 목적만으로 피해를 추정하지 않는다. 구체적인 문제 징후 또는 분해 가능한 구조 자료라는 근거 앵커를 통과한 원석만 질문 품질을 평가한다.
- 진입 조건을 통과한 원석은 질문 품질 6개 항목을 12점으로 평가하며, 8점 이상과 필수 항목을 충족해야 질문 품질 PASS다.
- 품질 PASS 뒤 출처 프레임과 편집적 추가를 분리한다. 독창성 PASS와 24시간 이내 최소 판정 실험이 있어야 우선 검증한다.
- 우선 검증에서는 시민 손실 근거와 구조 가설을 약화할 반대 근거를 모두 찾는다.
- 공공·공공연구 출발 원석이 60%를 넘거나 우선 검증이 한 계보에 몰리면 비공공 경로 보정 탐색을 한 차례 수행한다.
- 질문 게이트를 통과한 원석과 기사 게이트를 통과한 후보가 0건인 것은 각각 정상적인 결과다.
- 공식 발표·통계·공시도 분해·비교 가능한 현상이라면 질문 생성의 출발점으로 사용할 수 있다.
- 질문 게이트와 기사 게이트를 분리하며 검증 전 가설은 최종 기사 후보로 표시하지 않는다.\n- 브리핑은 A 확정 제안(S2·S3), B 당일 검증(S0·S1 질문 PASS), C 질문 원석·후속 관찰로 분리한다.
- 각 PASS 원석은 중심 질문 1개, 시민 손실 가설, 경쟁 가설 2개 이상, 기사 전환·축소·폐기 판정선을 기록한다.
- 출처군별 할당량 대신 주거·노동·돌봄·교육·교통·생활물가·디지털 권리·안전·지역경제 의제를 우선 탐색한다.
- 행사·공연·팝업·티켓·단일 예약 신호는 자동 제외하지 않되 일정·가격·이용 팁 이상의 분해·비교·책임 질문이 없으면 질문 게이트에서 제외한다.
- 탐색 작업량 미달은 별도의 탐색 수행 판정에서 숨기지 않는다.
- S2 승격에는 독립 근거군 두 개 이상과 실제로 관찰되거나 당사자가 진술한 시민 행동 신호가 필요하다.
- 계획된 현장 장면은 근거가 아니며 취재 예정으로 표시한다.
- 같은 원자료를 재인용한 기사들은 하나의 근거군으로 계산한다.
- 유튜브는 개별 영상의 조회수가 아니라 최근 30일의 반복 현상 군집을 발견한다. 생활정보·설명, 언론 재유통, 분류 대기 영상은 독립 시민 신호로 세지 않는다.
- 서울시의회와 응답소의 자동 통과 단서는 S0 이전 실험 구역과 사람 판정 대기열에만 둔다. ITEM_LEDGER에는 자동 등록하지 않는다.
- 열린데이터와 빅데이터캠퍼스는 기사 아이템이 아니라 질문의 분포·대상·시간대를 확인할 검증 데이터 지도로만 사용한다.
- 신규 소스 정밀도는 7일 동안 사람 판정 완료율 80% 이상일 때만 평가한다.

## 변경 안전장치

- 예약 실행은 이 문서와 정책·템플릿·출처군 등록부를 읽기 전용으로 취급한다.
- 상태 변경은 장부, 후속검증 대기열, 편집자 피드백 처리 상태, 각 작업의 산출물에 한정한다.
- 정책 변경 전에는 agent-system-v1/snapshots 아래에 기준 파일과 자동화 설정을 보존한다.
