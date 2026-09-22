# 서울 기획 아이템 발굴 시스템 v3.1 — 활성 구성

기준일: 2026-09-22

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
| 넓은 신규 소스 시험·비교 규격 | source-onboarding-v1/WIDE_SOURCE_SCREENING.md |
| 신규 소스 공통 비교 점수표 | source-onboarding-v1/source_batch_scorecard.py |
| 다원 후보 얇은 일괄 수집 | source-onboarding-v1/collect_wide_batch.py |
| 다원 후보 읽기 전용 비교 실행 | .github/workflows/source-onboarding-wide-batch.yml |
| 정보소통광장 접근·API 키 확인 기록 | source-onboarding-v1/OPENGOV_ACCESS_FINDINGS.md |
| 감사 결과·시민제안 동일 L2 본문 표본 비교 | source-onboarding-v1/collect_l2_equal_sample.py |
| 동일 L2 본문 표본 수동·PR 읽기 전용 실행 | .github/workflows/source-onboarding-l2-equal-sample.yml |
| 감사 첨부 공개문·시민제안 실질 본문 비교 | source-onboarding-v1/compare_substantive_samples.py |
| 실질 본문 비교 수동·PR 읽기 전용 실행 | .github/workflows/source-onboarding-substantive-comparison.yml |
| 고정 실질 본문 표본 사람 판정 재계산 | source-onboarding-v1/review_substantive_snapshot.py |
| 고정 표본 사람 판정 운영안 | source-onboarding-v1/SUBSTANTIVE_REVIEW_RUNBOOK.md |
| 2026-09-17 고정 표본 사람 판정(자동 작성 금지) | source-onboarding-v1/substantive_reviews_2026-09-17.csv |
| 고정 표본 사람 판정 main 변경·수동 읽기 전용 실행 | .github/workflows/source-onboarding-substantive-review.yml |
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
| 자치구의회 25곳 얇은 반복 관측 | district-council-pilot/watch_new_minutes.py |
| 자치구의회 관측 예약·파생 상태 저장 | .github/workflows/district-council-watch.yml |
| 자치구의회 25곳 L2 본문·목록 정합성 표본 | district-council-pilot/collect_body_l2.py, district-council-pilot/BODY_L2_RUNBOOK.md |
| 자치구의회 L2 수동·PR 읽기 전용 실행 | .github/workflows/district-council-body-l2.yml |
| 자치구의회 고정 7건 L3 발언 문맥 그림자 검토 | district-council-pilot/interpret_l3_context.py, district-council-pilot/l3_fixed_sample_2026-09-22.json |
| 자치구의회 L3 PR 무과금·수동 모델 실행 | .github/workflows/district-council-l3-context.yml |
| 구의회 본문 점검 결과·L3 운영 경계 | district-council-pilot/L2_FINDINGS_2026-09-22.md, district-council-pilot/L3_CONTEXT_RUNBOOK.md |
| 공식 SNS 26개 단위 L0 계정 등록 | official-social-pilot/accounts.json |
| 단체장 페이스북 26개 편집자 확인 원목록(플랫폼 재확인 전) | official-social-pilot/editor_confirmed_officeholders.json |
| 공식 SNS 계정 링크 L0 재확인 | official-social-pilot/verify_registry.py |
| 공식 SNS 26개 공식 홈페이지 링크 후보 L0 시험 | official-social-pilot/scan_official_sites.py |
| 단체장 26명 이름 검색 L0 씨앗 | official-social-pilot/name_search_seeds.json |
| 단체장 페이스북 검색 후보 L0 시험 | official-social-pilot/search_officeholder_names.py |
| 단체장 게시물 주소 검색 색인 가능성 시험(성숙도 L0 유지) | official-social-pilot/probe_post_index.py |
| 단체장 게시물 주소 검색 수동·PR·main 읽기 전용 실행 | .github/workflows/officeholder-post-index-feasibility.yml |
| 편집자 제출 페이스북 게시물 링크 검증 | official-social-pilot/validate_manual_post_links.py |
| 편집자 제출 링크 검증 수동·PR 읽기 전용 실행 | .github/workflows/facebook-manual-link-intake.yml |
| 공식 홈페이지 연결 유튜브 채널 8곳 L1 표본 시험 목록 | official-social-pilot/youtube_feed_trial.json |
| 공식 홈페이지 연결 유튜브 공개 피드 L1 표본 수집 | official-social-pilot/collect_youtube_feed_trial.py |
| 공식 유튜브 L1 PR·main·수동 읽기 전용 실행 | .github/workflows/official-youtube-feed-trial.yml |
| 단체장 이름 검색 L0 PR·수동·main 변경 실행 | .github/workflows/officeholder-name-search-l0.yml |
| 공식 SNS L0 수동·PR 읽기 전용 실행 | .github/workflows/official-social-l0.yml |
| 읽기 전용 운영 화면 설계·목업 | app-ui-v1/README.md |
| 읽기 전용 운영 화면 | app-ui-v1/index.html, app-ui-v1/styles.css, app-ui-v1/app.js |
| 검색·뉴스 관심 신호 수집(탐색용) | interest-signal-pilot/collect_interest_signals.py |
| 검색 제목 사람 검토 큐(자동 후보 승격 금지) | interest-signal-pilot/build_review_queue.py |
| 뉴스 원문 본문 한정 대조·내용 판정(최대 6회 모델 호출, 자동 후보 승격 금지) | interest-signal-pilot/analyze_news_context.py |
| 관심 신호 예약·수동 실행 | .github/workflows/collect-interest-signals.yml |
| 화면 데이터 생성·품질 게이트 | app-ui-v1/build_ui_data.py, editorial-v3/validate_candidate_contract.py |
| 화면 데이터 예약·수동 실행 | .github/workflows/app-ui-data.yml |
| 탐색 신호 승격 경계 PR 검증 | .github/workflows/editorial-hypothesis-gate.yml |
| 통합 흐름 및 구현 상태 | editorial-v3/SYSTEM_ARCHITECTURE.md |
| 월·수 기획 질문 검토 입력·모델·품질 게이트 | editorial-v4/pipeline.py |
| 기획 질문 검토 자동 실행 | .github/workflows/editorial-v4.yml |
| 사람 판정 기록 및 실행 | editorial-v4/record_decision.py, editorial-v4/decisions.json, .github/workflows/review-editorial-v4.yml |
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
11. 다원 후보 얇은 비교: 환경영향평가는 L0 상태에서 L1 상세주소 해석 가능성을 진단하고 정보소통광장은 L0 접속을 재시험한다. 서울시 감사 결과·시민제안은 최대 20건 목록, 25개 자치구의회는 전체 접속 상태와 실패한 의회 이름·유형을 같은 읽기 전용 실행에서 비교한다. 접속 전용 결과는 빈 목록으로 판정하지 않고, 건설알림이는 저장된 개별 상세주소가 없어 이 묶음에서 보류한다. 질문·브리핑·장부는 만들지 않는다.
12. 감사 결과·시민제안 동일 L2 본문 비교: 두 소스 모두 공식 목록 상단 고유 항목 5건과 상세 화면을 같은 분모·접근 기준으로 비교한다. 원문 전체와 개인정보·첨부파일은 저장하지 않고, 기술 본문 확보율과 사람 검토 대기열만 만든다. 소스별 게시 주기와 감사 첨부 PDF 의존 차이는 별도 한계로 표시하며 질문·브리핑·장부에는 연결하지 않는다.
13. 실질 본문 비교: 감사 결과는 공식 PDF 지적 일람표, 시민제안은 상세 제안문에서 소스별 최근 3건을 읽는다. 파생 근거와 가린 짧은 검토 문장만 저장한다. 동일한 사람 판정 라벨로 유효 단서율을 산출하되 사람 판정 전에는 서열을 매기지 않는다. 질문·브리핑·장부 연결은 하지 않는다.
14. 고정 실질 본문 표본 사람 판정: 2026-09-17 비교 실행의 불변 artifact에서 파생 카드 3건씩을 다시 읽고, 사람이 명시적으로 입력한 라벨만 결합한다. 최신 소스를 재수집해 분모를 바꾸지 않으며 3건씩은 흐름 시험으로만 표시하고 소스 서열·자동 편입을 만들지 않는다. 원문·질문·브리핑·장부는 변경하지 않는다.
15. 서울시 감사 결과 L4 그림자 평가: 매일 10:45 KST 최근·최대 12개월 후향 공식 감사문서 중 미평가 최대 3건만 표본화한다. 사람은 문서 가치와 대표 각도 선택을 분리해 기록한다. 소스 등록 단계는 L3로 유지하고 7개 관측일·12개 고유 문서·사람 판정 완료율 80%와 대표 각도 적중률 기준을 충족하기 전에는 승격 판정을 하지 않는다. 원문 비저장, 브리핑·장부 자동 연결 금지.
16. 자치구의회 25곳 얇은 반복 관측: 매일 08:45 KST 각 공식 최근목록의 첫 화면에서 최대 20건의 주소·회의일만 비교한다. 첫 관측은 기준선이고, 접속 실패는 기존 상태를 보존한다. 이전 관측과 겹치지 않으면 누락 가능성으로 표시하며 전체 회기 수집 완료로 주장하지 않는다. 질문·브리핑·장부에는 연결하지 않는다.
17. 자치구의회 25곳 L2 본문 정합성 표본: 각 의회의 최신 회의록 1건에서 본문 유무·회의일·회의 식별정보를 목록과 대조한다. 실패는 0건으로 환산하지 않고 본문 원문을 저장하지 않는다. 수동·PR 읽기 전용 artifact만 생성하며 성숙도는 L1로 유지하고 질문·브리핑·장부에 연결하지 않는다.
18. 자치구의회 고정 7건 L3 발언 문맥 그림자 검토: L2에서 비임시본과 회의일 대응이 확인된 문서만 고정한다. PR은 원문 접근·본문 변화만 검사하고, 수동 실행만 7건의 발언 문맥 판정과 최대 1회 독립 편집 판정(총 최대 8회 모델 호출)을 수행한다. 1차 REVIEW는 검증 단서이며 2차에서 방송 가치와 시민 연결을 별도로 판정한다. HOLD의 원문 단서와 다음 확인 조건도 남긴다. 원문 전체는 비저장, 결과는 Actions 요약과 7일 artifact로만 제공한다. 구의회 성숙도는 L1로 유지하고 편집 v4·공개 브리핑·장부로 자동 연결하지 않는다.
19. 공식 SNS L0 계정 확인: 서울시와 25개 자치구 슬롯을 등록하되 공식 서울시 목록에서 직접 연결된 시 기관 계정 3개만 우선 검증한다. 25개 구청 홈페이지는 정부24 등재 주소로 등록하되 SNS 기관·단체장 계정은 미등록 상태를 유지한다. 수동·PR 읽기 전용으로 공식 목록의 서울시 링크를 재확인하고 26개 홈페이지 첫 화면에서 SNS 링크 후보만 추출한다. 게시물·질문·브리핑·장부에 연결하지 않는다.
20. 단체장 이름 검색 L0 후보: 현직자 이름 확인 근거와 임시 선거결과 이름 씨앗을 구분해 서울시장·25개 구청장에 최대 2회씩 네이버 웹문서 검색을 실시한다. 페이스북 프로필 주소만 미승인 후보로 남기고 검색 실패·미발견을 계정 부재로 해석하지 않는다. PR은 키 없는 형태 시험, main 코드 변경 및 수동 실행은 읽기 전용 검색이다. 게시물·질문·브리핑·장부에 연결하지 않는다.

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


## 월·수 기획 질문 검토 흐름 (v4, 최종 기사 승인과 분리)

- 월·수 08:00 KST 공개 소스 피드, 08:30 KST 뉴스 관심 신호를 수집한 뒤 성공한 관심 신호 실행을 계기로 `editorial-v4/pipeline.py`를 실행한다. GitHub Actions 지연 가능성이 있어 09:00 정각 보장은 아니다.
- 서울시의회 발언과 뉴스 본문 판정의 파생 맥락을 함께 읽는다. 감사 결과는 최근 표본에서 지적 내용이 확인된 카드만 읽는다. 원문 전체나 API 키는 저장하지 않는다.
- 구의회는 목록 상태, 유튜브는 검색 전략 상태만 있어 본문 단위 후보 생성에서 제외하고 누락 이유를 화면에 드러낸다. 커뮤니티·제보 역시 실제 본문 경로가 연결되기 전에는 허위 아이템을 생성하지 않는다.
- 기존 판정·편집자 선정·미래 문서일을 먼저 제외하고, 남은 본문을 최신순·출처군 순환으로 최대 8건 고른다. 뉴스 관심도는 시민 직접 경험으로 세지 않는다.
- 모델은 먼저 최대 8개 파생 맥락에서 가설과 질문을 제안한다. 원문에 없는 인용, 원문 반복 제목, 범용 질문, 반대 설명·첫 확인 경로·방송 장면이 없는 제안은 보류한다. 최대 3건·동일 출처군 1건·0건 허용이다.
- 1차 제안이 있을 때만 별도 모델 호출로 실제 문제 신호, 질문 차별성, 반대 설명, 결정적 검증과 6~7분 제작 경로를 독립 반론 검토한다. 최대 2회 호출이며 통과도 사실 확인·기사 승인이 아니다. 응답 ID가 불완전하면 안전하게 실패한다.
- 모든 제안은 '취재 질문 검토·사실 미확인' 상태다. `review-editorial-v4.yml`에서 정확한 ID로 완료·기각·보류 판정을 기록한다. 다음 실행에서는 같은 ID 및 기존 편집자 선정 발언을 제외한다.
- v4 결과는 기존 `editorial-v3` 최종 후보 계약과 별도 영역에 표시한다. 사람 판정이 곧 사실 확인이나 기사 승인이 되지는 않는다.
