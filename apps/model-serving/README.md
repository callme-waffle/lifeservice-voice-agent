# Model serving component

## 책임과 런타임

STT와 TTS를 각각 별도 컨테이너·프로세스에 상주시키는 FastAPI 컴포넌트다. `MODEL_KIND=stt|tts`로 종류를 선택하고 시작할 때 한 번 로드한 모델을 요청 간 재사용한다. 전화·웹 세션과 보존·작업 API는 [orchestrator](../orchestrator/README.md)가 담당한다. 모델 서비스는 전화 회선이나 외부 작업 API의 성공 여부를 판정하지 않는다.

Python `>=3.11,<3.13`과 `voice-agent-orchestrator==0.1.0`을 사용한다. 모델 런타임 설치는 [Dockerfile.model](../../deploy/gpu/Dockerfile.model)을 따른다. 소스 기준은 `dev/v0.0.1`의 `080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244`이며 패키지·요구사항 버전 `0.1.0`과 브랜치 이름은 별도 식별자다.

## 인터페이스

[server.py](src/voice_models/server.py)가 앱 수명과 요청별 추론 잠금을 소유한다.

|엔드포인트|계약|
|---|---|
|`GET /ready`|로드 완료 시 200; 준비 전 503. TTS는 준비 전 첫 합성 워밍업 수행|
|STT `POST /infer`|16 kHz·모노·PCM16 원시 바이트 → `{"text":"..."}`. 빈 값·홀수 바이트·60초 초과 크기 또는 인식 음성 없음은 422|
|TTS `POST /infer`|`{"text":"..."}` → 16 kHz·모노·PCM16 원시 바이트. 빈 텍스트·4000자 초과는 422|
|`GET /metrics`|Prometheus 지표|

모델별 잠금으로 추론을 직렬화한다. 응답은 완성된 결과이며 원격 HTTP 추론 취소가 GPU 작업의 즉각 중단을 보장하지 않는다. 추론 API의 접근 제한은 배포의 loopback 바인딩으로 적용하므로 외부에 공개하지 않는다. 전사·응답·음성·비밀을 일반 로그·추적 속성에 넣지 않는다.

## 설정·배포

- STT: `VOICE_AGENT_STT_MODEL_ID` 기본 small, CUDA/int8 로드. TTS: MeloTTS KR, `cuda:0`, `VOICE_AGENT_TTS_SPEED` 기본 1.25.
- `MODEL_METRICS_HOST`, `MODEL_METRICS_PORT`로 독립 지표 서버를 선택하고 `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`로 추적을 보낸다.
- [GPU Compose](../../deploy/gpu/compose.yaml)는 STT `127.0.0.1:8101` → ready → 기본 30초 대기 → TTS `127.0.0.1:8102` → 워밍업 ready 순서다. 30초는 Compose의 `TTS_START_DELAY_SECONDS`이며 서버 코드가 자체 대기하는 값은 아니다.
- backend는 두 모델의 healthy 조건 뒤 시작한다. 지표는 관리망의 STT 8103, TTS 8104이며 관리망 접근 제한은 [운영 가이드](../../docs/guides/model-serving-observability.md)를 따른다.
- 현재 Compose에 모델 캐시 영속 볼륨과 모든 이미지·가중치 digest 고정이 완성됐다고 가정하지 않는다. 재부팅·재배포 복구는 OPS-008 후속 검증 대상이다.

## 검증 상태와 개발

GTX 1080 Ti에서 Python 3.11, faster-whisper 1.2.1, CTranslate2 4.4.0, MeloTTS 0.1.2, Torch 2.3.1+cu121 이미지 빌드·기동과 두 모델 동시 ready의 과거 기록이 있다. CTranslate2 실행 가능 스택 플래그를 이미지 빌드 때 제거한다. 2026-10-07 합성 문장의 TTS 첫 추론은 워밍업 전 60.262초, 반복 0.401초, 준비 전 워밍업 추가 후 첫 API 요청 0.327초였다. 이 수치는 과거 TTS 단독 측정이며 현재 후보의 전화 전체 응답 지연이나 상시 품질 합격 근거가 아니다. 약 3.8 GiB RAM에서 실제 통화 부하·장기 swap 안정성은 미검증이다. [공개 기준·증거 요약](../../docs/guides/service-readiness-baseline.md)에 현재 검증 범위를 구분한다.

필요한 모델 런타임·CUDA 환경을 준비한 호스트에서 저장소 루트 기준으로 실행한다.

```sh
PYTHONPATH=apps/model-serving/src:apps/orchestrator/src MODEL_KIND=stt uvicorn voice_models.server:app --host 127.0.0.1 --port 8101
PYTHONPATH=apps/model-serving/src:apps/orchestrator/src python -m pytest -c apps/model-serving/pyproject.toml tests/units/model-serving/testcodes
```

단위 시험은 fake 모델로 서비스 계약을 격리한다. 실제 GPU 추론·backend 연결·재시작 통합은 구체 실행안 승인 후 별도 검증하며 과거 결과를 재실행 결과로 표기하지 않는다. 배치 결정은 [ADR-011](../../docs/records/3_decisions/ADR-011-warm-model-services-observability.md), 개시 게이트는 [OPS-008 계획](../../docs/records/1_plans/VOIC-OPS-008-plan.md)을 따른다.
