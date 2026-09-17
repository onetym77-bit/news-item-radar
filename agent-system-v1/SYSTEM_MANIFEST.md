# 서울 기획 아이템 발굴 시스템 v2.5 — 활성 구성

기준일: 2026-09-17

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
| 신규 소스 성숙도 정책 | source-onboarding-v1/SOURCE_MATURITY_POLICY.md |
| 신규 소스 성숙도 등록부 | source-onboarding-v1/source_maturity_registry.json |
| 얇은 수집 공통 검증 | source-onboarding-v1/thin_source_contract.py |
| 신규 소스 L0 미통과 접속 재시험 | source-onboarding-v1/probe_l0_batch.py |
| 신규 소스 L0 수동·PR 읽기 전용 실행 | .github/workflows/source-onboarding-l0-batch.yml |
| 신규 소스 L1 목록 표본 수집 | source-onboarding-v1/collect_l1_batch.py |
| 신규 소스 L1 수동·PR 읽기 전용 실행 | .github/workflows/source-onboarding-l1-batch.yml |
| 서울시 감사 결과 L2 본문 구조 표본 | source-onboarding-v1/collect_audit_l2.py |
| 서울시 감사 결과 L2 수동·PR 읽기 전용 실행 | .github/workflows/source-onboarding-audit-l2.yml |
| 서울시 감사 결과 L3 검증 질문 시험 | source-onboarding-v1/interpret_audit_l3.py |
| 서울시 감사 결과 L3 수동·PR 읽기 전용 실행 | .github/workflows/source-onboarding-audit-l3.yml |
| 서울시 감사 결과 L4 그림자 평가기(L3 유지) | source-onboarding-v1/audit_l4_shadow.py |
| 서울시 감사 결과 그림자 평가·사람 판정 기준 | source-onboarding-v1/AUDIT_L4_SHADOW_RUNBOOK.md |
| 서울시 감사 결과 L4 사람 판정(자동 작성 금지) | source-onboarding-v1/audit_l4_reviews.csv |
| 서울시 감사 결과 L4 그림자 예약·PR 실행 | .github/workflows/source-onboarding-audit-l4-shadow.yml |
| 역할 분리형 신규 소스 수집 | source-scout-v1/collect_daily_feed.py |
| 내용 사전판정·질문 근거 검사 | source-scout-v1/grounding.py |
| 신규 소스 사람 판정 대기열 | source-scout-v1/HUMAN_REVIEW_QUEUE.csv |
| 편집자 지정 취재 착수 검토 목록 | source-scout-v1/editorial-decisions/selected_reporting_leads.json |
| 편집자 지정 검토 브리핑 주입 | source-scout-v1/inject_feed_into_briefing.py |
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
| 응답소 집계 변화 관측 시험(일일 브리핑 미편입) | eungdapso-stats-pilot/watch.py |
| 응답소 시험 수동 실행·두 파생파일 저장 | .github/workflows/eungdapso-stats-pilot.yml |
| 건설알림이 변화 관측 시험(일일 브리핑 미편입) | construction-watch-pilot/watch.py |
| 건설알림이 시험 예약·파생 상태 저장 | .github/workflows/construction-watch-pilot.yml |
| 시민제안 문장 형식 분류 시험(일일 브리핑 미편입) | citizen-proposal-pilot/watch.py |
| 시민제안 시험 수동·PR 읽기 전용 실행 | .github/workflows/citizen-proposal-pilot.yml |

## 예약 흐름

1. 관심 레이더: 매일 08:00, 12:00, 17:30 KST
2. 역할 분리형 신규 소스 입력과 일일 브리핑: 매일 09:30 KST
3. 주간 감사: 매주 월요일 09:00 KST
4. 건설알림이 변화 관측 시험: 매일 11:15 KST. 네 공식 목록의 첫 페이지를 비교하며, 출처 실패 시 기존 상태를 덮어쓰지 않는다. 일일 브리핑과 장부는 건드리지 않는다.
5. 응답소 집계 변화 관측 시험: 현재 수동 실행만 허용한다. main 수동 실행에서 기준 상태와 질문 파일 두 개만 저장하며 일일 브리핑과 장부는 건드리지 않는다.
6. 시민제안 문장 형식 분류 시험: 수동·PR 읽기 전용 실행만 허용한다. 첫 다섯 고유 제안의 목록·상세 제목 대응을 시험하고 원문 전체·작성자명·연락처를 저장하지 않는다. 다만 문구 분류는 사실 확인이 아니므로 질문·기사 게이트에 자동 연결하지 않는다.
7. 신규 소스 L0 접속 재시험: 네트워크 오류가 난 정보소통광장과 공개 함수형 상세주소를 안전하게 해석하지 못한 환경영향평가를 수동·PR 읽기 전용으로 재진단한다. 실패·부분 성공을 자료 0건으로 해석하지 않는다.
8. 신규 소스 L1 목록 표본 시험: L0 접속과 목록 대응을 통과한 서울시 감사 결과에서 첫 페이지 최대 20건의 고유번호·제목·개별 날짜·상세주소만 수집한다. 본문·질문·브리핑·장부는 만들거나 저장하지 않는다.
9. 서울시 감사 결과 L2 본문 구조 표본: 목록 최근 5건의 공식 상세 페이지만 읽어 제목 대응, 등록일·수정일 구분, 감사배경·대상·기간·중점·처분·재정조치·이행 구조 표지를 파생한다. 원문 문장·담당자·연락처·첨부파일은 저장하지 않고 질문·브리핑·장부에도 연결하지 않는다.
10. 서울시 감사 결과 L3 의미 해석 시험: 최근 3건의 공개 PDF 최대 24쪽에서 감사 지적·처분 일람표와 대표 후보의 처분요구 내용을 일시적으로 읽는다. 지적별 영향도·구체성·검증 가능성을 비교해 대표 각도 하나를 고르며, 원문과 개인정보는 저장하지 않는다. 검증 질문만 사람 검토용으로 제시하고 독립 근거와 반대 근거 확인 전에는 브리핑·장부에 연결하지 않는다.
11. 서울시 감사 결과 L4 그림자 평가: 매일 10:45 KST 최근·최대 12개월 후향 공식 감사문서 중 미평가 최대 3건만 표본화한다. 사람은 문서 가치와 대표 각도 선택을 분리해 기록한다. 소스 등록 단계는 L3로 유지하고 7개 관측일·12개 고유 문서·사람 판정 완료율 80%와 대표 각도 적중률 기준을 충족하기 전에는 승격 판정을 하지 않는다. 원문 비저장, 브리핑·장부 자동 연결 금지.

현재 일일 신규 소스 입력과 브리핑의 실행기는 GitHub Actions다. 읽기 전용 작업에서 소스를 한 번만 수집·검증해 artifact로 넘기고, main 전용 쓰기 작업만 그 동일 산출물을 저장한다. PR, 다른 브랜치, 과거 날짜 재실행에는 쓰기 권한과 Git 자격증명을 주지 않으며 main 최신본을 덮어쓰지 않는다. 비회기에도 원석이 끊기지 않도록 응답소뿐 아니라 서울연구원·고용노동부 임금체불 통계·한국소비자원 자료를 매일 보완 발굴 입력에 포함한다.

## 판정 원칙

- 후보 문장을 먼저 메뉴·회의 절차·일반 연설·우려·값 없는 표제·보고서 제목·본문 근거로 구분한다.
- 법조항, 회기, 연도·날짜 숫자는 측정값으로 세지 않는다.
- 사업명·정책 목적만으로 피해를 추정하지 않는다. 구체적인 문제 징후 또는 실제 값이 있는 분해 가능한 구조 자료만 질문 품질 평가에 들어간다.
- 질문 근거는 원문 문장을 보존하고, 질문에 등장하는 수치는 원문 수치의 부분집합이어야 한다. 새로 확인할 지역·대상·시간 등의 축은 사실이 아니라 검증 변수로 분리한다.
- 같은 사안이 다른 회의록 주소·표현으로 반복돼도 핵심 주제와 공통 수치 지문으로 한 카드만 남긴다.
- 오늘 새 발견 여부와 사람 검토 가능 여부를 분리해, 편집자가 입력한 판정은 동일 원문 지문이 재등장해도 소실되지 않는다.
- 목록 페이지의 최신 날짜를 개별 문장에 일괄 부여하지 않으며, 항목 자체의 게시일을 확인하지 못하면 오늘 후보에서 보류한다.
- 발행일과 수정일이 함께 있으면 발행일을 기준으로 삼아 오래된 문서의 단순 수정 시각이 신호를 새것으로 만들지 않게 한다.
- 공식 발표·통계·공시도 분해·비교 가능한 현상이라면 질문 생성의 출발점으로 사용할 수 있다.
- 전망·우려·이해관계자 추산은 독립 확인 전까지 주장으로 표시한다.
- 열린데이터와 빅데이터캠퍼스는 기사 아이템이 아니라 질문 확인용으로만 사용한다. 제목만 발견한 자료는 '스키마 미확인', 분류·갱신 설명만 읽은 자료는 '실제 값 미수집'으로 분리하고, 실제 데이터 행의 관측값을 수집한 경우에만 검증 데이터 지도에 넣는다.
- 증가·감소·증감은 그 자체로 피해가 아니다. 피해·부담 등의 근거가 없으면 중립적 구조 변화로 묻고, 예산 조정·계획 문구는 관찰 결과로 승격하지 않는다.
- 정적 통계표는 축 열과 분석값 열이 함께 있고 실제 행이 확인될 때만 수집한다. 파일명·용량·갱신일·제공기관 표는 실제값으로 세지 않는다.
- 소스의 역할은 해당 주장에 대한 독립 검증 완료를 뜻하지 않는다. 회의록은 원문 근거, 데이터 포털은 후속 검증 경로로 표시한다.
- 진입 조건을 통과한 원석은 질문 품질 6개 항목을 12점으로 평가하며, 8점 이상과 필수 항목을 충족해야 질문 품질 PASS다.
- 품질 PASS 뒤 출처 프레임과 편집적 추가를 분리한다. 독창성 PASS와 24시간 이내 최소 판정 실험이 있어야 우선 검증한다.
- 우선 검증에서는 시민 손실 근거와 구조 가설을 약화할 반대 근거를 모두 찾는다.
- 질문 게이트와 기사 게이트를 분리하며 검증 전 가설은 최종 기사 후보로 표시하지 않는다.
- 정확한 사안·서울 범위·영향 대상이 확인되고 수치 기준기간만 빠진 신선한 시의회 HOLD 단서는 별도 자동 `편집 검토` 영역에 노출할 수 있다. 자동 선별은 질문 생성이나 게이트 통과가 아니다.
- 편집자가 직접 고른 문맥 HOLD 단서는 별도 `취재 착수 검토` 영역에 노출할 수 있다. 원문 발언은 주장으로 표시하고 미확인 수치·피해를 확정하지 않으며, 이 노출은 S0 전이·질문 PASS·기사 PASS를 뜻하지 않는다.
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
- 신규 소스는 L0 접속, L1 목록, L2 본문 표본, L3 의미 해석, L4 7일 그림자 검증, L5 운영 승인 순서로 편입한다. L0~L2는 질문·브리핑을 만들 수 없고 L3도 검증 질문 외에는 일일 브리핑과 장부에 연결하지 않는다.

## v2.2 핵심 보완

- 문서 발행·회의일과 본문이 인용한 통계 기준기간을 분리한다. 현재월 통계는 실행일까지만 유효한 것으로 계산하되 원문 지문에는 안정적인 `YYYY-MM`을 쓴다.
- 서울 기관이라는 이유만으로 서울 현상으로 보지 않는다. 전국 소스는 서울 지역 행 또는 서울·문제지표·실제 값이 직접 결합된 경우에만 서울 범위로 인정한다.
- 같은 원문 지문의 전체 이력을 보존해 내용이 A→B→A로 되돌아와도 새 카드로 위장하지 못하게 한다. 지역화·재등장 단서도 관측일은 갱신하되 자동 활성화하지 않는다.
- 신선도 초과 자료는 `STALE_CARRYOVER`, 보관 기한을 넘긴 자료는 감사 표본, 날짜가 확인되지 않은 자료는 `날짜 확인 대기`로 분리한다.
- 전국 단서는 `서울 지역화 대기`에 두고 서울 원자료가 확보되기 전에는 편집 카드·킬러 테스트·S0 제안을 만들지 않는다.
- 접속 실패와 본문 저하를 최종 브리핑에 표시해 0건을 현상 부재로 오해하지 않게 한다.
- 실행 묶음의 모든 허용 산출물과 이번 실행의 정확한 history 두 파일에 SHA-256 지문을 부여하고, wildcard 없이 main 저장 전후에 검증한다.
- 과거 날짜 재실행은 과거 스냅샷 재현이 아니라 현재 장부의 지정일 재계산과 현재 소스의 혼합임을 명시한다.

## 변경 안전장치

- 예약 실행은 이 문서와 정책·템플릿·출처군 등록부를 읽기 전용으로 취급한다.
- 정책과 코드 변경 이력은 Git 커밋과 pull request로 보존하며 별도 스냅숏 복제본을 만들지 않는다.
- main의 최신 브리핑은 실행 ID, 검사 코드, 생성 시각, 정책 버전, 공개 모드, 저장 여부, 유효 시한, 원본·본문 지문을 표시한다.
- 검증한 파일과 저장한 파일의 지문이 다르면 실행을 실패시킨다.
- PR 수집·검증 작업은 contents: read와 persist-credentials: false로 실행하고, main 저장 작업만 contents: write를 사용한다.
- 저장 직전 ITEM_LEDGER.csv와 QUESTION_QUALITY_AUDIT.csv 무변경 및 생성파일 allowlist를 확인하며, 실행 중 main이 이동하면 non-fast-forward로 안전 실패한다.
- 기존 20건의 빈 근거 앵커는 자동 추정하지 않는다. 원자료를 복구한 뒤 0점부터 재심사하고 승인된 변경만 장부에 반영한다.
