# Orchestrator Component

## 1. 책임과 현재 기준

orchestrator는 한국어 음성의 STT → 외부 작업 API → TTS 흐름, 웹·HT813 FXO 채널, 단일 세션, 암호화 보존 및 운영 조회를 조정하는 FastAPI 컴포넌트다. 모델 학습이나 웹 사용자 화면을 구현하지 않는다. 작업 API의 chat completion 응답을 받아 음성으로 전달하며 외부 예약·주문 등의 업무 변경을 보장하지 않는다.

현재 공개 기준은 `dev/v0.0.1`의 `080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244`다. 패키지·PRD/SRS 버전 `0.1.0`은 브랜치 이름과 별도이며 배포 완료 표시가 아니다. M6는 부분 실장 검증 상태, M7 착신내역·M8 대화내역은 구현·합성 검증 완료 상태다. 실제 통화와 두 조회 기능의 연결, 현재 운영 배포, 복구·장기 품질은 미검증이다. 과거 실장 결과와 한계는 [공개 기준·증거 요약](../../docs/guides/service-readiness-baseline.md)을 따른다.

## 2. 런타임과 구조

Python `>=3.11,<3.13`, FastAPI, asyncio를 사용한다. 정확한 의존 범위와 pytest 설정은 [pyproject.toml](pyproject.toml)에 있다. 프로세스는 단일 worker이며 웹·전화를 합쳐 활성 세션 1개를 허용한다. GPU Compose는 STT/TTS를 별도 상주 서비스로 실행하고 백엔드는 HTTP 어댑터를 사용한다. 모델 엔드포인트를 둘 다 생략하면 로컬 모델 어댑터가 선택된다.

|경로 (`src/voice_agent/`)|책임|
|---|---|
|`contracts/`|PCM·세션·이벤트·오류·취소·STT/작업/TTS Protocol|
|`core/orchestrator.py`|제한 버퍼, 단계별 시간 제한, 한 발화와 전화 다중 턴 조정|
|`adapters/`|faster-whisper, MeloTTS, 외부 작업 API, 원격 모델 HTTP 경계|
|`channels/web/voice.py`|인증된 WebSocket 음성 프레임과 이벤트|
|`channels/ht813/`|직접 SIP/UDP·RTP·DTMF, 착신·발신, 턴 구분, 운영 API|
|`infrastructure/`|AES-GCM 보존·조회·만료 및 지표·추적|
|`bootstrap.py`|구체 구현과 수명 주기 조립|
|`config.py`, `main.py`, `__main__.py`|설정 검증, ASGI 앱, 단일 worker 실행|

contracts는 다른 애플리케이션 모듈에 의존하지 않고 core는 contracts를 사용한다. adapters/channels는 contracts를 구현하며 core 내부를 import하지 않는다. bootstrap이 구체 구현을 조립하며 채널은 모델 어댑터를 직접 호출하지 않는다. `channels/asterisk/`의 잔여 빈 패키지는 현재 전화 배포에 사용하지 않는다.

## 3. 공통 음성·전화 계약

- 내부 음성은 16 kHz·모노·PCM16이다. `AudioChunk`는 UUID 세션 ID, 0부터 시작하는 연속 번호, 형식, 최대 1초 바이트를 갖는다. HT813 G.711 PCMU/PCMA 8 kHz와 MeloTTS 44.1 kHz 출력은 각 경계에서 내부 PCM으로 변환한다.
- `SingleSessionGate`는 웹·전화의 단일 점유 슬롯이다. 전화는 발신 시도 수락 또는 착신 수락부터 미디어·SIP 정리까지 슬롯을 유지한다. 버퍼는 유한하고 시간 제한·취소는 대기와 출력 정리를 포함한다.
- 웹 `VoiceOrchestrator.run()`은 한 발화, 전화 `run_call()`은 같은 통화의 유한 발화를 순차 처리한다. 전화의 발화 종료는 통화 종료가 아니다. 성공한 이전 턴의 최종 전사·응답만 같은 통화 메모리에 보유하고 종료 시 정리한다.
- 작업 어댑터는 승인된 HTTPS 호스트의 `/v1/chat/completions`로 현재 최종 전사와 같은 통화의 이전 최종 전사·응답을 보낸다. 이전 통화, 부분 전사, 음성 원본은 보내지 않는다. Bearer 키를 사용하며 자동 재시도나 응답 본문 로깅은 하지 않는다.
- 전화 턴 경계 기본값은 RMS 400, 연속 무음 800 ms, 최대 발화 15,000 ms다. 처리·송출 중 입력을 다음 턴으로 재사용하지 않는다. 상대 BYE·운영자 취소·오류에서 모델·송출·점유를 정리한다. DTMF는 RFC 4733 경계로 전달한다.

## 4. 웹·HT813 인터페이스

`/voice` WebSocket은 연결 수락 전에 `voice-agent`와 `token.<토큰>` subprotocol을 검사하며 응답에는 `voice-agent`만 보낸다. 첫 JSON `{"type":"start"}`에 서버가 `session_id`를 반환한다. 이진 프레임은 4바이트 big-endian 순서 번호와 내부 PCM 데이터다. `{"type":"end"}`는 발화 입력 종료, `{"type":"cancel"}`은 취소이며 이벤트는 `{"type":"event","event":...}`다.

발신은 SIP/UDP INVITE·ACK·BYE/CANCEL, Digest 도전, SDP G.711과 RTP를 사용한다. 번호 형식은 3~15자리 숫자와 선택적 선행 `+`이며 `*`·`#` 기능 코드를 거부한다. 저수준 정책은 명시 접두사도 표현하지만 **운영 발신 API는 `VOICE_AGENT_HT813_ALLOWED_EXACT`의 정확한 번호만** 허용한다. 발신 허용 설정이 없으면 발신 객체를 만들지 않는다.

착신은 `VOICE_AGENT_HT813_INBOUND_ENABLED=true`일 때 독립 활성화한다. 설정된 HT813 FXO 피어 IP·SIP 포트만 수용하고, 미디어 주소가 피어와 다르거나 G.711이 없으면 거부한다. 다른 웹/전화 세션이 점유 중이면 `486 Busy Here`다. Caller ID와 미표시 여부는 접근 필터가 아니다. 정상 INVITE에는 `100 Trying`·Contact 포함 `200 OK`를 보내고 ACK 뒤 음성을 시작한다. ACK 전 `200 OK` 재전송, 초기 CANCEL의 `200`/`487`, 상대 BYE의 `200`, 미디어 오류·ACK 시간 초과·종료 시 자원 회수를 구현한다. 앱 종료 중 BYE 응답 대기·재전송과 실제 FXO Idle까지 보장하지는 않는다.

실제 착신 대화·발신 연결의 과거 부분 성공은 있지만 현재 후보의 반복 음성·DTMF·정밀 종료·Caller ID 설정은 별도 실장 검증 대상이다. FXS→에이전트와 FXS 독립 발신은 첫 전화 개시 범위 밖이다.

## 5. 운영 API와 두 조회 기능

[operator.py](src/voice_agent/channels/ht813/operator.py)는 모든 운영 요청에 loopback 클라이언트와 `Authorization: Bearer <VOICE_AGENT_WEB_ACCESS_TOKEN>`을 요구한다. 외부 프록시로 공개하지 않는다. 발신 비활성 상태에서도 retention과 조회 라우터는 조립된다.

|API|성공 결과와 한계|
|---|---|
|`POST /operator/calls`|JSON `{"number":"<정확한 허용 번호>"}`, 202 및 `session_id`, `status`|
|`GET /operator/calls/{session_id}`|현재 메모리에 보유한 발신 제어 기록의 상태. 영속 발신 목록이 아님|
|`DELETE /operator/calls/{session_id}`|현재 발신 취소 요청, 202|
|`GET /operator/inbound-calls?limit=50&offset=0`|최신순 `items`, `next_offset`. limit 1~100, offset ≥0|
|`GET /operator/calls/{session_id}/conversation`|발착신 전화의 보존 최종 텍스트 `session_id`, `turns`|

착신 항목은 `session_id`, `started_at`, `ended_at`, `status`, `caller_number`를 포함한다. 시작만 기록돼 있으면 `incomplete`이고 종료 기록은 `ended` 또는 `failed`다. 수락된 착신은 무발화여도 기록하지만 백엔드 중지 중의 부재중 전화, 수락되지 않은 시도와 과거 번호·상태를 소급 생성하지 않는다.

Caller ID는 `VOICE_AGENT_HT813_CALLER_ID_HEADER`의 `from`, `p-asserted-identity`, `p-preferred-identity`, `disabled` 중 선택한 헤더만 읽는다. HT813의 `Caller ID Transport Type`과 맞춰야 한다. `sip:`/`tel:` URI의 7~15자리 숫자와 선택적 `+`를 추출하고 SIP 계정 ID와 같은 값, 미표시·비정상 값은 `null`이다. 다른 헤더로 자동 대체하지 않는다. 이는 장비 표시 정보이며 신원 인증 결과가 아니다.

대화 항목은 `turn_index`, `speaker` (`user`/`assistant`), `text`, `created_at`이다. 정렬은 턴 번호 → 생성 시각 → 같은 시각일 때 사용자 우선이다. 답변이 없으면 사용자 전사만 남을 수 있다. 웹 세션·부분 전사·녹취는 이 API에서 제공하지 않는다. 발신은 별도 목록이 없으므로 생성 응답의 `session_id`를 운영자가 보관한다.

|오류|계약|
|---|---|
|401|loopback 요청의 Bearer 인증 누락·불일치|
|403|원격 접근 또는 발신 목적지 미허용|
|404|현재 발신 제어 ID 없음, 또는 대화 텍스트 없음·미확인 ID·전체 만료|
|409|새 발신 시 웹/전화 세션 점유 중|
|422|잘못된 UUID·페이지 값·요청 형식·번호 형식|
|503|발신 미설정 또는 보존 미준비·손상 등 조회 불가|

빈 착신 목록은 200과 빈 `items`다. 파일 손상은 원문 없는 503으로 응답하며 디스크 경로나 키를 응답하지 않는다. 조회는 디렉터리를 스캔하므로 다른 세션 파일 손상도 전체 조회를 실패시킬 수 있다. 자세한 사용법은 [착신내역 가이드](../../docs/guides/inbound-call-history.md)와 [대화내역 가이드](../../docs/guides/call-conversation-history.md)를 따른다.

## 6. 보존 계약

[retention.py](src/voice_agent/infrastructure/retention.py)는 턴별 입력·출력 PCM, 최종 전사·응답, 착신 시작·종료 메타데이터를 무작위 이름의 AES-256-GCM 파일로 쓴다. 파일별 12바이트 nonce와 인증된 UTC 생성 시각을 사용하며 임시 파일에서 원자적으로 게시한다. 부분 전사와 통화 문맥은 별도 저장하지 않는다.

키는 Base64로 인코딩한 32바이트이며 누락·형식 오류면 기동하지 않는다. 새 디렉터리는 `0700`, 파일은 `0600`이다. 저장 경로가 심볼릭 링크이거나 기존 권한이 넓으면 준비 완료로 전환하지 않는다. 생성 시각 + 정확히 30일에 만료하며 시작·주기 스윕과 조회에서 만료를 적용한다. 기본 삭제 주기는 3600초, 허용 범위는 60~86400초다. 시작·종료·텍스트 파일은 각각 생성 시각을 가져 일부만 남을 수 있다.

삭제 감사에는 익명 ID·종류·생성/삭제 시각·결과·실패 사유만 기록한다. 저장·삭제 실패는 보존 준비 상태를 내리고 신규 음성 처리를 막는다. 기존 보존 키를 임의로 교체하면 기존 암호문을 복호화할 수 없다. 재부팅 후 동일 키 주입과 백업·복구는 별도 운영 설계·검증 대상이다.

## 7. 설정·배포 매핑

[config.py](src/voice_agent/config.py)의 `Settings.from_env`가 실제 환경변수 소비 계약이다. [.env.example](../../.env.example)은 이전 조사 항목도 포함하므로 전체 항목이 구현돼 있다고 해석하지 않는다. `.env` 자동 로딩을 가정하지 말고 실행 환경으로 주입한다.

|설정|소스 기본값·제약 / GPU Compose 매핑|
|---|---|
|`VOICE_AGENT_API_HOST`, `VOICE_AGENT_API_PORT`|직접 실행 기본 `127.0.0.1:8000`; Compose 명령은 이를 고정. 예제 파일의 host는 `0.0.0.0`이므로 직접 실행 시 확인|
|`VOICE_AGENT_STT_ENDPOINT`, `VOICE_AGENT_TTS_ENDPOINT`|함께 지정하거나 모두 생략; Compose는 `http://127.0.0.1:8101`, `:8102`|
|`VOICE_AGENT_STT_MODEL_ID`, `VOICE_AGENT_TTS_SPEED`|STT small/medium; TTS 기본 1.25, 범위 0.5~2|
|`VOICE_AGENT_TASK_API_BASE_URL`, `VOICE_AGENT_TASK_APPROVED_HOST`, `VOICE_AGENT_TASK_MODEL`|필수 작업 API 설정; Compose가 전달|
|`VOICE_AGENT_TASK_API_KEY`, `VOICE_AGENT_WEB_ACCESS_TOKEN`, `VOICE_AGENT_DATA_ENCRYPTION_KEY`|직접 값 또는 각각 `_FILE`, 동시 지정 금지. Compose는 `/run/secrets/*`|
|`VOICE_AGENT_HT813_HOST`, `VOICE_AGENT_HT813_LOCAL_IPV4`, `VOICE_AGENT_HT813_SIP_USER_ID`|전화 활성화 시 필수; Compose는 항상 필수 입력|
|`VOICE_AGENT_HT813_ALLOWED_EXACT`, `VOICE_AGENT_HT813_INBOUND_ENABLED`, `VOICE_AGENT_HT813_CALLER_ID_HEADER`|Compose 전달. 기본 빈 발신 목록, false, from|
|FXO/발신/착신 SIP·RTP 포트|소스 기본 FXO 5062, 발신 5060/4000, 착신 5061/4002. backend Compose에는 포트 조정 변수 전달 없음|
|`VOICE_AGENT_RECORDINGS_DIR`, `VOICE_AGENT_TRANSCRIPTS_DIR`, `VOICE_AGENT_CALLS_DIR`, `VOICE_AGENT_DELETION_AUDIT_LOG`|직접 실행 `./data/*`; Compose `/data/recordings`, `/data/transcripts`, `/data/calls`, `/data/deletion-audit.jsonl`|
|`VOICE_AGENT_DATA_DIR`, `VOICE_AGENT_SECRETS_DIR`|Compose 호스트 입력: `/data` 볼륨과 세 비밀 파일 경로. Settings가 직접 소비하지 않음|
|`VOICE_AGENT_METRICS_HOST`, `VOICE_AGENT_METRICS_PORT`, `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`|선택 지표/추적; Compose가 관리망 주소·8001·OTLP 목적지를 주입|

그 밖에 VAD·단계 시간 제한·보존 삭제 주기·SIP 비밀번호·저수준 접두사 설정은 소스에서 읽지만 현재 backend Compose의 `environment`에는 전달하지 않는다. 단순히 호스트 `.env`에 추가했다고 컨테이너 동작이 바뀌지 않는다. Compose 변경이 필요하면 생성·배포 경계까지 검토한다. Asterisk 항목과 일부 모델 조사 항목은 현재 Settings의 운영 설정이 아니다.

[compose.backend.yaml](../../deploy/gpu/compose.backend.yaml)은 모델 health 의존, host network, `restart: unless-stopped`, loopback API 및 `/data` 영속 마운트를 제공한다. 이 설정 자체는 호스트 재부팅 후 비밀 파일 복구·모델 캐시 영속성·실제 전화 준비를 보장하지 않는다. 관측 대상은 [생성 스크립트](../../scripts/render_observability_targets.py)를 통해 만들며 생성 결과를 직접 편집하지 않는다.

## 8. 상태·개발 명령·검증

`/health`는 조립·보존 준비와 원격 모델을 사용하는 경우 STT/TTS `/ready` 결과를 반환한다. 상태는 `ready`, `degraded`, `stopping`이다. 외부 작업 API·PSTN/HT813 연결 성공은 검사하지 않는다. `/metrics`와 선택적 독립 지표 포트를 제공하고 STT·작업 API·TTS span을 기록한다. 전사·답변·오디오·비밀을 추적 속성이나 지표 라벨에 넣지 않는다.

필요한 의존성과 필수 설정을 준비한 뒤 저장소 루트에서 실행한다.

```sh
PYTHONPATH=apps/orchestrator/src python -m voice_agent
python -m pytest -c apps/orchestrator/pyproject.toml tests/units/orchestrator/testcodes
```

단위 시험은 `tests/units/orchestrator/testcodes/`에서 `*.test.py`로 수집한다. 외부 모델·HTTP·SIP/RTP는 fake로 격리하며 결과를 해당 시험 로그에 기록한다. 파일·실전화·배포 통합 시험은 별도 Gate 1/2 및 구체 실행안 승인을 따른다. 현재 배포와 품질의 사실 확인은 [OPS-008 계획](../../docs/records/1_plans/VOIC-OPS-008-plan.md), 운영 절차는 [모델 상주·관측 가이드](../../docs/guides/model-serving-observability.md)를 따른다.

## 9. 관련 결정

- [ADR-003](../../docs/records/3_decisions/ADR-003-initial-task-backend-and-operating-constraints.md): 작업 API·동시 1세션·30일 보존
- [ADR-005](../../docs/records/3_decisions/ADR-005-web-voice-transport-and-access.md): 웹 전송·토큰
- [ADR-007](../../docs/records/3_decisions/ADR-007-ht813-multiturn-call-lifecycle.md): 전화 다중 턴·같은 통화 문맥
- [ADR-008](../../docs/records/3_decisions/ADR-008-local-encrypted-retention.md): 로컬 암호화 보존
- [ADR-009](../../docs/records/3_decisions/ADR-009-ht813-all-inbound-agent.md): 전체 FXO 착신
- [ADR-011](../../docs/records/3_decisions/ADR-011-warm-model-services-observability.md): 모델 상주·관측 배치
- [ADR-012](../../docs/records/3_decisions/ADR-012-encrypted-call-index-for-history.md): 암호화 착신 인덱스·대화 조회
