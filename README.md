# voice-agent

한국어 음성을 STT → 외부 작업 API → TTS로 처리하는 전화·웹 음성 에이전트다. 첫 서비스 개시 범위는 HT813 FXO 전체 착신, 정확한 허용 번호 발신, 같은 통화의 연속 대화, 인증된 운영자의 착신내역·대화내역 조회다. 현재 작업 API는 chat completion 응답 텍스트를 반환하며 예약·주문 등 외부 업무 변경의 성공을 보장하지 않는다.

## 현재 기준과 검증 상태

M9 소스 기준은 `dev/v0.0.1`의 `080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244`다. 착신내역 PR #1과 대화내역 PR #2가 병합된 공개 안전화 기준이다. 브랜치 이름 `dev/v0.0.1`과 패키지·요구사항 문서 버전 `0.1.0`은 서로 다른 식별자이며, 이름만으로 배포 릴리스가 확정된 것은 아니다.

- M6: 전화·모델·보존 구현과 일부 실장 성공 기록이 있으며, 전체 운영 검증은 부분 완료다.
- M7/M8: 두 조회 API 구현과 합성 검증이 완료됐다. 실제 새 통화 → 암호화 파일 → 조회의 운영 경계는 미검증이다.
- 상시 운영: 현재 운영 호스트의 배포 SHA·가동 상태, 동일 키 복구, 재부팅·경보·장기 안정성은 이 소스 확인으로 입증되지 않는다.

검증 결과의 범위와 공개 가능한 과거 근거는 [서비스 기준·증거 요약](docs/guides/service-readiness-baseline.md), 개시까지의 단계는 [VOIC-OPS-008 승인 계획](docs/records/1_plans/VOIC-OPS-008-plan.md)에서 추적한다. 문서 정합화나 MR 병합을 서비스 개시 성공으로 해석하지 않는다.

## 구성 요소

|경로|책임|
|---|---|
|[apps/orchestrator](apps/orchestrator/README.md)|FastAPI, 단일 세션, 웹·SIP/RTP 채널, 작업 API, 암호화 보존·조회|
|[apps/model-serving](apps/model-serving/README.md)|독립 상주 STT/TTS 프로세스, 준비 상태·추론·지표|
|[deploy/gpu](deploy/gpu)|GPU 호스트의 모델·백엔드·GPU exporter Compose|
|[deploy/observability](deploy/observability)|Tempo·Prometheus·Grafana 및 관리망 접근 구성|
|[scripts](scripts)|벤치마크·GPU 지표 및 로컬 관측 대상 설정 생성|

웹·전화를 합쳐 동시 활성 세션은 1개, PSTN 회선은 1개다. STT/TTS는 로컬 모델 서비스로, 최종 전사와 같은 통화의 이전 최종 전사·응답은 승인된 외부 HTTPS 작업 API로 전달한다. 음성·원문·착신 메타데이터는 로컬 AES-GCM 파일에 생성 후 30일간 보존한다. Caller ID는 표시 정보이며 인증 수단이 아니다. 웹 사용자 화면, FXS 독립 발신, 다중 회선·계정, 공개 운영 API는 전화 우선 개시의 후속 범위다.

## 개발·운영 진입점

Python 범위와 의존성은 각 컴포넌트의 `pyproject.toml`을 따른다. 저장소 루트에서 단위 시험을 실행한다.

```sh
python -m pytest -c apps/orchestrator/pyproject.toml tests/units/orchestrator/testcodes
PYTHONPATH=apps/model-serving/src:apps/orchestrator/src python -m pytest -c apps/model-serving/pyproject.toml tests/units/model-serving/testcodes
```

[.env.example](.env.example)은 입력 양식이며 실제 값은 Git이 추적하지 않는 환경 설정과 런타임 비밀 파일로 주입한다. 파일의 모든 항목이 현재 코드 또는 Compose로 전달되는 것은 아니므로 [orchestrator 설정 계약](apps/orchestrator/README.md)과 해당 배포 파일을 함께 확인한다. 비밀값·실제 번호·전사·오디오는 저장소와 일반 로그에 넣지 않는다.

- [모델 상주·관측 운영 가이드](docs/guides/model-serving-observability.md)
- [착신내역 조회](docs/guides/inbound-call-history.md), [대화내역 조회](docs/guides/call-conversation-history.md)
- [기존 M6 잔여 검증 실행서](docs/guides/m6-remaining-test-runbook.md)
- [PRD 0.1.0](docs/ideas/prd/0.1.0.md), [SRS 0.1.0](docs/ideas/srs/0.1.0.md)

운영 API는 backend loopback와 Bearer 인증을 모두 요구한다. 운영 호스트 또는 인증된 SSH 터널에서 사용하며 외부 프록시에 공개하지 않는다. 실제 통화·배포·장애 주입·통합 시험은 승인된 구체 실행 범위와 현장 조건을 따른다.

## 에이전트 작업 규칙

모든 코딩 에이전트는 작업 전 [AGENTS.md](AGENTS.md)를 읽는다. 작업 기록은 `docs/records/`, 필수 절차는 `.agents/workflows/`, 템플릿은 `.agents/templates/`, 세션 상태는 `.agents/sessions/`에 둔다. 이슈 접두어는 `VOIC`이다.

공개 기록의 `192.0.2.0/24`, `198.51.100.0/24`는 문서용 예시 주소다. 실제 배포 주소·작업 API 호스트는 추적되지 않는 설정에 둔다. 과거 비공개 운영 기록과 삭제된 이력을 통째로 재게시하지 않는다.
