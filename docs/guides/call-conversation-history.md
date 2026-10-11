# 통화별 대화내역 조회

운영자는 통화의 `session_id`로 사용자 최종 전사와 AI 최종 응답을 조회할 수 있다. 외부 착신과 AI 발신 모두 같은 형식이다. 이 API는 로컬 운영 경계에만 열며 외부 프록시에 공개하지 않는다.

```http
GET /operator/calls/{session_id}/conversation
Authorization: Bearer <VOICE_AGENT_WEB_ACCESS_TOKEN>
```

성공 응답 예시는 다음과 같다. `session_id`는 UUID이고, `turn_index`는 0부터 시작한다. `speaker`는 `user` 또는 `assistant`다.

```json
{
  "session_id": "00000000-0000-4000-8000-000000000001",
  "turns": [
    {"turn_index": 0, "speaker": "user", "text": "합성 질문", "created_at": "2026-10-11T00:00:00+00:00"},
    {"turn_index": 0, "speaker": "assistant", "text": "합성 답변", "created_at": "2026-10-11T00:00:01+00:00"}
  ]
}
```

응답은 보존 파일에 실제로 있는 최종 텍스트만 포함한다. AI 응답이 없는 턴에는 사용자 전사만 있고, 녹취·부분 전사는 포함되지 않는다. 텍스트가 없는 통화, 알 수 없는 통화 ID, 만료된 통화는 404를 반환한다. 잘못된 UUID는 422, 인증 누락은 401, 원격 접근은 403, 보존 저장소 장애·손상 파일은 원문 없는 503이다.

텍스트는 AES-GCM 파일에 생성 시각부터 30일 보존된다. 기존의 아직 만료되지 않은 전사·응답도 동일한 키로 읽을 수 있다. API 토큰을 가진 운영자는 대화 원문을 볼 수 있으므로 토큰과 응답을 로그나 공유 문서에 남기지 않는다.
