# News Item Radar

서울 지역 기획기사 아이템 발굴 시스템의 온라인 운영 저장소입니다.

## 기준본

- 이 저장소를 앞으로의 코드, 정책, 설정 기준본으로 사용합니다.
- 기존 Windows 로컬 폴더는 수정하지 않는 원본 보관본으로 유지합니다.
- 현재 활성 구성은 `agent-system-v1/SYSTEM_MANIFEST.md`를 따릅니다.

## 주요 구성

- `agent-system-v1/`: 공통 정책, 질문 품질·독창성 게이트, 상태 장부, 자동 검증
- `interest-radar-v2/`: 관심 신호 수집기, 편집 렌즈, YouTube 할당량·검색 건강도 상태
- `briefing-v3.0-draft/`: 브리핑 작성·편집 판단 기준
- `daily-briefing-v4/`: 최종 편집 게이트와 출력 형식
- `structure-radar-v1/`: 구조 데이터 수집·분석 코드와 설계 문서

## 데이터와 보안

원자료, 대용량 생성 결과, 압축파일, 이미지, 과거 실행 산출물과 인증정보는 Git에 저장하지 않습니다. API 키는 실행 환경의 secret 또는 환경변수로만 제공합니다.

필요한 환경변수:

- `YOUTUBE_API_KEY`
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

## 검증

변경 후 저장소 루트에서 다음 검증을 실행합니다.

```bash
python agent-system-v1/validate_discovery_system.py
```

변경은 별도 브랜치와 검토 가능한 diff를 거쳐 `main`에 반영합니다.
