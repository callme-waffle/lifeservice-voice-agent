# 모델 상주 서비스와 관측 스택 운영

공개 문서의 `192.0.2.0/24`와 `198.51.100.0/24`는 실제 관리망이 아닌 문서용 주소다. 실제 값은 추적되지 않는 로컬 `.env`에만 둔다.

배포 전에 `.env`에 `VOICE_AGENT_GPU_HOST`, `OBSERVABILITY_HOST`, `VOICE_AGENT_TASK_API_BASE_URL`, `VOICE_AGENT_TASK_APPROVED_HOST`, `VOICE_AGENT_HT813_HOST`, `VOICE_AGENT_HT813_LOCAL_IPV4`를 설정한다. 작업 VM에서는 `python3 scripts/render_observability_targets.py`로 추적되지 않는 `deploy/observability/targets/`의 Prometheus 대상 파일을 생성한다. 두 방화벽 유닛은 `/etc/voice-agent/hosts.env`의 `VOICE_AGENT_GPU_HOST`, `OBSERVABILITY_HOST`, `VOICE_AGENT_LAN_INTERFACE`를 사용하므로 설치 전에 root 소유 `0600` 파일로 준비한다.

이 가이드는 [ADR-011](../records/3_decisions/ADR-011-warm-model-services-observability.md)의 배포 파일을 설명한다. 2026-10-07 GPU VM `198.51.100.74`에 Docker Engine/Compose와 NVIDIA Container Toolkit을 설치했고, GTX 1080 Ti의 컨테이너 접근, STT·TTS 동시 `/ready`, GPU 지표 수집을 확인했다. 작업 VM `198.51.100.67`에서는 Tempo·Prometheus·Grafana와 대시보드 및 OTLP 추적을 확인했다. GPU VM은 RAM 약 3.8 GiB, VRAM 11 GiB다. **30초 기동 간격은 두 모델의 최종 상주 메모리를 줄이지 않는다.** 실제 통화 부하·장시간 swap·상시 백엔드는 아직 운영 검증 전이다.

## 배치와 동작

`deploy/gpu/compose.yaml`은 GPU VM에서 STT(8101), TTS(8102), GPU 지표 수집기(9400)를 각각 분리한다. `deploy/gpu/compose.backend.yaml`을 추가했을 때만 FastAPI 백엔드(8000)가 포함된다. 모델 서비스와 백엔드는 호스트 네트워크를 쓰되 추론 API는 `127.0.0.1`에만 바인딩한다. 백엔드 SIP/RTP는 기존 HT813 직접 LAN 주소 `192.0.2.23`을 사용한다. STT가 모델 로드를 마쳐 `/ready`가 200이 되면 TTS 컨테이너가 생성되고, 기본 30초 대기 뒤 모델을 로드한다. TTS는 첫 합성을 한 번 수행한 뒤 `/ready`를 200으로 전환한다. 시험에서 첫 합성 60.262초, 반복 합성 0.401초, 준비 전 워밍업 적용 후 첫 API 합성 0.327초였다. TTS `/ready` 뒤 백엔드가 생성된다. 백엔드는 시작과 `/health` 호출 시 두 모델을 각각 2초 제한으로 확인하며 장애 시 `degraded`를 반환한다. 기존 단일 프로세스 경로는 로컬 개발용으로 남지만 배포 Compose는 HTTP 모델 엔드포인트를 지정한다.

`deploy/observability/compose.yaml`은 작업 VM의 Tempo, Prometheus, Grafana를 분리한다. Tempo는 OTLP HTTP `198.51.100.67:4318`에서 span을 받고, Prometheus는 GPU VM의 백엔드·STT·TTS·GPU 지표를 긁는다. Grafana/Prometheus UI는 작업 VM loopback만 연다. Grafana의 `Voice Agent: 지연 및 GPU` 대시보드는 STT 모델 추론, 작업 API, TTS 모델 추론 p95와 GPU 사용률·메모리를 표시한다. Tempo 데이터소스의 Explore에서 한 요청의 span을 시간순으로 볼 수 있다. 앱 추적에는 세션 ID, 전사·응답 텍스트, 오디오 페이로드, 전화번호, API 키를 넣지 않는다. 5분 구간 내 요청이 적으면 p95가 비어 보일 수 있다.

## 설치 선행 조건

1. GPU VM에는 Docker Engine/Compose와 NVIDIA Container Toolkit이 설치돼 있다. 재설치나 업그레이드 시 [NVIDIA 설치 문서](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)와 [GPU 컨테이너 확인 절차](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/sample-workload.html)를 따른다.
2. 작업 VM의 현재 계정은 `sudo -n docker`로 관측 스택을 관리한다. Docker 소켓 권한 부여는 사실상 호스트 관리 권한이므로 운영자가 접근 정책을 결정한다.
3. 두 VM 간 관리망에서 GPU→Tempo 4318/TCP, Prometheus→GPU 8001·8103·8104·9400/TCP만 허용한다. GPU VM의 `voice-agent-metrics-filter.service`는 지표 포트를 작업 VM `198.51.100.67`에, 작업 VM의 `voice-agent-otlp-filter.service`는 Tempo 포트를 GPU VM `198.51.100.74`에 한정한다. Docker 게시 포트는 `INPUT` 외에 `DOCKER-USER` 전달 경로도 제한한다. 두 규칙은 이 포트만 대상으로 하며 SSH나 다른 서비스를 변경하지 않는다. 실제 관리망 주소가 달라졌다면 Compose·Prometheus 대상과 두 유닛을 함께 수정한다.
4. 기존 보존 데이터와 **같은** 암호화 키, 데이터 경로, 작업 API 키와 웹 토큰을 준비한다. 백엔드 Compose는 키 값을 환경변수에 넣지 않고 `VOICE_AGENT_SECRETS_DIR` 아래의 `task_api_key`, `web_access_token`, `data_encryption_key` 파일을 `/run/secrets`에 마운트한다. GPU 디스크에 평문 키를 두지 않으려면 운영자가 호스트의 tmpfs 디렉터리에 0600 권한으로 파일을 준비하고 재부팅 시 다시 주입해야 한다. Docker 관리자에게는 마운트된 비밀을 읽을 권한이 생기므로 접근을 제한한다. 이전 30분 착신 시험의 메모리 전달 승인을 상시 배포 승인으로 해석하지 않는다.
5. 이미지 다운로드와 MeloTTS 한국어 사전·가중치 다운로드가 가능한지 확인하거나 신뢰한 내부 이미지/모델 캐시를 준비한다. `Dockerfile.model`은 Python 3.11·Torch CUDA 12.1 및 MeloTTS Git 커밋을 고정했고 GPU VM에서 실제로 빌드·기동했다. 이미지 재생성 시 모델 파일의 네트워크 재다운로드가 발생할 수 있다.

## 검증 순서

먼저 비밀 없는 구문 검증을 한다. `sudo -n docker compose --env-file .env -f deploy/gpu/compose.yaml config --quiet`는 비밀 없이 검사할 수 있다. 백엔드 포함 검증은 `-f deploy/gpu/compose.backend.yaml`을 추가하고 작업 모델 ID, 데이터 경로와 tmpfs 비밀 디렉터리 경로를 지정한다. 실제 운영용 보존 데이터를 시험용 키로 열지 않는다. 이번 백엔드 상태 스모크는 별도 tmpfs 데이터·시험 키, 착신 비활성, 외부 작업 API 호출 없음으로 실행한 뒤 컨테이너와 파일을 삭제했다. 관측 스택은 `OBSERVABILITY_SECRETS_DIR` 아래의 `grafana_admin_password`를 Docker secret으로 마운트한다. 작업 VM에서는 `/etc/voice-agent-observability/grafana_admin_password`에 암호를 생성해 root 소유·상위 디렉터리 0700으로 보관한다. 암호 파일을 삭제하면 다음 Grafana 컨테이너 재생성 시 실패한다.

관측 스택을 먼저 올리고, GPU VM에서는 STT 단독 → STT 준비 → TTS 30초 지연 → TTS 준비 순서로 올린다. 두 VM에 동일한 검증 커밋을 체크아웃하고 각 실행 환경의 필수 변수·권한을 준비한 뒤 해당 VM에서 다음 명령을 사용한다.

접근 제한 유닛을 새 호스트에 설치할 때는 해당 호스트에서 `deploy/gpu/voice-agent-metrics-filter.service` 또는 `deploy/observability/voice-agent-otlp-filter.service`를 `/etc/systemd/system/`에 설치하고 `systemctl daemon-reload`, `systemctl enable --now <유닛명>`을 실행한다. 적용 뒤 GPU→Tempo OTLP 200과 작업 VM→GPU 메트릭 200을 다시 확인한다. 관리 IP·NIC 이름이 다르면 유닛을 먼저 수정한다.

```bash
# 작업 VM: 암호 파일을 준비한 상태
OBSERVABILITY_SECRETS_DIR=/etc/voice-agent-observability sudo -n --preserve-env=OBSERVABILITY_SECRETS_DIR docker compose --env-file .env -f deploy/observability/compose.yaml up -d

# GPU VM: STT 및 TTS 모델만 먼저 기동
sudo -n docker compose --env-file .env -f deploy/gpu/compose.yaml up -d stt tts

# 두 모델의 /ready와 RAM/VRAM 안정 상태를 확인한 뒤, tmpfs 비밀 파일이 준비된 경우에만
sudo -n docker compose --env-file .env -f deploy/gpu/compose.yaml -f deploy/gpu/compose.backend.yaml up -d backend gpu-exporter
```

모델만 기동할 때는 백엔드 비밀값이 필요하지 않다. `free -m`, `nvidia-smi`, `docker compose ps`에서 메모리·swap·GPU와 준비 상태를 확인한다. 메모리 부족/OOM 또는 GPU 초기화 실패가 있으면 백엔드를 올리지 않고 중지한다. 두 모델이 안정적으로 상주하면 백엔드 loopback `/health`의 `status=ready`, `stt=ready`, `tts=ready`를 확인한다. 모델 서버 하나를 중지해 `degraded` 전환을 확인한 뒤 복구한다. 이번 격리 스모크에서 두 상태를 확인했다. 이어 Prometheus 네 scrape 대상의 `up=1`과 GPU 지표 존재, Tempo 추적 수신, Grafana 패널을 확인한다. 네 수집 대상이 `up=1`인 것은 시험용 백엔드가 실행된 동안만 확인됐으며, 백엔드를 정리한 현재 백엔드 대상은 `up=0`이 정상이다. 작업 VM의 Grafana는 `127.0.0.1:3000`에 있고 관리자 암호는 위 root 전용 파일에 있다. 합성 음성 2턴과 실제 회선 검증은 기존 M6 Gate 및 장비 복구 상태가 확인된 뒤 수행한다.

실통화 전후의 listening→처리→speaking 지연, 각 단계 p50/p95, RAM available·swap·GPU 메모리와 OOM 이벤트를 기존 log-47 기준선과 비교한다. GPU 지표 수집기는 `nvidia-smi` 실패 시 `/metrics`에 503을 돌려주므로 Prometheus의 `up=0`으로 확인된다. 종료 시에는 기존 보존 데이터를 삭제하거나 키를 교체하지 않고 서비스만 중지한다. Grafana/Tempo/Prometheus 데이터는 각 named volume에 저장된다.
