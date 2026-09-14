# 질문 근거 검사 수정 전후 비교

- 동일 자료: 2026-09-14 실제 실행에서 확인된 오탐·오분류 29건과 보존해야 할 양성 3건
- 수정 전은 당시 실행 결과·질문을 요약했고, 수정 후는 현재 분류기를 같은 문장에 다시 적용한 값

| 사례 | 수정 전 | 수정 후 | 자동 처리 |
|---|---|---|---|
| 예산 증감 조정 절차 | DECOMPOSABLE_STRUCTURE | PASS · REPORTABLE_TEXT · NONE · 질문 HOLD | 자동 제외 |
| 귀속된 이용 증가 주장 | 확인된 변화로 표현 | PASS · REPORTABLE_TEXT · DECOMPOSABLE_STRUCTURE · 질문 PASS | 후보 유지 |
| 중립적 이용 증가 | MEASURED_PROBLEM_SIGNAL | PASS · REPORTABLE_TEXT · DECOMPOSABLE_STRUCTURE · 질문 PASS | 후보 유지 |
| 일반 의정 연설 | MEASURED_PROBLEM_SIGNAL | FAIL · SPEECH_PROMISE · NONE · 질문 HOLD | 자동 제외 |
| 학생인권 우려 발언 | MEASURED_PROBLEM_SIGNAL | HOLD · CONCERN_OR_ATTRIBUTED_CLAIM · NONE · 질문 HOLD | 본문 확보 대기 |
| 위원 선임 절차 | DECOMPOSABLE_STRUCTURE | FAIL · PARLIAMENTARY_PROCEDURE · NONE · 질문 HOLD | 자동 제외 |
| 열린데이터 메뉴 | 검증 지도 진입 | FAIL · NAVIGATION · NONE · 질문 HOLD | 자동 제외 |
| 서울연구원 제목 | MEASURED_PROBLEM_SIGNAL | HOLD · DOCUMENT_TITLE_ONLY · NONE · 질문 HOLD | 본문 확보 대기 |
| 값 없는 체불 표 제목 | MEASURED_PROBLEM_SIGNAL | HOLD · TABLE_SCHEMA_WITHOUT_VALUE · NONE · 질문 HOLD | 본문 확보 대기 |
| 응답소 연락처 푸터 | DIRECT_PROBLEM_SIGNAL | FAIL · CONTACT_BOILERPLATE · NONE · 질문 HOLD | 자동 제외 |
| 정책 투입액 발표 | MEASURED_PROBLEM_SIGNAL | HOLD · POLICY_ANNOUNCEMENT · NONE · 질문 HOLD | 본문 확보 대기 |
| 포털 표시 안내 | 검증 지도 진입 | FAIL · PLATFORM_NOTICE · NONE · 질문 HOLD | 자동 제외 |
| 민원 처리 요약 제목 | DIRECT_PROBLEM_SIGNAL | PASS · REPORTABLE_TEXT · NONE · 질문 HOLD | 자동 제외 |
| 교육 예산 약속 | MEASURED_PROBLEM_SIGNAL | HOLD · POLICY_ANNOUNCEMENT · NONE · 질문 HOLD | 본문 확보 대기 |
| 체불 표 구조 설명 | MEASURED_PROBLEM_SIGNAL | HOLD · TABLE_SCHEMA_WITHOUT_VALUE · NONE · 질문 HOLD | 본문 확보 대기 |
| 포털 제공기간 안내 | 검증 지도 진입 | FAIL · PLATFORM_NOTICE · NONE · 질문 HOLD | 자동 제외 |
| K-패스 가정값 | MEASURED_PROBLEM_SIGNAL | HOLD · HYPOTHETICAL_EXAMPLE · NONE · 질문 HOLD | 본문 확보 대기 |
| 출생아 증가 | MEASURED_PROBLEM_SIGNAL·문제 질문 | PASS · REPORTABLE_TEXT · DECOMPOSABLE_STRUCTURE · 질문 PASS | 후보 유지 |
| 응답소 안내 푸터 | DIRECT_PROBLEM_SIGNAL | FAIL · CONTACT_BOILERPLATE · NONE · 질문 HOLD | 자동 제외 |
| 의회 쟁점 언급과 발언시간 | MEASURED_PROBLEM_SIGNAL | HOLD · ISSUE_MENTION_ONLY · NONE · 질문 HOLD | 본문 확보 대기 |
| 응답소 단순 접수 현황판 | DIRECT_PROBLEM_SIGNAL | HOLD · AGGREGATE_ACTIVITY_DASHBOARD · NONE · 질문 HOLD | 활동 기준선·후보 아님 |
| 임금체불 증가 | 긍정 회복으로 오분류 | PASS · REPORTABLE_TEXT · MEASURED_PROBLEM_SIGNAL · 질문 PASS | 후보 유지 |
| 응답소 이용 안내 | DIRECT_PROBLEM_SIGNAL | FAIL · PORTAL_INSTRUCTION · NONE · 질문 HOLD | 자동 제외 |
| 행정 범위 숫자만 있는 우려 | DECOMPOSABLE_STRUCTURE | HOLD · CONCERN_OR_ATTRIBUTED_CLAIM · NONE · 질문 HOLD | 본문 확보 대기 |
| 채무비율 정책 전망 | DECOMPOSABLE_STRUCTURE·지역 분해 질문 | HOLD · POLICY_FORECAST · NONE · 질문 HOLD | 본문 확보 대기 |
| 다음 문장의 무관한 예산 | MEASURED_PROBLEM_SIGNAL | PASS · REPORTABLE_TEXT · NONE · 질문 HOLD | 자동 제외 |
| 시위 종료와 의회 서수 | MEASURED_PROBLEM_SIGNAL | PASS · REPORTABLE_TEXT · NONE · 질문 HOLD | 자동 제외 |
| 제목만 확인된 데이터셋 | 검증 자산 | PASS · DATASET_METADATA · NONE · 질문 HOLD | 스키마·값 확인 대기 |
| 설명만 확인된 데이터 구조 | 검증 자산 | PASS · REPORTABLE_TEXT · DECOMPOSABLE_STRUCTURE · 질문 HOLD | 실제 값 수집 대기 |
| 외국인 카드 총액 | NONE | PASS · REPORTABLE_TEXT · DECOMPOSABLE_STRUCTURE · 질문 PASS | 후보 유지 |
| UD택시 공급 제약 | 질문에 병원 이동·미배차를 사실처럼 추가 | PASS · REPORTABLE_TEXT · MEASURED_PROBLEM_SIGNAL · 질문 PASS | 후보 유지 |
| 버스 소송 추산 | 원인을 관리 공백으로 단정 | PASS · REPORTABLE_TEXT · MEASURED_PROBLEM_SIGNAL · 질문 PASS | 후보 유지 |

수정 후 PASS는 기사 승인이 아니라 사람 판정 카드 진입 자격이다.
HOLD는 현상이 없다는 뜻이 아니라 제목·주장만으로는 사실관계를 확정할 수 없다는 뜻이다.
