# 음성 제공자 선택과 통화시험 준비

## 설정

`VOICE_AGENT_VOICE_PROVIDER=onprem`이 기본값이다. 기존 STT → 작업 API → TTS 경로를 사용한다. `openai_live`는 OpenAI Live WebSocket을 사용하고 STT/TTS 모델을 기동하거나 상태 조회하지 않는다. 변경 후 백엔드를 재시작해야 하며 장애 시 다른 제공자로 자동 전환하지 않는다.

|설정|Live 기본값/의미|
|---|---|
|`VOICE_AGENT_OPENAI_API_KEY` 또는 `VOICE_AGENT_OPENAI_API_KEY_FILE`|둘 중 하나 필수. 동시에 설정하면 실패|
|`VOICE_AGENT_OPENAI_LIVE_MODEL`|`gpt-live-1`|
|`VOICE_AGENT_OPENAI_LIVE_VOICE`|`marin`|
|`VOICE_AGENT_LIVE_CONNECT_TIMEOUT_S`|10초; 0 초과 60 이하|
|`VOICE_AGENT_LIVE_DRAIN_TIMEOUT_S`|5초; 웹 입력 종료 후 출력 대기|
|`VOICE_AGENT_LIVE_AUDIO_QUEUE_MAX_MS`|500ms; 40~2000ms. 초과 시 세션 실패|

작업 API 설정, 웹 접근 토큰, 기존 보존 데이터와 같은 암호화 키, HT813 설정은 두 모드에서 공통이다. Live 키는 서버에만 제공하며 웹 클라이언트에 전달하지 않는다. `onprem`에서는 Live 키를 읽지 않는다. Live에서는 미사용 STT/TTS 설정을 검증하지 않는다.

## 키 주입과 실행

기존 [배포 안내](model-serving-observability.md)의 공통 환경값·비밀 디렉터리·데이터 경로를 유지한다. 운영 호스트의 `VOICE_AGENT_SECRETS_DIR` 아래에 기존 `task_api_key`, `web_access_token`, `data_encryption_key`를 준비하고, Live만 `openai_api_key` 파일을 추가한다. 파일 권한 0600, 상위 디렉터리 0700을 사용한다. 키를 채팅·Git·명령행 인수에 넣지 말고 호스트에서 보안 편집기 또는 기존 비밀 주입 절차로 기록한다. 기존 보존 데이터를 새 시험 키로 열지 않는다.

```dotenv
VOICE_AGENT_VOICE_PROVIDER=openai_live
VOICE_AGENT_OPENAI_LIVE_MODEL=gpt-live-1
VOICE_AGENT_OPENAI_LIVE_VOICE=marin
```

Compose 경로는 선택값에 따라 자동으로 결정된다. 직접 실행할 때는 `_FILE` 또는 키 환경변수를 사용하지만 Compose에서는 `openai_api_key` secret 파일로 마운트한다.

```bash
python3 scripts/voice_stack.py --env-file /path/to/runtime.env config --quiet
python3 scripts/voice_stack.py --env-file /path/to/runtime.env up -d --build --remove-orphans
python3 scripts/voice_stack.py --env-file /path/to/runtime.env ps
curl --fail http://127.0.0.1:8000/health
```

Docker 권한이 필요한 호스트에서는 해당 명령을 승인된 관리자 권한으로 실행한다. `.env` 안의 선택값을 사용하면 `sudo` 환경변수 필터의 영향을 피할 수 있다. 기존 서비스가 통화 중이면 먼저 통화를 종료한다. 같은 Compose 프로젝트 이름을 사용하며 `--remove-orphans`는 Live 전환 시 미사용 모델 컨테이너를 내린다. 관측 스택은 별도 프로젝트로 유지된다.

온프레미스로 돌아갈 때는 같은 설정 파일을 `VOICE_AGENT_VOICE_PROVIDER=onprem`으로 변경하고 위 명령을 실행한다. 이때 GPU·STT·TTS 준비 확인이 다시 필요하다. 데이터 디렉터리와 암호화 키는 바꾸지 않는다.

Live `/health` 예시는 `{"status":"ready","provider":"openai_live","remote":"unverified"}`이다. `ready`는 로컬 기동과 보존 준비가 됐다는 뜻이며 **키 유효성·모델 사용 권한·OpenAI 연결 성공을 의미하지 않는다**. 건강 조회는 유료 세션을 열지 않는다. 실제 연결 중에는 `remote=connected`, 세션 실패 후에는 `unavailable`이 표시된다.

## 대화와 종료 의미

전화에서는 입력 수신과 출력 재생을 동시에 수행하며 기존 턴 VAD의 입력 차단을 적용하지 않는다. 8kHz G.711 ↔ 내부 16kHz PCM ↔ Live 24kHz PCM을 상태 유지 방식으로 변환한다. 출력은 20ms 프레임으로 RTP에 전달한다. 음성 재생 중 말을 해도 입력 전송은 계속되며, 모델의 발화 결정과 실제 장비 에코 특성은 실통화에서 확인해야 한다.

웹은 기존 인증 subprotocol, `start`, 순번 4바이트 + PCM 이진 메시지, `end`, `cancel`을 유지한다. Live의 `end`는 입력을 닫고 설정된 시간만큼 출력을 기다린다. 대기 중 `cancel` 또는 연결 해제는 종료를 우선한다. `end` 뒤에 새 음성을 보내면 취소된다.

부분 전사는 `LiveTranscript` 이벤트로 방향·`start_ms`·`end_ms`·`partial=true`를 함께 전달한다. 기존 최종 턴으로 간주하면 안 된다. 위임 이벤트에는 작업 텍스트가 없으므로 현재 세션의 제한된 전사 문맥을 사용하며, 요청이 불명확하거나 작업 API가 실패하면 성공으로 안내하지 않는다. 동일 위임 ID는 한 번만 실행한다.

## 기록과 관측

입력, 생성 출력, 실제 송신 완료 출력은 각각 `input`, `generated`, `sent` 방향으로 최대 10초씩 암호화 보존한다. 샘플 위치와 방향을 기록하여 취소로 전송되지 않은 생성 음성을 구분한다. 전사는 시간·방향·부분성을 보존한다. AES-GCM과 생성 후 30일 삭제 정책은 유지된다. 보존 실패는 세션 중단으로 처리한다.

전화 대화 조회는 기존 `turns`와 Live `segments`를 구분한다. [조회 안내](call-conversation-history.md)를 참조한다. 웹 전사는 전화 조회 API에 노출되지 않는다.

내용·키·전화번호가 없는 지표:

- `voice_live_audio_seconds_total{direction}`: 입력/생성/송신 오디오 길이.
- `voice_live_output_queue_seconds`: 현재 출력 대기량.
- `voice_live_media_delay_seconds`: 출력 프레임 수신 후 송신 완료까지의 내부 지연.
- `voice_live_failures_total{reason}`: 큐 초과/시간 초과/기타 실패.
- `voice_live_finalizations_total{status}`: 최종 사용량 수신 또는 불완전 종료.
- `voice_live_last_session_usage_seconds`: 마지막 세션의 누적 사용량 스냅샷. 반복 이벤트 값을 합산하면 안 된다.

종료 시 `session.close`를 보내고 최대 1초간 `session.closed`를 기다린다. 미수신은 사용량 최종 확정 실패로 표시하며 성공으로 추측하지 않는다. 로컬 자원 종료와 공급자 최종 과금 확정은 구분한다.

## 실제 API·회선 시험의 다음 입력

로컬 모의 시험과 이미지 검증은 실제 서비스 인수시험을 대체하지 않는다. 실제 시험 직전 다음을 확정한다.

1. 실행 호스트와 해당 호스트에 안전하게 주입된 OpenAI 키, 모델 사용 권한.
2. 기존 작업 API·암호화 키·웹 토큰·HT813 설정의 유효성.
3. 시험 참여자, 착신/발신 번호와 허용 목록, 시간창 및 API 비용/세션 시간 상한.
4. 실제 시험 Gate 2 승인과 **매 발신 직전 승인**. 현재 승인된 범위는 localhost 모의 시험뿐이다.

실제 순서는 웹 짧은 음성 → 착신 → 승인된 발신 → 겹쳐 말하기/에코 → 위임 → 종료·기록 조회 → onprem 원복이다. 실패 시 자동 재시도·자동 발신 없이 세션을 종료하고 증거를 남긴다. 실제 내부 지연 p95≤200ms, 큐≤설정값, 종료≤2초 등 계획의 인수 기준은 실제 실행에서 판정한다.
