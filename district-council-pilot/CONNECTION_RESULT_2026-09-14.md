# 서울 25개 구의회 연결 점검 결과

확인일: 2026-09-14 / 마지막 일괄 실행: 11:10~11:12 KST

## 결론

서울 25개 구의회 연결 구성을 추가했다. 시험 과정 전체에서는 25곳 모두 공식 회의록 본문 읽기를 확인했다. 그러나 **마지막 일괄 실행이 25곳 전부 정상이라는 뜻은 아니다.** 마지막 실행은 23곳의 목록과 본문 46건을 확보했고, 도봉·동대문은 외부 접속 오류로 미확인 상태다.

연결 범위 확장은 완료했지만 접속 안정성은 관측이 더 필요하다. 이번 변경은 일일 브리핑 편입이나 기사 아이템 승인 완료가 아니다.

## 확인 근거

- [최종 코드 전체 25곳 실행 #11](https://github.com/onetym77-bit/news-item-radar/actions/runs/34798308731): 코드 d0d5beae4e21cf22f5a364dd9050657f42daf2d9. 목록 23/25곳, 본문 46/50건, 날짜·대수·회차 자동 대조 MATCH 45건, UNVERIFIED 1건. 목록 접속 실패로 선정하지 못한 4건은 분모에서 빼지 않았다.
- [이전 전체 실행 #9](https://github.com/onetym77-bit/news-item-radar/actions/runs/34797778449): 도봉과 동대문 각각 본문·메타데이터 2/2 확인. 당시 서대문은 목록만 성공했으며 본문은 실패했다.
- 마지막 코드에서 서대문은 공식 목록의 네 탭을 읽고 실제 발언 본문 2건을 추출했다. AI 요약을 대체 본문으로 쓰지 않았다.
- 서로 다른 실행의 성공 기록을 더해 마지막 실행의 성공률을 100%로 보고하지 않는다. 페이지에 HTTP 200이 반환된 것도 본문 확보와 별도로 판단한다.

## 구별 최종 실행 상태

| 구·공식 목록 | 목록 | 본문 | 메타 대조 MATCH | 판단 |
|---|---|---:|---:|---|
| [강남구](https://www.gncouncil.go.kr/kr/minutes/late.do) | 성공 | 2/2 | 1/2 | 본문 2건 확보, 1건 날짜 대조 미확인 |
| [관악구](https://www.ga21c.seoul.kr/kr/minutes/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [노원구](https://council.nowon.kr/kr/assembly/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [마포구](https://council.mapo.seoul.kr/kr/assembly/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [성동구](https://sdcouncil.sd.go.kr/kr/assembly/late) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [종로구](https://bookcouncil.jongno.go.kr/kr/assembly/late.do?menuNo=400052) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [중구](https://council.junggu.seoul.kr/kr/minutes/late) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [용산구](https://www.yscl.go.kr/promote/minutes/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [성북구](https://www.sbc.go.kr/kr/assembly/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [강북구](https://council.gangbuk.go.kr/kr/minutes/search.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [도봉구](https://www.council-dobong.seoul.kr/meeting/confer/recent.do) | 실패 | 0/2 | 0/2 | 이번 DNS 실패; #9에서는 본문·메타 2/2 |
| [은평구](https://council.ep.go.kr/kr/minutes/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [서대문구](https://ams.sdmcouncil.go.kr/assem/recent.do) | 성공 | 2/2 | 2/2 | 공식 4탭 목록·원문 발언 블록 연결 |
| [양천구](https://www.ycc.go.kr/kr/assembly/late) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [강서구](https://gsc.gangseo.seoul.kr/meeting/confer/recent.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [광진구](https://council.gwangjin.go.kr/kr/assembly/late) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [동대문구](https://council.ddm.go.kr/kr/minutes/late.do) | 실패 | 0/2 | 0/2 | 이번 시간초과; #9에서는 본문·메타 2/2 |
| [중랑구](https://council.jungnang.go.kr/kr/minutes/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [구로구](https://www.guroc.go.kr/meeting/confer/main.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [금천구](https://council.geumcheon.go.kr/council/kr/minutes/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [영등포구](https://www.ydpc.go.kr/content/minutes/minutesLately.html) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [동작구](https://assembly.dongjak.go.kr/kr/minutes/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [서초구](https://sdc.seoul.kr/kr/minutes/pages/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [송파구](https://council.songpa.go.kr/kr/assembly/late.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |
| [강동구](https://council.gangdong.go.kr/meeting/confer/recent.do) | 성공 | 2/2 | 2/2 | 이번 표본 읽기 완료 |

## 잔여 문제

1. 도봉구: 공식 호스트와 확인된 별칭 모두 일시적인 주소 해석 오류. 재시도 후에도 실패했으므로 UNKNOWN_COLLECTION으로 남겼다.
2. 동대문구: 목록 요청 시간초과. 새 회의록 없음으로 바꾸지 않았다.
3. 강남구 [문서 9108](https://www.gncouncil.go.kr/viewer/minutes.do?uid=9108): 본문은 읽히지만 목록의 2026-07-29를 상세의 날짜 표기로 자동 대조하지 못했다. UNVERIFIED를 유지하며 원문 검토가 필요하다.
4. 단일 날짜 시험으로 매일 안정적인 공급·수집을 보장할 수 없다. 회의일을 공개일로 바꾸지 않았으며 공개일은 미확인이다.

## 검사 결과

- 파서·목록 선정·오류 분리·관측 상태 회귀검사 37개 통과.
- 시스템 검증: 오류 0개, 기존 경고 12개.
- 경고 구성: 기존 검토기한 경과 항목 11개, 온라인 저장소에서 제외된 과거 source_report 26개 파일의 존재 검사 생략 안내 1개. 관련 판정표와 원본 파일은 이번 범위에서 변경하지 않았다.
- 별도 코드 검토에서 병합 차단 결함은 발견되지 않았다. 실제 접속 문제는 위 구별 결과에 그대로 남겼다.
- 최종 실행 결과를 남기는 이 문서 커밋은 설명만 추가한다. 검증한 코드·설정·워크플로는 변경하지 않으며 중복 외부 요청을 피하도록 문서 커밋의 자동 재실행을 생략한다.

## 이번 변경 범위

- 기존 5곳 구성은 유지하고 25곳 구성과 수동 연결 검사 경로를 별도 추가했다.
- 같은 공유 코드 변경으로 5곳·25곳 수집이 중복 실행되지 않도록 기존 5곳은 수동 실행으로 유지했다.
- 서초·서대문의 발언 블록, 레거시 팝업, 경로형 문서번호 등 공식 사이트별 차이를 처리했다.
- 첫 관측·확인 범위 내 신규 문서·수집 실패를 구분했다. 본문 변경 지문은 보존하지만 개정 이력 자동 분석은 아직 없다.
- 기존 로컬 파일, ITEM_LEDGER, 편집자 판정, YouTube 요청량, 일일 브리핑 예약은 변경하지 않았다.
- 영구 보고서는 이 문서이며 실행 산출물은 GitHub Actions에서 30일 보관한다. 원문 아카이브·개인 연락처·키는 저장소에 추가하지 않았다.

## 다음 운영 연결에서 필요한 것

매일 첫 2건만 읽는 방식을 그대로 정식 발굴로 사용하지 않는다. 회기 중 대량 공개를 놓치지 않도록 마지막 관측 문서까지 목록을 따라가고 미검토 자료를 대기열에 남겨야 한다. 수집 실패 재확인도 별도 상태로 관리한다.

본문 확보나 자동 추출 문단 수는 질문 품질의 증거가 아니다. 실제 비교·설명 질문, 경쟁 설명, 첫 검증 자료를 기준으로 편집 검토해야 한다.

비회기 보완은 [추가 소스 시험안](OFF_SESSION_SOURCE_PLAN.md)에 정리했다. 응답소 민원통계, 건설알림이, 시민제안을 우선 소량 시험하고, 새 게시물이 없는 날에도 축적 질문을 지역·기간·대상별로 다시 검증하는 흐름을 결합하는 방향이다. 신규 비의회 수집기와 일일 예약 편입은 이번에 수행하지 않았다.
