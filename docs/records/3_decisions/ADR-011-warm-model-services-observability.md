# 0. 결정 정보

|key|value|
|---|---|
|ADR ID|ADR-011-warm-model-services-observability|
|상태|accepted|
|결정 시간|2026-10-07 13:39:49 UTC|
|결정자|사용자 (2026-10-07 모델별 컨테이너·30초 지연·Tempo/Grafana 명시 지시)|
|기록 에이전트|Codex|
|관련 이슈|[VOIC-FEAT-001](../0_issues/VOIC-FEAT-001.md)|
|관련 계획|[VOIC-FEAT-001-plan-02](../1_plans/VOIC-FEAT-001-plan-02.md)|
|대체 대상|[ADR-009](ADR-009-ht813-all-inbound-agent.md)의 단일 컴포넌트 배치 전제, [ADR-010](ADR-010-gpu-vm-direct-telephony-lan.md)의 systemd 단일 앱 배포 제안|
|대체 문서|(없음)|

---

# 1. 배경 및 맥락

기존 FastAPI 앱은 STT와 TTS를 매 요청·턴마다 생성·해제한다. 실제 착신에서 응답이 들렸으나 턴 전환 지연이 길었고, 작업 API와 모델 추론·송출의 시간 분해가 없었다. GPU VM은 GTX 1080 Ti 11 GiB VRAM이지만 호스트 RAM은 약 3.8 GiB이므로 두 모델을 동시에 상주시킬 수 있는지는 검증되지 않았다. 전화 SIP/RTP는 HT813와 같은 LAN의 GPU VM `192.0.2.23` 경로를 유지한다.

# 2. 검토한 대안

## A. 기존 단일 프로세스에서 매 턴 재로딩

- 장점: 배포 단순, 모델 간 상주 메모리 충돌 감소.
- 단점: 장시간 대기와 모델 지연 원인 분리 어려움.

## B. 단일 프로세스에 두 모델 상주

- 장점: 네트워크 경계가 없다.
- 단점: 모델별 장애·기동 순서·자원 분리와 준비 상태 확인이 어렵다.

## C. 모델별 독립 컨테이너와 별도 관측 스택

- 장점: 모델별 준비·장애·지연 구분, 기동 순서 제어, 독립 교체 가능.
- 단점: HTTP 경계·컨테이너 런타임·GPU 메모리 동시 상주 및 관측 인프라가 필요하다.

# 3. 결정 내용

사용자 지시에 따라 C를 채택한다. GPU VM에는 STT, TTS, FastAPI 백엔드, GPU 메트릭 수집을 별도 컨테이너로 둔다. STT `/ready`가 모델 로드를 마친 뒤 30초를 기다려 TTS를 시작하며, TTS `/ready` 뒤 백엔드를 시작한다. 백엔드는 시작과 `/health` 요청에서 두 모델 엔드포인트의 준비 상태를 확인한다. 음성·원문은 모델 사설 HTTP 경계에서만 전달하고 추적·메트릭의 태그나 로그에 싣지 않는다. STT·작업 API·TTS 처리 단계는 OpenTelemetry span과 지연 히스토그램으로 계측한다. Tempo는 추적, Prometheus는 지연·GPU 지표, Grafana는 조회와 대시보드를 담당한다. 관측 스택은 RAM 여유가 있는 작업 VM에 둔다.

ADR-009의 HT813 전체 외부 착신→에이전트, Caller ID 비필터, 신뢰 피어 제한, 발신 허용 번호, 전역 단일 통화 및 직접 SIP/RTP 계약은 그대로 계승한다. ADR-004의 코어·계약·채널 의존 방향도 유지한다. 단일 FastAPI 컴포넌트 전제만 백엔드+모델 서비스로 바꾼다. ADR-010의 GPU VM LAN 경로는 유지하며 단일 앱 systemd 배포 제안만 대체한다.

# 4. 결정 사유

사용자가 원하는 대기 시간 개선과 장애 판별을 위해 모델을 한 번 로드하고 준비 상태를 명시해야 한다. 30초 간격은 사용자 선택이다. Tempo는 trace 저장소이므로 GPU 수치와 단계별 지연 시계열을 표시하기 위해 Prometheus를 함께 둔다.

# 5. 결과 및 영향

## A. 쉬워지는 것

모델별 재기동·상태 판단, STT/작업 API/TTS 지연 비교, GPU 사용량 관찰이 가능해진다.

## B. 어려워지거나 제약되는 것

GPU VM의 컨테이너 런타임·NVIDIA GPU 컨테이너 지원과 두 모델 동시 상주 RAM/VRAM 검증이 선행돼야 한다. 백엔드↔모델 전송은 로컬 호스트로 제한하며 관측 포트 접근은 관리망에서 제한해야 한다. 30초 간격은 CPU/RAM 순간 피크 분산일 뿐 총 상주 메모리 부족을 해결하지 않는다. 실제 배포와 전화 품질은 별도 검증 전까지 미확인이다.

# 6. 재검토 조건

두 모델 동시 상주에서 OOM·swap 급증·GPU VRAM 부족이 발생하거나, HTTP 경계가 목표 지연을 더 악화시키거나, GTX 1080 Ti에서 컨테이너 CUDA/MeloTTS 조합이 기동하지 못하면 모델 크기·배치·호스트 RAM 증설을 재검토한다.

# 7. 참고자료

- [실착신 지연 기록](../2_logs/VOIC-FEAT-001-log-47.md)
- [Docker Compose 시작 순서](https://docs.docker.com/compose/how-tos/startup-order/)
- [Tempo OTLP 수신 구성](https://grafana.com/docs/tempo/latest/set-up-for-tracing/instrument-send/set-up-collector/otel-collector/)
