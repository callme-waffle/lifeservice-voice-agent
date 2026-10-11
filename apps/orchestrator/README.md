# Orchestrator Component

## 1. 책임

orchestrator는 한국어 음성 기반 작업 에이전트의 단일 FastAPI 애플리케이션 컴포넌트다.

이 컴포넌트는 다음 책임을 가진다.

- STT → 작업 처리 → TTS 비동기 흐름 조정
- 웹 및 HT813 FXO 발신·착신 채널의 세션을 공통 내부 계약으로 변환
- 기존 한국어 STT/TTS 모델을 교체 가능한 어댑터로 연결
- 작업 처리 API를 교체 가능한 어댑터로 연결
- 단일 활성 세션 제한, 취소, 시간 제한, 역압 및 오류 전파
- 녹취·원문 데이터의 30일 보존 후 삭제 수명 주기
- 애플리케이션 시작·종료, 준비 상태 및 자원 정리

이 컴포넌트는 STT/TTS 모델을 학습하거나 프론트엔드 UI를 구현하지 않는다.

## 2. 런타임

- 언어: Python
- 웹 프레임워크: FastAPI
- 실행 모델: 초기에는 단일 프로세스 모듈형 모놀리스였으며, M6-S3 배포에서는 STT/TTS를 별도 상주 컨테이너로 분리
- 비동기 모델: asyncio 기반
- 추론 장치: 준비 예정인 NVIDIA GeForce GTX 1080 Ti
- 초기 활성 세션 제한: 웹과 전화를 합쳐 1개

Python 및 주요 라이브러리의 버전 범위는 `pyproject.toml`을 따른다. STT/TTS 모델 런타임은 M4 환경 검증 뒤 결정한다.

## 3. 아키텍처

디렉터리와 의존 방향은 [ADR-004](../../docs/records/3_decisions/ADR-004-ht813-direct-outbound-telephony.md)가 계승한 모듈 규칙을 따른다. 아래 `ht813/`은 계획된 경계이며, 구현 전까지 기존 `asterisk/` 빈 골격이 남아 있을 수 있다.

    apps/orchestrator/
    ├── README.md
    ├── pyproject.toml
    └── src/voice_agent/
        ├── main.py
        ├── bootstrap.py
        ├── config.py
        ├── api/
        ├── contracts/
        ├── core/
        ├── adapters/
        │   ├── stt/
        │   ├── task/
        │   └── tts/
        ├── channels/
        │   ├── web/
        │   └── ht813/
        └── infrastructure/

의존 방향은 다음 규칙을 적용한다.

1. contracts는 다른 애플리케이션 모듈에 의존하지 않는다.
2. core는 contracts에만 의존한다.
3. adapters와 channels는 contracts를 구현하며 core의 내부 구현을 import하지 않는다.
4. bootstrap만 구체 구현을 선택하고 객체 수명 주기를 조립한다.
5. 채널은 모델 어댑터를 직접 호출하지 않는다.
6. core는 웹, SIP/RTP 또는 특정 모델의 프로토콜을 알지 않는다.

## 4. 모듈별 책임

### api

- FastAPI 애플리케이션 팩토리
- 상태 확인과 준비 상태 엔드포인트
- 공통 예외 처리 및 애플리케이션 수명 주기 진입점

### contracts

- 오디오 형식과 청크
- 세션 문맥과 상태
- 이벤트 봉투와 순서 정보
- 표준 오류와 취소 의미
- STT, 작업 처리 및 TTS 비동기 Protocol

### core

- STT → 작업 처리 → TTS 오케스트레이션
- 세션 상태 전이
- 제한 큐, 시간 제한, 취소 및 오류 전파
- 단일 활성 세션 제한

### adapters

- stt: 선정된 기존 한국어 STT 모델을 내부 계약으로 변환
- task: 로컬 `.env`에 지정한 HTTPS 작업 처리 API를 내부 계약으로 변환
- tts: 선정된 기존 한국어 TTS 모델을 내부 계약으로 변환

인증 비밀은 환경 변수 또는 런타임 비밀 저장소에서만 주입하며 문서·코드·로그에 기록하지 않는다.

### channels

- web: HTTP/WebSocket 요청과 오디오 스트림을 내부 계약으로 변환
- ht813: FXO를 통한 허용 번호 외부 발신과 모든 외부 착신을 별도 SIP 경계에서 수용하며, 통화 상태·RTP 오디오·DTMF를 내부 계약으로 변환한다. 착신 Caller ID는 접근 필터로 사용하지 않고 HT813 피어를 검증한다. 한 통화에서는 연속 음성 턴과 상대방 정상 종료를 처리한다. FXS→에이전트는 범위 밖이다.
- 외부 착신→FXS 링은 최신 M6 요구로 대체됐다. FXS 외부 발신은 전화기가 물리적으로 연결되고 별도 승인된 뒤 검증한다.

### infrastructure

- 오디오 코덱·샘플레이트·채널 변환
- GPU 장치 및 자원 상태
- 로그·메트릭·추적 상관관계
- 30일 보존 데이터의 만료 및 삭제 지원

## 5. 외부 의존성

M4 검증을 통해 모델·전화 경계의 정확한 패키지와 버전을 결정한다.

- FastAPI 및 ASGI 서버
- Uvicorn WebSocket 프로토콜 런타임 `wsproto` (기본 `uvicorn` 설치만으로는 WebSocket 처리 불가)
- 데이터 검증 라이브러리
- 비동기 HTTP/WebSocket 클라이언트
- 선정할 STT/TTS 모델 런타임
- 오디오 변환 라이브러리
- SIP/RTP 발신·착신 경계 구현 또는 해당 기능을 제공하는 검증된 라이브러리 (구체 선택은 M4 계약 후 결정)
- pytest 및 비동기 테스트 지원

## 6. 설정

설정은 코드와 분리하고 시작 시 검증한다. 최소 설정 범주는 다음과 같다.

- 애플리케이션 호스트·포트 및 로그 수준
- 활성 세션 제한
- STT/TTS 모델 식별자, 모델 경로, 장치 및 정밀도
- 작업 처리 API 기본 주소, 모델 및 시간 제한
- 작업 처리 API 인증 비밀
- HT813 FXO 피어 주소·SIP/RTP 포트, 발신 허용 목적지, 전체 착신 수신 및 피어 접근 제어 설정
- 내부 오디오 형식과 채널별 변환 정책
- 녹취·원문 저장 위치, 암호화 및 30일 만료 정책

비밀값은 예제 설정에 실제 값으로 포함하지 않는다.

저장소 루트의 [.env.example](../../.env.example)을 입력 양식으로 사용한다.

    cp .env.example .env

실제 .env는 Git 추적 대상이 아니다. 현재 Asterisk 서버는 없으므로 해당 연결 값은 비워 둔다. HT813 설정은 확인된 값만 기록하고, API 키와 비밀번호는 .env 또는 런타임 비밀 주입으로만 제공한다.

## 7. 인터페이스

M4의 공통 계약은 `src/voice_agent/contracts/`에 있다. 웹 및 HT813는 이 계약으로 변환하며, 외부 경계의 상세 시나리오는 SRS에서 추적한다.

- 웹: 상태 확인용 HTTP와 실시간 음성용 WebSocket을 기본 후보로 사용
- HT813: FXO 로컬 SIP 포트 `5062/UDP`는 관리 화면 관찰값이다. 직접 SIP/RTP 피어링, 전화번호 전달, 실제 코덱 협상과 통화 종료는 실장 검증 전 미확정이다. 전체 외부 착신의 에이전트 직접 SIP 수신은 ADR-009에 따라 M6 구현 대상이며 현재 장비 호환성은 미검증이다.
- STT: 오디오 입력, 부분·최종 전사, 취소 및 표준 오류
- 작업 처리: 전사 텍스트와 세션 문맥 입력, 구조화된 응답 텍스트 출력
- TTS: 응답 텍스트 입력, 순서가 있는 오디오 청크 출력

모든 스트리밍 경계는 session_id, 순서, 오디오 형식, 시간 제한, 취소 및 종료 의미를 보존해야 한다.

### M4 공통 계약

- 내부 기준 음성은 16 kHz·모노·16비트 PCM이다. `AudioChunk`는 UUID 세션 ID, 0부터 시작하는 연속 번호, `AudioFormat`, 최대 1초 분량의 불변 바이트를 갖는다. 입력 HT813 G.711 PCMU/PCMA는 8 kHz·모노로 표시하고 내부 PCM 변환은 추후 인프라 경계에서 수행한다. MeloTTS 출력 44.1 kHz도 같은 경계에서 변환해야 한다.
- `SessionContext`는 웹 또는 HT813 FXO 채널과 UTC 생성 시각을 갖는다. `EventEnvelope`는 세션 ID, 0 이상의 순서 번호 및 세션 상태·통화 상태·전사·작업 결과·DTMF·공개 오류 중 하나를 전달한다. 이벤트 발행자는 채널별 순서 번호를 증가시켜야 한다.
- `SingleSessionGate`는 웹과 전화가 공유하는 단일 점유 슬롯이다. `BoundedAudioBuffer`는 유한 크기 FIFO이며 송신자는 공간이 생길 때까지 기다린다. `CancellationToken`은 대기 중인 송·수신을 깨우고 `finish()`는 정상 종료를 알린다. 오디오 버퍼는 단일 생산자·단일 소비자용이다.
- STT·작업 처리·TTS는 `ports.py`의 비동기 Protocol을 따른다. `StepTimeouts`가 각 처리 단계의 양수 제한 시간을 요구한다. 실제 제한 시간 집행과 오류 상태 전이는 M5 코어 책임이다.
- `OutboundCallRequest`의 번호는 3~15자리 숫자와 선택적 선행 `+`만 허용한다. `*`·`#` 기능 코드는 일반 외부 발신 번호로 통과하지 않는다. 발신 전 비어 있지 않은 `AllowedNumberPolicy`의 정확한 번호 또는 명시한 접두사로 승인해야 한다. 실제 허용 목록은 사용자와 확인 후 설정으로 주입한다.
- `CallStatus`는 dialing, ringing, active, busy, failed, ended를 구분한다. SIP 응답을 이 상태로 변환하는 일과 RTP·DTMF 전송은 M5 HT813 채널의 책임이다. 이 계약 테스트는 실제 장비 상호 운용성의 검증 결과가 아니다.

GPU 단독 측정은 [log-05](../../docs/records/2_logs/VOIC-FEAT-001-log-05.md)에 있다. small/medium STT와 MeloTTS 한국어 출력은 확인했으나 3.8 GiB RAM에서 모델 동시 상주와 전화 음성 품질은 미검증이므로 최종 운영 조합은 보류다.

### M5 구현 인터페이스

- `core/orchestrator.py`: `VoiceOrchestrator.run`이 한 세션의 입력 오디오를 제한 버퍼에 넣고 STT→작업 처리→TTS를 호출한다. 단계별 제한 시간, 취소, 공개 오류, 단일 세션 점유 해제를 담당한다.
- `adapters/stt/faster_whisper.py`: 16 kHz PCM을 WAV로 감싸 `faster-whisper` small 또는 medium/int8에 전달한다. `adapters/tts/melo.py`: MeloTTS의 44.1 kHz 모노 WAV를 16 kHz PCM으로 변환해 최대 1초 청크로 낸다. 기본 발화 속도는 1.25배다. 각 호출에서 모델을 로드하며 실제 연속 호출의 RAM·swap·지연은 아직 검증되지 않았다.
- `adapters/task/openai_compatible.py`: 사용자가 승인한 최종 전사 텍스트만 `VOICE_AGENT_TASK_API_BASE_URL`의 `/v1/chat/completions`에 전송한다. 주소의 호스트는 로컬 `VOICE_AGENT_TASK_APPROVED_HOST`와 정확히 일치해야 한다. API 키는 Bearer 헤더로만 주입한다. 자동 재시도는 하지 않으며 응답 본문·비밀을 예외 메시지로 노출하지 않는다.
- `channels/web/voice.py`: `/voice` WebSocket은 `voice-agent`와 `token.<설정 토큰>` subprotocol을 연결 전에 검사하며 응답에는 `voice-agent`만 보낸다. 첫 JSON은 `{"type":"start"}`이고 서버가 UUID `session_id`를 돌려준다. 이후 이진 입력/출력 프레임은 4바이트 big-endian 순서 번호와 16 kHz 모노 PCM16 데이터다. JSON `{"type":"end"}`는 정상 종료, `{"type":"cancel"}`은 취소다. 이벤트는 `{"type":"event","event":...}`로 전송한다. 최대 입력 음성 청크는 1초다.
- `channels/ht813`: 발신 전용 SIP/UDP INVITE·ACK·BYE/CANCEL 및 Digest 도전, SDP G.711 PCMU/PCMA, RTP 음성·RFC 4733 DTMF를 구현했다. `HT813Outbound`는 `AllowedNumberPolicy`가 없는 경우 생성할 수 없고 모든 발신에서 요청 번호를 먼저 검사한다. 고정 로컬 SIP/RTP 포트와 사용자 ID·선택적 SIP 비밀번호를 설정으로 받는다. 실제 HT813의 인증·번호 전달·코덱·회선 점유·DTMF 호환성은 확인되지 않았다.

M5-S4/S5의 fake 경계 단위 검증만 통과했다. M6-S1에서 `config.py`가 런타임 환경변수를 검증하고 `bootstrap.py`가 코어·웹·선택적 HT813 발신 객체를 조립하며, `main.py`가 단일 ASGI 실행 진입점을 제공한다. 전화 허용 번호가 비어 있으면 HT813 발신 객체를 만들지 않는다. 조립 단계는 전화 연결이나 모델 추론을 시작하지 않는다. M6-S1-T3~T6은 [ADR-007](../../docs/records/3_decisions/ADR-007-ht813-multiturn-call-lifecycle.md)의 다중 턴·같은 통화 문맥과 [ADR-008](../../docs/records/3_decisions/ADR-008-local-encrypted-retention.md)의 로컬 암호화 보존 및 [ADR-009](../../docs/records/3_decisions/ADR-009-ht813-all-inbound-agent.md)의 전체 착신을 구현한다. M6의 실브라우저·실장 통합은 별도 Gate 대상이다.

### M6-S1-T3/T4 다중 턴 발신 조립

- `VoiceOrchestrator.run_call()`은 같은 전화 세션에서 각 유한 발화를 순차 처리하고 통화 전체에 걸쳐 이벤트·출력 오디오 순서를 유지한다. 기존 웹 `run()`은 한 발화 동작을 유지한다. 성공한 이전 턴의 최종 전사와 응답만 현재 통화 메모리에 두며, 다음 작업 API 요청의 `messages`에 user/assistant 순서로 넣는다. 통화 종료 뒤 문맥을 지운다.
- `channels/ht813/turns.py`는 16 kHz PCM 에너지, 연속 무음, 최대 발화 길이로 턴을 끝낸다. 기본값은 각각 RMS 400, 800 ms, 15,000 ms이며 `VOICE_AGENT_HT813_VAD_ENERGY`, `VOICE_AGENT_HT813_VAD_SILENCE_MS`, `VOICE_AGENT_HT813_MAX_UTTERANCE_MS`로 조정한다. 무음은 통화 종료 신호가 아니다.
- `OutboundCallManager`는 발신 시도부터 SIP 정리까지 웹과 공유하는 단일 세션을 점유한다. 발신 목적지는 `VOICE_AGENT_HT813_ALLOWED_EXACT`의 정확한 번호만 사용한다. 처리·송출 중 들어온 입력은 다음 턴으로 재사용하지 않고 RTP DTMF와 이벤트 순서를 보존한다. 상대 BYE 또는 운영자 취소에 모델·송출을 취소하고 점유를 해제한다.
- 로컬 운영 진입점은 loopback HTTP 클라이언트에만 열리며 `Authorization: Bearer <VOICE_AGENT_WEB_ACCESS_TOKEN>`을 요구한다. `POST /operator/calls`의 JSON 본문은 `{"number":"<허용된 정확한 번호>"}`이고, 응답의 `session_id`로 `GET /operator/calls/{session_id}` 상태를 보거나 `DELETE /operator/calls/{session_id}`로 취소한다. URL·일반 로그에 목적지 번호를 넣지 않는다. 운영 API를 외부 프록시로 노출하지 않는다.
- `GET /operator/calls/{session_id}/conversation`은 같은 로컬 Bearer 경계에서 보존 중인 최종 사용자 전사·AI 응답을 `turn_index`, `speaker`, `text`, `created_at` 순서화된 항목으로 제공한다. 텍스트 없는 통화·만료·미확인 ID는 404, 손상 파일은 원문 없는 503을 반환한다. [운영 가이드](../../docs/guides/call-conversation-history.md)를 따른다.
- 이 조립은 가짜 SIP/RTP·ASGI 단위 시험으로만 검증됐다. 실제 HT813 인증·코덱·번호 전달·양방향 음성과 지연은 M6-S2의 별도 Gate 2 후 판정한다.

### M6-S1-T5 모든 FXO 착신 수신

- `VOICE_AGENT_HT813_INBOUND_ENABLED=true`일 때 앱 수명 주기에 HT813 직접 SIP/UDP 수신기를 시작한다. 기본 로컬 착신 SIP 포트는 5061, RTP 포트는 4002이며 발신 로컬 5060/4000과 충돌하면 설정을 거부한다. 발신 목적지 허용 목록이 비어도 착신 수신은 독립적으로 설정할 수 있다.
- 수신기는 설정한 HT813 FXO 피어 IP와 SIP 포트에서 온 패킷만 처리한다. Caller ID 값·미표시 여부는 접근 필터가 아니다. SDP의 미디어 주소가 신뢰 피어와 다르거나 G.711 PCMU/PCMA가 없으면 통화 전에 거부한다. 다른 활성 웹/전화 세션이 있으면 SIP `486 Busy Here`를 보낸다.
- 정상 INVITE에 `100 Trying`과 G.711 SDP를 담은 `200 OK`로 응답하고 ACK 뒤 발신과 같은 음성 다중 턴 코어에 연결한다. `200 OK`에는 설정한 로컬 SIP 사용자·주소·착신 포트의 `Contact`를 포함해 피어의 ACK 목적지를 제공한다(RFC 3261 §12.1.1). 초기 CANCEL에는 `200`/`487`, 상대 BYE에는 `200`으로 답하고, RTP 실패·ACK 시간 초과·앱 종료에도 RTP와 단일 세션 점유를 정리한다. UDP `200 OK`는 ACK 전 재전송한다. 앱 정상 종료 시 활성 착신에는 소켓을 닫기 전에 BYE를 한 번 전송하며, 전송 실패에도 로컬 미디어·점유·소켓을 회수한다. 종료 중 BYE 응답 대기·재전송 및 장비 회선 해제 확인은 현재 보장하지 않는다.
- 현재 구현 결과는 가짜 SIP/RTP 피어의 단위 검증이다. HT813의 실제 `Unconditional Call Forward to VoIP` 대상, 인증·코덱·번호 표시·회선 상태, 앱의 SIP/RTP 도달성은 확인되지 않았다. 장비 설정 백업·변경안과 Gate 2를 확정하기 전에는 수신기를 실제 회선에 연결하지 않는다. 보존 기능 T6을 완료하기 전에는 실제 음성 시험을 하지 않는다.

### M6-S1-T6 암호화 보존

- `VOICE_AGENT_DATA_ENCRYPTION_KEY`는 런타임에 주입한 32바이트 키의 Base64 인코딩이며 비어 있거나 길이가 다르면 기동하지 않는다. 키 값·실제 `.env`는 로그나 버전 관리에 넣지 않는다. `cryptography`의 AES-256-GCM으로 각 파일마다 새 12바이트 nonce를 사용하고 생성 시각을 인증 헤더에 둔다.
- 웹과 전화의 각 턴에서 입력·출력 16 kHz PCM, 최종 전사, 에이전트 응답을 익명 파일명으로 나누어 암호화한다. 중간 전사와 같은 통화의 문맥은 별도 파일로 기록하지 않는다. `VOICE_AGENT_RECORDINGS_DIR`, `VOICE_AGENT_TRANSCRIPTS_DIR`, `VOICE_AGENT_DELETION_AUDIT_LOG`로 경로를 지정하며 새 디렉터리는 `0700`, 파일은 `0600`으로 만든다. 기존 경로의 접근 권한이 넓거나 심볼릭 링크이면 준비 상태로 전환하지 않는다.
- UTC 생성 시각에서 정확히 30일째 시작 스윕과 주기 스윕에서 삭제한다. 기본 스윕 주기는 3600초이며 `VOICE_AGENT_RETENTION_SWEEP_INTERVAL_SECONDS`로 60~86400초 안에서 조정한다. 삭제 감사에는 익명 파일 ID, 종류, 시각, 결과와 원인 코드만 남긴다. 저장·삭제 오류는 공개 응답에 원문이나 키를 포함하지 않으며 보존 준비 상태를 내리고 신규 음성 응답을 중단한다. `/health`의 `degraded` 상태는 이 보존 경계 오류를 뜻할 수 있다.
- 암호화 코덱, 만료 판정, 가짜 저장소·시계·스케줄러를 이용한 단위 검증까지 완료했다. 실제 파일 시스템의 권한·원자적 쓰기·삭제 감사를 확인하는 통합 검증은 별도 Gate 2 이후 실행한다.

## 8. 개발 명령

M5 구현 경계: 코어는 `SpeechToText`, `TaskProcessor`, `TextToSpeech`와 `EventSink` 계약만 호출한다. 각 단계 제한 시간은 코어가 집행하고, 취소·예외 뒤 단일 세션 점유를 해제한다. 모델·외부 HTTP·웹·SIP/RTP는 각각 어댑터와 채널에서 변환한다. HT813 외부 발신은 빈 허용 목적지 정책으로는 시작할 수 없다. 외부 착신은 Caller ID와 관계없이 설정된 HT813 SIP 피어에서만 수신한다. 모델 동시 상주 배치는 GPU 호스트 RAM 실측 전까지 확정하지 않는다.

M5 단위 검증은 fake 모델, fake HTTP, fake 웹 코어, fake SIP/RTP 피어만 사용한다. 실제 장비 변경·실전화·통합 검증은 M6의 Gate 1과 실행 직전 Gate 2 승인 대상이다.

`pyproject.toml`과 패키지 골격은 M1-S1에서 생성되었고 M6-S1에서 아래 실행 진입점을 구현했다. `.env.example`의 필요한 값을 런타임 환경 변수에 주입한 뒤 단일 작업자 프로세스로 실행한다. 필수 런타임 설정이 누락되면 시작 단계에서 설정 키 이름만 있는 오류로 중단한다. `/health`는 프로세스 조립 상태를 나타내며 외부 모델·작업 API·전화 회선의 준비나 연결 성공을 보증하지 않는다.

M6-S3 분리 배포에서는 `VOICE_AGENT_STT_ENDPOINT`와 `VOICE_AGENT_TTS_ENDPOINT`를 함께 설정해 두 모델의 HTTP 어댑터를 선택한다. 백엔드 컨테이너의 작업 API 키·웹 토큰·보존 암호화 키는 `${KEY}_FILE` 설정으로 `/run/secrets`의 파일을 읽으며, 로컬 개발에서는 기존 환경변수 값도 사용할 수 있다. 이때 기동 전 각 `/ready`가 200인지 검사하고, `/health`는 `stt`·`tts` 상태를 각각 포함한다. 모델 서비스 중 하나가 응답하지 않으면 `degraded`로 표시한다. 두 엔드포인트가 없으면 기존 로컬 모델 어댑터가 유지되며 `/health`의 기존 응답 형식도 유지된다. 작업 API 자체의 실서비스 정상 여부는 `/health`에서 조회하지 않는다. `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`를 설정하면 STT·작업 API·TTS span이 OTLP HTTP로 나간다. 지연 히스토그램은 `/metrics`에, `VOICE_AGENT_METRICS_HOST`를 설정하면 관리망의 독립 포트에도 제공한다. 전사·답변·오디오·비밀은 span 속성이나 메트릭 라벨에 넣지 않는다. 배포 세부 절차는 [모델 상주·관측 가이드](../../docs/guides/model-serving-observability.md)를 따른다.

    python -m voice_agent
    pytest

M4에서 작성하는 단위 테스트는 설치된 Python 환경에서 `python -m pytest`로 실행하며, 실행 여부와 결과는 테스트 로그에 기록한다.

## 9. 테스트 규칙

- 단위 테스트 루트: tests/units/orchestrator/testcodes/
- 단위 테스트 실행 로그: tests/units/orchestrator/logs/
- 통합 테스트 루트: tests/integrations/
- 단위 테스트 파일은 원본 소스 구조를 반영하고 이름은 ORIGIN_FILE_NAME.test.py 형식을 따른다.
- pyproject.toml에서 *.test.py 수집 규칙을 명시한다.
- 테스트는 VOIC-FEAT-001과 계획의 M/S/T 작업 ID를 참조한다.
- 단위 테스트는 외부 모델·API·HT813을 결정론적 fake로 격리한다.
- 실제 외부 경계 테스트는 Gate 1과 Gate 2 승인을 모두 받은 경우에만 수행한다.
- 각 테스트 실행은 대응 로그 파일에 기록한다.

## 10. 운영 및 보안 제약

- 초기 동시 활성 세션은 1개다.
- 녹취와 원문 데이터는 생성 시점부터 30일 보존 후 삭제한다.
- API 키, 장비 자격 정보 및 기타 비밀은 저장소와 로그에 기록하지 않는다.
- 민감한 음성·텍스트는 로그에서 비식별화한다.
- 실제 전화 통합 테스트는 허용된 시험 번호·시간·회선 영향 범위를 정하고 Gate 1 및 실행 직전 Gate 2 승인 후에만 수행한다.
- GPU 성능 완료 판정은 GTX 1080 Ti 호스트 접근 정보가 제공된 뒤에만 가능하다.

## 11. 관련 기록

- [VOIC-FEAT-001](../../docs/records/0_issues/VOIC-FEAT-001.md)
- [VOIC-FEAT-001-plan](../../docs/records/1_plans/VOIC-FEAT-001-plan.md)
- [VOIC-FEAT-001-plan-02](../../docs/records/1_plans/VOIC-FEAT-001-plan-02.md)
- [ADR-001](../../docs/records/3_decisions/ADR-001-python-fastapi-extensible-core.md)
- [ADR-002](../../docs/records/3_decisions/ADR-002-python-modular-monolith-directory-contracts.md)
- [ADR-003](../../docs/records/3_decisions/ADR-003-initial-task-backend-and-operating-constraints.md)
- [ADR-004](../../docs/records/3_decisions/ADR-004-ht813-direct-outbound-telephony.md) (ADR-009로 대체)
- [ADR-007](../../docs/records/3_decisions/ADR-007-ht813-multiturn-call-lifecycle.md)
- [ADR-008](../../docs/records/3_decisions/ADR-008-local-encrypted-retention.md)
- [ADR-009](../../docs/records/3_decisions/ADR-009-ht813-all-inbound-agent.md)
