# 시민 신호·인기 콘텐츠 탐색층

이 층은 서울시민의 문제 제기와 지역 현장 신호를 찾는 탐색 소스다.

## 공통 원칙

- 공개 페이스북·인스타그램·유튜브·뉴스·공공 민원 공개 페이지만 사용한다.
- 비공개 그룹, 개인 계정, 로그인 우회, 개인정보가 포함된 원문은 수집하지 않는다.
- 게시물의 인기·조회수는 관심 신호일 뿐 사실이나 기사 가치의 증거가 아니다.
- 단일 게시물과 단일 민원은 후보가 아니라 발견 신호로 취급한다.
- 공식 자료·반복 제보·현장 확인 중 하나 이상으로 교차 확인하기 전에는 기사 후보로 승격하지 않는다.

## 공개 지역 페이지

페이지 목록은 `public_pages.json`에 편집자가 등록한다. 비어 있는 목록은 연결 실패가 아니라 아직 안전하게 검증된 공개 페이지를 등록하지 않았다는 뜻이다.

## 응답소 공개 민원사례 L2 표본

`collect_public_complaints.py`는 시민이 공개를 선택한 응답소 민원사례만 읽는다.

- 공식 목록 최대 20건, 상세 본문 최대 5건
- 민원·답변 원문, 작성자, 전화번호, 이메일, 상세주소 비저장
- 제목·신청일·공개일·공개 원문 주소와 파생 문제 표지만 저장
- 시민 진술은 `미확인 주장`, 기관 답변은 `귀속된 답변이며 독립 증거 아님`으로 구분
- 시민 작성 구간과 기관 답변 구간을 명시적으로 분리하지 못하면 `문맥 미확정`으로 보류하며, 답변에 등장한 문제 단어를 시민 신호로 재사용하지 않음
- L2에서는 질문과 기사 후보를 생성하지 않음
- 수동·PR 읽기 전용 workflow의 7일 artifact로만 확인

실행:

```bash
python -X utf8 -m unittest community-signal-pilot/test_collect_public_complaints.py -v
python -X utf8 community-signal-pilot/collect_public_complaints.py
```

산출물:

- `community-signal-pilot/output/public_complaints_latest.json`
- `community-signal-pilot/output/public_complaints_latest.md`
