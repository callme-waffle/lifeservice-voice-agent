# Sub-agent Status

|key|value
|---|---
|Agent Name|telephony-review
|Parent Session|20261016-service-readiness-m10
|State|done <!-- active / blocked / done -->
|Started|2026-10-16 KST
|Last Updated|2026-10-16 KST

---

## 1. Delegated Objective

전화 수명·BUG-003·P0/D01~03/F01~05의 정적 검토 및 실행안 제안

## 2. Permitted Scope / Ownership

전화 코드·HT813 기존 시험·BUG-003 공개 증거를 읽기만 한다. 쓰기 소유권은 이 STATUS 파일만. 시험 생성/실행·운영 접근·Git 변경 금지.

## 3. Required References

AGENTS.md, how-to-work/work-planning/create-testcase, OPS-008 issue/plan, 해당 component README, service-readiness-contract/baseline, m6-remaining-test-runbook, PRD/SRS 0.1.0, 관련 ADR/BUG-003. 모두 /tmp/voice-agent-m10 병합 소스에서 읽는다.

## 4. Work Completed

## 5. Findings

<!-- Important findings must eventually be promoted to docs/records/ by the parent. -->

## 6. Verification Performed

## 7. Unresolved Concerns

## 8. Handoff to Parent

<!-- Output, changed files, recommended next action. -->

### 정적 검토 결과 (2026-10-16 KST)

- 읽은 범위: AGENTS, 실행·계획·시험·ADR 워크플로, OPS-008 이슈/계획, BUG-003, root/orchestrator README, PRD/SRS 0.1.0, service-readiness-contract/baseline, M6 실행서, ADR-004/007/009, HT813 기존 시험·전화 코드·backend Compose.
- 시험 생성/실행, 실전화, 운영 접속, 배포, Git 변경 없음. 본 STATUS에만 결과를 추가했다. sandbox bwrap 실패 후 require_escalated로 읽기 명령을 실행했다.
- 공개 BUG-003 증거는 service-readiness-baseline.md:43~44: 2026-10-09 착신 2통/두 번째 2답변, 2026-10-11 발신 1통 벨·연결·종료·Idle. 발신 2턴/DTMF/최초 미수신 원인은 미확인. 비공개 TRY10 링크는 재게시하지 않고 공개 요약으로 연결해야 한다.
- 기존 live_app.py:51~55는 발신 허용 번호를 강제로 비운다. F01/F02를 이 CLI로 실행할 수 없다. 24~27의 5~3600초 제한, 134~146의 graceful shutdown/시간 제한, 71~88의 내용 없는 계측은 재사용 가능하지만, M10 발신+착신 계측은 Gate 2 후 별도 보강해야 한다.
- operator.py:60~63은 CallState만 모으므로 발신 DTMF/턴 수 증거가 없다. live_app.py:83~85도 DTMF 횟수만 출력하므로 SRS-T03의 숫자/기호/지속 시간 판정에는 부족하다. 신뢰 가능한 테스트 지정 숫자·duration 또는 기대값 일치 boolean 계측이 필요하다.
- device_route_probe.py:35는 5061을 직접 점유하며 71~76은 REGISTER/OPTIONS만 검증한다. live backend와 병행할 수 없고 F01의 INVITE 0건 또는 정상 전화 증거 수집기로 사용할 수 없다.
- operator.py:52의 SIP 설정 제한은 60초다. outbound.py:232~237은 HT813 SIP 200 뒤 ACTIVE로 전환하므로 PSTN 벨/응답 및 15초 미수신 중단은 현장 확인과 별도 watchdog가 필요하다. ACTIVE 통화에는 전체 통화 제한 시간이 없다.
- DELETE /operator/calls/{id}는 현재 발신만 취소한다(operator.py:148~155). 착신 ID에 사용하면 404다. 착신 긴급 회수는 상대 종료 또는 시험 backend 정상 종료다. inbound.py:442~464와 outbound.py:266~284의 로컬 BYE는 응답 확인 없이 자원을 정리하므로 API 202/ended/포트 해제만으로 FXO Idle을 보장하지 않는다.
- 정상 종료 합격은 종료 버튼부터 FXO Idle/RTP/세션 중 가장 늦은 회수까지 ≤10초(contract:31). 복구 개시는 15초(runbook:58/64/72). 10~15초 회수도 정량 실패이며 시계 근거 없으면 미측정이다.

### 실행안 반영 권고

1. Gate 2 전에는 본 정적 결과·명령 계약만 문서화한다. 승인 후 기존 live_app를 기반으로 발착신 공용 M10 계측 runner와 내용 없는 operator/web helper를 만들고 후보 SHA에 묶는다. 현재 파일이 이미 구현됐다고 쓰지 않는다.
2. P0/D01 → D02 1회(FXS 준비 및 매 발신 직전 승인) → F01 → D03/F02 동일 발신 1회 → F03 착신 1회 → 조회 → F04 착신 2회 → F05 조건부 착신 1회의 순서를 제안한다. D02/F01 실패면 후속 발신 중단. D02 생략은 FXS 미준비 제한을 설명한 별도 승인 없이는 불가.
3. 위 기본 묶음 상한은 D02 포함 5회, F05 포함 6회다. D03와 F02를 별개 발신으로 중복 집계하지 않는다. 30분 자동 정상 종료를 유지하며 개별 정상 대화는 최대 5분으로 제안한다. 별도의 무발화/처리 중 종료/재생 중 종료/운영자 취소는 추가 전화이며 동일 상한에 몰래 넣지 않는다. M10-S2-T2 완료에는 해당 별도 범위가 필요하다.
4. 정상 종료 시각은 통화 담당자의 종료 버튼 시각과 계측 시계를 연결하고, SIP BYE/200, RTP closed, gate free, FXO Idle 시각을 각각 남긴다. 사용자 청취·실제 벨·Idle은 에이전트 관측으로 대신 보고하지 않는다.
5. F01은 합성 미허용 번호 HTTP 403, 기능 코드 422, SIP INVITE 0, FXO Idle을 함께 확인한다. 발신 객체 미설정 503은 F01 PASS가 아니다.
6. 실패/15초 미수신/회선 잔류/예상 밖 전화/개인정보 출력 시 신규 전화 중단. 발신 DELETE→상태·FXO 확인, 필요시 정상 backend 종료. 착신은 정상 backend 종료 후 현장 Idle 확인. 기존 키·암호문 삭제, 무인 재시도, 검증 안 된 FXS 자동 우회 금지.
7. BUG-003은 한 번 성공으로 종료하지 않는다(OPS-008 plan:560). 원인 확인·수정 또는 반복 수용 표본·미확정 위험에 대한 사용자 인수 판정이 필요하다.

### 부모 인계

- 재사용 가능한 합성 경계 명령(승인 후): `python -m pytest -c apps/orchestrator/pyproject.toml tests/integrations/ht813/test_loopback_sip_rtp.py` (발신 2턴/DTMF/BYE 및 착신 busy/Caller ID 합성 경계; 실제 PSTN 증거 아님).
- 현재 실착신 한정 CLI(승인 후): `PYTHONPATH=apps/orchestrator/src python tests/integrations/ht813/live_app.py --seconds 1800 < "$M10_ENV_JSON"`. 환경 JSON은 보호된 런타임 파일이며 내용 출력 금지. 발신용으로 사용 금지.
- P0 읽기 명령 제안(승인 후 GPU 호스트 로컬): `curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8101/ready`, 동일 :8102/ready, :8000/health. 상태 JSON만; 환경·docker inspect 전체 덤프 금지.
- 실제 발신 POST/취소 DELETE는 기존 operator API 사용. 토큰·번호를 CLI 인자로 넣지 않고 보호 파일을 Python/HTTP 클라이언트 내부에서 읽게 한다. 출력은 session_id/status/HTTP 코드/일치 boolean으로 제한한다. 본 단계에서는 helper를 생성하지 않았다.
- 다음 단계: 부모가 이 결과를 Gate 2 실행안의 도구 생성 범위·전화 수·현장 입력·복구 절차에 반영한다. 현장 입력 미정 및 Gate 2 미승인을 유지한다.

### 부록 A 독립 리뷰 (2026-10-16 KST)

대상: `docs/records/1_plans/VOIC-OPS-008-plan.md` A1~A7 초안(586~766행). 시험/배포 없이 정적 문서 대조만 수행했다. 8시도 합계(발신 2 + FXS 1 + 착신 5), 30분 창/90분 전체 시간, 10초 합격과 15초 복구 구분, D02 예외·매 발신 승인·미확인 입력 차단은 명시돼 있다.

실행 전 수정 권고:

1. **[P1] 중지/부재 원복 시 시험 컨테이너가 남음 — 694~705행.** 시험 `up`은 기존 backend를 시험 image/command/mount/restart=no로 교체한다. 원래 중지/부재면 마지막 원복 `up`만 생략하는 분기는 시험 컨테이너를 그대로 남긴다. 훗날 start가 시험 wrapper를 다시 실행할 수 있다. 원래 중지면 원본 이미지/설정으로 미기동 컨테이너를 재생성하고, 원래 부재면 시험 backend 컨테이너만 제거하는 분기를 명시해야 한다. volume/키 삭제 없이 수행하며 현장 Compose 버전에서 지원하는 명령과 종속 모델 비변경을 확인해야 한다. `compose create --no-deps` 지원 여부는 본 리뷰에서 검증하지 않았으므로 그대로 확정 명령으로 쓰지 않는다.
2. **[P1] 빌드 working directory/SHA 고정이 주석뿐임 — 652행, 681~683행.** R1은 운영 checkout으로 이동하지만 D1은 새 후보 checkout이라는 주석만 있고 `cd`나 HEAD/dirty 검증이 없다. 그대로 명령을 이어 실행하면 운영 소스를 빌드해 M10_TEST_SHA 태그를 붙일 수 있다. 별도 후보 경로로 명시 이동하고 HEAD == M10_TEST_SHA, 필요한 앱/시험 파일 manifest와 clean 상태를 확인한 후 build하도록 구체화해야 한다.
3. **[P2] 독립 CLI 사이 session_id 전달 계약 없음 — 717, 719, 723, 726행.** dial은 응답 ID를 메모리에만 보관하지만 history/cancel은 별도 프로세스로 실행한다. UUID를 메모리에서만 보관하면 다음 CLI가 F02/F03/C의 실제 ID를 찾을 수 없다. 보호된 0600 상태 파일(번호/원문 없이 사례↔UUID) 또는 같은 상주 helper의 제어 인터페이스 중 하나를 구체화해야 한다. 기존 API에는 발신 목록도 없으므로 API 조회로 사후 복구할 수 없다.
4. **[P2] 개별 최대 점유와 15초 무벨 타이머 집행 계약이 없음 — 634, 692, 717, 746행.** 30분 전체 창과 발신 요청에 최대 점유를 제시한다는 문구만 있고 사례별 상한/타이머 시작점/만료 시 cancel 또는 정상 종료 동작이 없다. 현재 API의 60초는 SIP 설정 timeout이며 ACTIVE 뒤 전체 통화 상한은 없다. 15초 실제 무벨을 SIP active로 우회하지 않도록 현장 벨 확인 입력과 probe timer, 개별 최대 점유/30분 deadline의 우선 적용을 명시할 것을 권고했다.

위 사항은 부모에게 메시지로 전달했다. draft MR임과 Gate 2 미승인/현장 입력 대기 상태를 유지한다. 본 STATUS 외 변경 없음.

### 부록 A 수정 재검토 (2026-10-16 KST)

기존 지적 4건의 문서 수정 확인을 완료했다. 이번 검토 범위에서 미해결 지적은 없다.

- P1 원복: 711행에 원래 실행/중지/부재별 분기, 중지는 원복 설정 `up --no-start`, 부재는 시험 backend만 `rm -f` 및 `-v` 금지, 현장 옵션 확인이 추가됐다.
- P1 빌드 기준: 685~688행에 후보 경로 이동, HEAD 일치, clean, 승인 기준 ancestry 확인이 추가됐다.
- P2 ID 인계: 715행에 0600 비추적 case-state.json의 사례↔UUID·소비 상태 원자적 전달과 정리 계약이 추가됐다.
- P2 타이머: 632행 사례별 최대 점유 합계 20분(8시도)과 753행 POST 직전 monotonic 기준 15초 무벨 watchdog·DELETE, ID 유실 회수, 전체 wrapper 독립 30분 타이머가 추가됐다.

이는 실행안의 정적 검토이며 실제 도구 구현·시험 통과·운영 복구를 검증한 것이 아니다. 현장 입력 및 Gate 2 미승인 상태는 그대로다. 본인 STATUS 외 파일 변경·시험·운영 접속·배포 없음.
