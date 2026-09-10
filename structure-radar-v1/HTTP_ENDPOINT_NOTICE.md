# 서울 OpenAPI HTTP 수집기 사용 주의

`collector-commercial-v1.1-http.py`는 서울 열린데이터광장이 공식 예시로 제공하는 `http://openapi.seoul.go.kr:8088` 엔드포인트만 사용한다.

- 이 포트는 HTTPS/TLS를 지원하지 않아 HTTPS 수집기에서는 `WRONG_VERSION_NUMBER` 오류가 발생한다.
- 호출 키는 HTTP 전송 경로에 포함된다. 다른 서비스와 공유하지 않는 전용 키만 쓴다.
- 키는 코드, 보고서, JSON, 채팅에 기록하지 않는다.
- 의심스러운 노출이 있으면 열린데이터광장에서 즉시 키를 재발급하고 이전 키 사용을 중지한다.

실행 결과는 새 스냅샷으로만 저장되고 키는 포함하지 않는다.
