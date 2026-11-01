# 0. 로그 정보

|key|value|
|---|---|
|로그 ID|VOIC-FEAT-010-log-03|
|원본 이슈|[VOIC-FEAT-010](../0_issues/VOIC-FEAT-010.md)|
|실행 계획|[승인 계획](../1_plans/VOIC-FEAT-010-plan.md)|
|기록 시간|2026-11-01T13:36:59.722626+00:00|
|세션 ID|20261031-voice-provider-planning|
|기록 에이전트|Codex|

# 1. 실행 요약

M13 설정·요구사항, M14 Live 실행·채널·보존, M15 로컬 배포 준비를 구현했다. 사용자 요청인 키 주입 후 시험 시작 준비를 위한 코드·로컬 검증 결과이며 실제 OpenAI/HT813 인수 완료를 의미하지 않는다. 계획 전체 상태는 approved를 유지한다.

# 2. 수행 내용

## 대상 마일스톤: M13~M15 키·실회선 전 준비

최신 사용자 지시가 완료까지 계속 수행하도록 명시하여 동일 대화에서 단계별로 진행했다. 한 마일스톤 뒤 중단하는 기존 관례보다 이 지시를 우선했다.

### M13. 계약·설정

- 기준: `origin/dev/v0.0.1`의 `f1c2088`에서 `codex/voice-providers` 생성. 승인 기록 이관 `0d117d2`, PRD/SRS 독립 커밋 `1286589`, 설정 구현 `eb88bf9`.
- 기존 M10 PR #4는 draft/open이다. 전체 M10 합격을 가정하지 않는다. 본 작업에 필요한 수신 종료 경합 수정과 6개 시험을 기존 `45556d0a2411cd6efccf0f370d7522829121cd3f`에서 선택 반영했다.
- `onprem` 기본값, `openai_live` 선택, 키/FILE 상호배타, 모델·음성·시간·큐 검증. 미선택 STT/TTS 또는 Live 비밀은 읽지 않는다.
- Live와 Realtime API를 구분했다. 공식 Live start/audio/transcript/delegation/usage/close 계약을 적용했다. 아래 출처 참조.

### M14. 연속 대화·채널·보존

- 별도 Live 어댑터와 실행기, 24↔16kHz 상태 유지 변환, 20ms 출력 프레임, 독립 입력·출력·위임 작업, 단일 점유 및 취소.
- 전화 ready/VAD 게이트는 Live에서 우회. RTP 송신 시간축을 호출 간 유지. 웹 end 뒤 cancel 감시 유지.
- 같은 세션의 제한된 부분 전사로 작업 API에 위임. ID 중복 방지, 실패 명시, 결과 길이 제한, 종료 시 작업 취소.
- 최대 10초 오디오 분할, generated/sent 구분, 시간·부분성이 있는 전사. 기존 조회 `turns`와 새 `segments` 공존. 30일 만료 및 보존 실패 차단 유지.
- 내용 없는 지표와 최종 사용량 확정 여부. 서버 선행 종료의 최종 사용량을 이중 close로 덮어쓰지 않도록 시험 추가.
- 프로덕션 경로에 스캐폴드/더미 없음. 모의 서버와 합성 키·음성은 시험 코드에만 존재.

### M15. 배포·시험 준비

- `scripts/voice_stack.py`가 env에 따라 기존 GPU 스택 또는 backend만 있는 Live Compose를 선택한다.
- Live secret 마운트, GPU 모델 의존성 제거, 키를 조회하지 않는 health, 보안 빌드 컨텍스트, 운영 안내.
- 두 Compose 구문·서비스 구성을 합성 환경값으로 확인했다. onprem에는 backend/gpu-exporter/stt/tts, Live에는 backend만 존재한다.
- Docker 일반 소켓 접근은 거부됐지만 기존 `sudo -n` 권한으로 빌드/격리 실행 가능했다. 이미지 `voice-agent-provider-check:local` 빌드 성공.
- 외부 네트워크 없는 일회용 컨테이너, tmpfs 데이터, 합성 키, 착신 비활성으로 기동/health/종료 PASS. 결과 `status=ready, provider=openai_live, remote=unverified`. 컨테이너는 `--rm`으로 제거했다.

# 3. 검증 결과

## A. 단위 검증

설정 24개 PASS 이후 전체 orchestrator 회귀 최종 실행 151개 PASS, 추가 전화 연속 입력 시험 1개 PASS. 현재 총 152개를 검증했다. 처음 전체 수집 명령은 model-serving 패키지 미설치로 수집 실패했으며 대상 경로를 명시해 해결했다. 실패를 삭제하지 않았다.

- [설정 시험](../../../tests/units/orchestrator/logs/M013_S002_T001-TRY1.md)
- [최종 전체 회귀](../../../tests/units/orchestrator/logs/M014_S001_T002-TRY5.md)
- [전화 연속 입력](../../../tests/units/orchestrator/logs/M014_S002_T001-TRY1.md)
- [최초 수집 실패](../../../tests/units/orchestrator/logs/M014_S001_T002-TRY1.md)

## B. 승인된 로컬 통합 검증

Gate 1은 기존 승인, Gate 2는 이번 사용자 “로컬 통합시험 작성·실행 승인”. 범위 localhost/임시 파일/합성 데이터, API 비용 0원, 외부 API·실전화·운영 배포 제외.

```text
python -m pytest -c apps/orchestrator/pyproject.toml -o python_files='test_*.py' tests/integrations/voice_provider/test_local_live.py tests/integrations/call_history/test_call_conversation.py tests/integrations/retention/test_retention_file_boundary.py
8 passed, 1 warning in 7.79s
```

- [x] `test_web_live_duplex_delegation_cancel_and_encrypted_storage` — PASS
- [x] `test_live_and_legacy_phone_history_coexist_and_expire` — PASS
- [x] `test_voic_feat_005_m8_s3_prd08_srs_o04_conversation_boundary` — PASS
- [x] `test_voic_feat_001_m6_s2_private_files_encrypt_audio_and_final_text` — PASS
- [x] `test_voic_feat_001_m6_s2_startup_sweep_deletes_at_exact_day_30` — PASS
- [x] `test_voic_feat_001_m6_s2_periodic_sweep_deletes_real_file` — PASS
- [x] `test_voic_feat_001_m6_s2_rejects_broad_permissions_and_symlink` — PASS
- [x] `test_voic_feat_001_m6_s2_delete_failure_retries_and_cleans_orphan` — PASS

실패 없음. 실제 localhost WebSocket에서 web → Live 어댑터 → 모의 서버 → 위임 → 출력 → 암호화 파일 경계를 검증했다. 실제 OpenAI 이벤트 전달·권한·지연을 검증한 것은 아니다.

## C. 판정

키 없는 로컬 준비 검증 통과. Python 3.11/3.12 범위의 audioop 폐기 예고 및 기존 Starlette/httpx 경고가 있으며 현재 시험 실패는 없다. 실장비 에코·회선 안정성·실제 p95 지연·실제 비용은 미측정이다.

# 4. 계획 대비 이탈 사항

실제 I01~I08은 API 키/참여자/번호/시간/비용 상한 및 별도 실제 시험 Gate 2 전까지 미실행이다. 같은 대화에서 준비 단계를 진행한 것은 최신 사용자 명시 지시에 따른다. 기존 작업 실행기는 래퍼를 덧씌우지 않고 동일 계약으로 유지하고 연속 입력 기능 계약을 추가했다.

# 5. 미해결 사항 / 후속 작업

- 운영 호스트에 키를 안전하게 주입하고 Live 모델 사용 권한 확인. 공통 작업 API와 HT813·데이터 키는 기존 설정 유지.
- 실제 시험 번호/시간창/비용 상한 확정, 실제 API/회선 Gate 2 및 매 발신 직전 승인. 운영 배포 및 실회선 변경은 아직 하지 않았다.
- M10 회선 이슈가 해결됐다고 보고하지 않는다. 실제 착신/발신과 에코·재생 중 발화·종료를 다시 판정해야 한다.
- [운영 절차](../../guides/voice-provider-operation.md)에 키 주입, 실행, health 해석, 원복, 관측과 다음 시험 입력을 기록했다.

# 6. 참고자료

- [OpenAI Live WebSocket](https://developers.openai.com/api/docs/guides/voice-websockets)
- [Live delegation](https://developers.openai.com/api/docs/guides/live-delegation)
- [Live WebSocket reference](https://developers.openai.com/api/reference/resources/live/primary-websocket)
- [ADR-014](../3_decisions/ADR-014-selectable-voice-provider.md)
