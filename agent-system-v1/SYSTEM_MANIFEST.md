# 서울 기획 아이템 발굴 시스템 v1.9 — 활성 구성

기준일: 2026-09-14

이 문서는 예약 실행과 수동 실행이 참조할 단일 활성 구성을 지정한다. 아래에 없는 초안·구버전 수집기는 참고 자료이며 자동 실행에 사용하지 않는다.

## 활성 구성

| 역할 | 활성 파일 |
|---|---|
| 공통 정책 | agent-system-v1/AGENT_POLICY.md |
| 질문 품질 게이트 | agent-system-v1/QUESTION_QUALITY_GATE.md |
| 질문 독창성·최소 검증 게이트 | agent-system-v1/ORIGINALITY_AND_TEST_GATE.md |
| 질문 품질 재심사 장부 | agent-system-v1/QUESTION_QUALITY_AUDIT.csv |
| 상태 장부 | agent-system-v1/ITEM_LEDGER.csv |
| 후속검증 대기열 | agent-system-v1/VERIFICATION_QUEUE.csv |
| 편집자 결정 | agent-system-v1/EDITOR_FEEDBACK.md |
| 실행 계측 | agent-system-v1/RUN_METRICS_TEMPLATE.md |
| 출처군·독립성 | agent-system-v1/SOURCE_FAMILY_REGISTRY.md |
| 운영 소스 역할 | source-scout-v1/SOURCE_ROLE_REGISTRY.md |
| 역할 분리형 신규 소스 수집 | source-scout-v1/collect_daily_feed.py |
| 내용 사전판정·질문 근거 검사 | source-scout-v1/grounding.py |
| 신규 소스 사람 판정 대기열 | source-scout-v1/HUMAN_REVIEW_QUEUE.csv |
| 편집 판정 카드·전이 제안 | source-scout-v1/compile_editorial_review.py |
| 7일 정밀도 평가 | source-scout-v1/evaluate_human_review.py |
| 관심 신호 설정 | interest-radar-v2/config/editorial_lenses.json |
| API 수집기(v2.3, 예약 호환 파일명 유지) | interest-radar-v2/collect_source_material_v2_1.py |
| 자치구의회 25곳 연결 등록(수동 점검, 핵심소스 승인 전) | district-council-pilot/sources_25.json |
| 자치구의회 연결 점검기 | district-council-pilot/collect_pilot.py |
| 비회기 보완소스 시험안(미편입) | district-council-pilot/OFF_SESSION_SOURCE_PLAN.md |
| 브리핑 핵심 지침 | briefing-v3.0-draft/SKILL.md |
| 시장 우선 발견 | briefing-v3.0-draft/MARKET_FIRST_DISCOVERY.md |
| 편집 매력도 | briefing-v3.0-draft/EDITORIAL_ATTRACTIVENESS.md |
| 모델 운영 | briefing-v3.0-draft/RUNBOOK.md |
| 편집 게이트 | daily-briefing-v5/EDITORIAL_GATE.md |
| 브리핑 형식 | daily-briefing-v5/OUTPUT_TEMPLATE.md |
| 실행 식별·원본 지문 | daily-briefing-v5/run_provenance.py |
| 예약 실행 | .github/workflows/daily-briefing.yml |
| 자동 검증 | agent-system-v1/validate_discovery_system.py |

## 예약 흐름

1. 관심 레이더: 매일 08:00, 12:00, 17:30 KST
2. 역할 분리형 신규 소스 입력과 일일 브리핑: 매일 09:30 KST
3. 주간 감사: 매주 월요일 09:00 KST

현재 일일 신규 소스 입력과 브리핑의 실행기는 GitHub Actions다. 한 실행에서 소스를 한 번만 수집하고, 같은 파일을 검증·artifact 업로드·main 저장에 사용한다. PR, 다른 브랜치, 과거 날짜 재실행은 미리보기 전용이며 main 최신본을 덮어쓰지 않는다.

## 판정 원칙

- 후보 문장을 먼저 메뉴·회의 절차·일반 연설·우려·값 없는 표제·보고서 제목·본문 근거로 구분한다.
- 법조항, 회기, 연도·날짜 숫자는 측정값으로 세지 않는다.
- 사업명·정책 목적만으로 피해를 추정하지 않는다. 구체적인 문제 징후 또는 실제 값이 있는 분해 가능한 구조 자료만 질문 품질 평가에 들어간다.
- 질문 근거는 원문 문장을 보존하고, 질문에 등장하는 수치는 원문 수치의 부분집합이어야 한다. 새로 확인할 지역·대상·시간 등의 축은 사실이 아니라 검증 변수로 분리한다.
- 공식 발표·통계·공시도 분해·비교 가능한 현상이라면 질문 생성의 출발점으로 사용할 수 있다.
- 전망·우려·이해관계자 추산은 독립 확인 전까지 주장으로 표시한다.
- 열린데이터와 빅데이터캠퍼스는 기사 아이템이 아니라 질문을 확인할 검증 데이터 지도로만 사용한다. 메뉴 문구와 값 없는 표제는 진입시키지 않는다.
- 진입 조건을 통과한 원석은 질문 품질 6개 항목을 12점으로 평가하며, 8점 이상과 필수 항목을 충족해야 질문 품질 PASS다.
- 품질 PASS 뒤 출처 프레임과 편집적 추가를 분리한다. 독창성 PASS와 24시간 이내 최소 판정 실험이 있어야 우선 검증한다.
- 우선 검증에서는 시민 손실 근거와 구조 가설을 약화할 반대 근거를 모두 찾는다.
- 질문 게이트와 기사 게이트를 분리하며 검증 전 가설은 최종 기사 후보로 표시하지 않는다.
- 브리핑은 A 확정 제안(S2·S3), B 당일 검증(S0·S1 질문 PASS), C 질문 원석·후속 관찰로 분리한다.
- 행사·공연·팝업·티켓·단일 예약 신호는 자동 제외하지 않되 일정·가격·이용 팁 이상의 분해·비교·책임 질문이 없으면 질문 게이트에서 제외한다.
- 탐색 작업량 미달과 수집 실패·본문 부족·오탐 제외·질문 불일치를 각각 표시한다. 질문 원석 0건과 기사 게이트 0건은 각각 정상일 수 있다.
- S2 승격에는 독립 근거군 두 개 이상과 실제로 관찰되거나 당사자가 진술한 시민 행동 신호가 필요하다.
- 계획된 현장 장면과 계획된 킬러 테스트는 수행 결과가 아니다.
- 같은 원자료를 재인용한 기사들은 하나의 근거군으로 계산한다.
- 유튜브는 개별 영상 조회수가 아니라 최근 30일의 반복 현상 군집을 발견한다. 생활정보·설명, 언론 재유통, 분류 대기 영상은 독립 시민 신호로 세지 않는다.
- 서울시의회와 응답소의 자동 통과 단서는 S0 이전 판정 카드에만 둔다. ITEM_LEDGER에는 자동 등록하지 않는다.
- 자동 원석은 사람의 PROMISING·VERIFY·NOISE·DUPLICATE 판정을 거친다. PROMISING도 S0 전이 제안일 뿐이며 명시 승인 전에는 장부를 변경하지 않는다.
- 예약 실행은 QUESTION_QUALITY_AUDIT.csv와 ITEM_LEDGER.csv를 자동 수정하지 않는다.
- 신규 소스 정밀도는 7일 동안 사람 판정 완료율 80% 이상일 때만 평가한다.

## 변경 안전장치

- 예약 실행은 이 문서와 정책·템플릿·출처군 등록부를 읽기 전용으로 취급한다.
- 정책과 코드 변경 이력은 Git 커밋과 pull request로 보존하며 별도 스냅숏 복제본을 만들지 않는다.
- main의 최신 브리핑은 실행 ID, 검사 코드, 생성 시각, 정책 버전, 공개 모드, 저장 여부, 유효 시한, 원본·본문 지문을 표시한다.
- 검증한 파일과 저장한 파일의 지문이 다르면 실행을 실패시킨다.
- 기존 20건의 빈 근거 앵커는 자동 추정하지 않는다. 원자료를 복구한 뒤 0점부터 재심사하고 승인된 변경만 장부에 반영한다.
