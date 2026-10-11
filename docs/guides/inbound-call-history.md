# 착신 이력 조회

백엔드 배포 이후 새로 수락한 HT813 FXO 착신부터 통화 단위 기록이 생긴다. HT813 관리 화면의 `Caller ID Transport Type`에 맞춰 로컬 `.env`의 `VOICE_AGENT_HT813_CALLER_ID_HEADER`를 `from`, `p-asserted-identity`, `p-preferred-identity`, `disabled` 중 하나로 설정한다. 다른 헤더로 자동 대체하지 않는다. 선택한 헤더에 유효한 번호가 없으면 `caller_number`는 `null`이다. 이 번호는 장비가 제공한 표시 정보로 취급한다.

백엔드는 통화 시작·종료 메타데이터를 `VOICE_AGENT_CALLS_DIR`의 암호화 파일에 보존하고 생성 후 30일에 삭제한다. 시작만 기록된 통화는 `incomplete`로 표시한다. 과거 통화의 번호는 복원할 수 없다.

조회는 백엔드 호스트의 loopback에서만 허용하며 `Authorization: Bearer <VOICE_AGENT_WEB_ACCESS_TOKEN>`이 필요하다.

```http
GET /operator/inbound-calls?limit=50&offset=0 HTTP/1.1
Authorization: Bearer <token>
```

응답 `items`는 최신 시작 시각순이며 `session_id`, `started_at`, `ended_at`, `status`, `caller_number`를 담는다. `next_offset`이 `null`이면 마지막 페이지다. `limit`은 1~100, `offset`은 0 이상이다. 보존 저장소가 손상되었거나 준비되지 않았으면 내용 대신 503을 반환한다. 전화번호를 URL·운영 로그·파일명에 넣지 않는다.
