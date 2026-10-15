# 전화 우선 서비스의 소스·증거 기준

2026-10-16 KST, [VOIC-OPS-008 계획](../records/1_plans/VOIC-OPS-008-plan.md) M9-S1 기준이다. 구현, 과거 실장, 현재 운영 상태를 분리한다. 실제 운영 서버의 배포 SHA·이미지 digest·가동 상태는 이번 M9에서 조회하지 않았다.

## 1. 후보와 버전

|항목|기준|
|---|---|
|저장소|`callme-waffle/lifeservice-voice-agent`|
|대상 브랜치|`dev/v0.0.1`|
|원격 재조회 기준 SHA|`080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244`|
|M9 브랜치|`codex/ops008-m9-baseline`|
|기준 조회|`git ls-remote origin refs/heads/dev/v0.0.1` 및 fetch 뒤 같은 SHA 확인|
|앱·요구사항 버전|두 `pyproject.toml`과 PRD/SRS는 `0.1.0`. `dev/v0.0.1`은 기존 브랜치명이며 배포 버전이나 출시 태그가 아니다.|
|릴리스 식별|M9는 문서 변경 후보다. 실제 이미지 digest·모델 revision·배포 manifest·릴리스 버전은 M11에서 고정한다.|

부모 관리 브랜치의 과거 로컬 `ec5f5dc`에는 두 조회 구현이 없다. 부모 관리 커밋 `6245ba2`는 이력에 합치지 않고 OPS-008 이슈·계획·조사/승인 로그 네 문서만 내용을 검토해 이관했다. 과거 세션·원문 시험 로그·미추적 파일·실제 `.env`는 이관하지 않았다. 공개 이력에서 빠진 자료의 링크는 아래 공개 요약으로 연결하며, 요약을 원문이나 재실행 결과라고 표현하지 않는다.

## 2. 조회·환경변수·배포 연결

|계약|현재 소스·설정|운영 시 확인할 조건|
|---|---|---|
|착신 목록|[operator.py](../../apps/orchestrator/src/voice_agent/channels/ht813/operator.py), `GET /operator/inbound-calls`, 기본 limit 50, 최대 100, offset 페이지|localhost+Bearer, 새 착신만. 번호 없음은 null, backend 중지 중 부재중 기록 미지원|
|통화별 대화|같은 operator.py, `GET /operator/calls/{session_id}/conversation`|발착신 동일 session_id, 최종 user/assistant 텍스트만. 발신 ID는 POST 응답에서 보관; 별도 발신 목록 없음|
|기록·조회 조립|[bootstrap.py](../../apps/orchestrator/src/voice_agent/bootstrap.py), [retention.py](../../apps/orchestrator/src/voice_agent/infrastructure/retention.py)|발신 비활성 상태에서도 운영 조회 라우터·retention 조립. 기존 키·데이터 경로 유지|
|Caller ID|[config.py](../../apps/orchestrator/src/voice_agent/config.py), `VOICE_AGENT_HT813_CALLER_ID_HEADER`|`from`/`p-asserted-identity`/`p-preferred-identity`/`disabled`; 실제 장비 전송 방식과 일치. 신원 인증이 아님|
|영속 경로|[backend Compose](../../deploy/gpu/compose.backend.yaml), `VOICE_AGENT_DATA_DIR` → `/data`|`VOICE_AGENT_CALLS_DIR=/data/calls`, recordings/transcripts와 동일 볼륨·보존 정책|
|비밀 주입|같은 Compose, `VOICE_AGENT_SECRETS_DIR`의 `task_api_key`, `web_access_token`, `data_encryption_key` → `/run/secrets`; 앱은 각 `_FILE` 읽기|현재 Compose는 비밀 원본을 생성·복원하지 않음. 기존 32바이트 Base64 보존 키 유지|
|기동|[모델 Compose](../../deploy/gpu/compose.yaml), STT healthy → TTS 기본 30초 지연·워밍업 → backend|restart 정책만으로 재부팅 시 tmpfs 비밀 복원·기동 순서를 입증할 수 없음|
|관측|[targets 생성기](../../scripts/render_observability_targets.py), [Prometheus](../../deploy/observability/prometheus.yaml)|targets는 생성기로 생성. 현재 저장소는 scrape·대시보드 기반이며 장애 전달·수신 확인은 미구현/미검증|

포트·VAD·sweep·SIP 비밀번호 등 일부 Settings 입력은 현재 backend Compose에서 전달하지 않는다. 호스트 `.env` 수정만으로 반영된다고 가정하지 않으며 [설정 계약](../../apps/orchestrator/README.md)의 차이 목록을 확인한다.

API 상세 오류·필드는 [착신 가이드](inbound-call-history.md)와 [대화 가이드](call-conversation-history.md)를 따른다. 인증 실패 401, 원격 요청 403, 잘못된 입력 422, 대화 없음 404, 보존 읽기 실패 503을 혼동하지 않는다. 목록은 비어 있으면 빈 items를 반환한다. 시작 기록만 남은 착신은 incomplete이며 대화의 부분 턴과 다른 의미다. `GET /health`의 ready는 작업 API·PSTN 통화 성공을 증명하지 않는다.

## 3. 공개 가능한 과거 증거 요약

아래 로컬 로그 ID는 원본의 식별자다. 원문은 공개 기준에 없으며 이 MR로 재게시하지 않는다. 날짜는 원문 UTC 날짜를 기준으로 적었다. 현재 운영 상태를 뜻하지 않는다.

|근거|확인된 사실|확인하지 못한 범위|
|---|---|---|
|로컬 VOIC-FEAT-001-log-49 (2026-10-07 UTC)|STT/TTS 동시 ready, 분리 컨테이너와 관측 스모크. 합성 TTS 첫 API 0.327초. 격리 tmpfs 시험 backend 정리|실전화 전체 응답 지연, 운영 키 상시 주입, 재부팅, 장기 RAM/swap|
|로컬 VOIC-FEAT-001-log-55 (2026-10-09 UTC)|실착신 2건, 두 번째에서 두 답변 청취. HT813 BYE/서버 200/RTP 해제 및 사용자 FXO Idle 보고|종료 버튼의 정확한 시각 없음, 종료 ≤10초 수치 판정 불가. 장시간 종료 톤 오검출 미검증|
|로컬 VOIC-FEAT-001-log-58 (2026-10-11 UTC)|실발신 1회 벨·연결·상대 종료·Idle 확인|음성 두 턴·DTMF 미실행, 이전 미수신 원인 미확정. BUG-003 미해결|
|부모 조사 로그의 과거 보존/웹 시험 요약|격리 파일 경계 5건 및 Chrome 합성 PCM 왕복 성공 기록 존재|이번 M9에서 원본 재실행 없음. 실마이크 UI·운영 파일 복구 증거 아님|
|[PR #1](https://github.com/callme-waffle/lifeservice-voice-agent/pull/1)|착신내역 구현, 과거 단위 116+합성 경계 1건 보고, `c2d0280`에 병합|실전화→목록, 상시 배포 미검증|
|[PR #2](https://github.com/callme-waffle/lifeservice-voice-agent/pull/2)|대화내역 구현, 병합 조합 총 122건 보고, `080f5d3`에 병합|122건은 이번 재실행 수가 아님. 운영 키·실전화→대화 미검증|

PR 두 건의 merged 상태와 merge SHA를 M9에서 GitHub 연결로 재조회했다. 시험 수를 합산해 중복 커버리지나 현재 후보 시험 통과로 표시하지 않는다.

## 4. 마일스톤·요구사항 추적

|상태|요구·기능|기존 근거|다음 검증|
|---|---|---|---|
|M6 부분 완료|PRD-02/03/05, SRS-T01~T06/I01~I05/O02~O03|다중 턴 코드·과거 착신/발신 일부 증거|M10 F01~F05, 발착신 각각 2턴·DTMF·종료 계측·실제 Caller ID|
|M7 구현·합성 검증 완료|PRD-07, SRS-I06|PR #1, [계획](../records/1_plans/VOIC-FEAT-004-plan.md) executed|M10 실전화→calls 파일→목록|
|M8 구현·합성 검증 완료|PRD-08, SRS-O04|PR #2, [계획](../records/1_plans/VOIC-FEAT-005-plan.md) executed|M10 발착신 ID→대화·부분 턴·권한|
|운영 미검증|PRD-06, SRS-O01, M9 추가 수용 요구|ADR-008/011/012, 현재 Compose|M11 동일 키·백업/복구·재부팅·알림·성능; M12 제한 운영|
|전화 우선 후속|PRD-01/04, SRS-W01~W03/F02~F03|웹 프로토콜 구현·FXS 요구 유지|별도 범위. 물리 FXS 회선 공유 충돌은 개시 전 확인 또는 동시 사용 제한|

[운영 계약](service-readiness-contract.md)은 목표 제안과 사용자 입력을 구분한다. [실행 로그](../records/2_logs/VOIC-OPS-008-log-03.md)에서 이번 검증 결과와 MR 인수 상태를 확인한다.
