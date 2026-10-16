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

## 2026-10-16 관리 정정 후 재개 범위

전화 종료·취소·다음 전화 수락과 관측 도구 구현 지점 정적 조사. Gate 2 전 새 통합시험 생성/실행 금지. 앱·공유 문서 수정 금지. 본인 STATUS만 수정 가능. 부모의 현재 승인 방식은 담당 채팅 명시 응답이며 MR 선행 병합은 불필요하다.

### M10 재개 정적 조사 범위 (2026-10-16 KST)

사용자 최신 지시에 따라 MR #4 병합 선행조건은 철회됐으며 Gate 2는 채팅 응답 대기다. 부모가 위임한 추가 범위는 전화 처리/재생 중 종료·운영 취소·다음 전화 수락의 기존 코드/시험 정적 조사와 발착신 메타데이터 wrapper 조립 지점 제안이다. 코드·시험 생성/수정/실행, 운영 접속·실전화는 금지한다. 쓰기는 본 STATUS만이다.

## 추가 위임 — BUG-009 단위 재현/수정

VOIC-BUG-009를 읽고 inbound.py와 대응 inbound.test.py만 소유한다. 테스트 워크플로를 따라 fake 경계 단위 재현 FAIL→최소 수정→PASS 및 관련 단위시험을 실행한다. 통합시험/실전화 금지. 실행 원본/JUnit은 /tmp/m10-bug009-*에 저장하고 부모가 표준 TRY 로그를 작성한다. Git commit/index·공유 문서 수정은 부모만 수행한다.

### 재개 조사 결과: 종료·취소·후속 수락 (2026-10-16 KST)

정적 조사 완료. 최신 관리 지시의 MR #4 선행 병합 철회를 우선하며 Gate 2 채팅 응답 대기 상태를 유지한다. 생산 코드·시험 변경/실행·운영 접속·실전화 없음.

기존 커버리지와 남은 경계:

- `tests/units/orchestrator/testcodes/channels/ht813/call_manager.test.py:142`는 FakeOutbound로 task 처리 대기 중 상대 종료→송출 0·gate 해제·COMPLETED를 검증한다. 179행은 연결 중 취소·gate 유지/해제, 208행은 task timeout 후 통화 유지, 248행은 재생 중 입력 버림이다. 실제 SIP/RTP·retention·HTTP 조회·후속 전화는 결합하지 않는다.
- `tests/units/orchestrator/testcodes/channels/ht813/operator.test.py:43,79`는 FakeManager의 운영 API DELETE를 검증한다. 실제 발신 manager/core/UDP/RTP/보존 결합 취소가 아니다.
- `tests/units/orchestrator/testcodes/channels/ht813/inbound.test.py:226,238,300`은 초기 CANCEL, 미디어 오류, shutdown BYE 시도·gate/media 회수를 검증한다. 300행은 send 실패에도 자원 회수되는지 확인하지만 동시 상대 BYE와 shutdown의 경쟁은 없다.
- `tests/integrations/ht813/test_loopback_sip_rtp.py:202`는 발신 정상 2턴·DTMF·문맥·원격 BYE, 288행은 착신 정상 2턴·busy·미표시 후속 착신·shutdown 포트 회수를 검증한다. 이미 있는 정상/피어/SDP/busy 시험을 복제할 필요는 없다.
- Gate 2 이후 추가 대상은 실제 core/channel/gate/retention+loopback peer+Operator ASGI를 연결한 (a) task/TTS 대기 또는 실제 RTP 재생 중 상대 BYE, (b) 발신 처리/재생 중 DELETE, (c) 동일 인스턴스/포트의 다음 전화 수락·새 문맥·조회 ID 격리다. Event로 단계 진입을 동기화하고 고정 sleep에 의존하지 않는다. 기존 정상 시험 헬퍼와 fake 모델을 재사용하되 실제 외부 API는 호출하지 않는다.
- TTS 응답 텍스트는 core/orchestrator.py:149~154에서 송출 전에 보존된다. 재생 중 종료 시 assistant 텍스트 존재는 정상일 수 있다. task 대기 중 종료는 최종 user만 남을 수 있고, STT 완료 전은 대화 404일 수 있다. 이미 전송돼 네트워크 큐에 남은 RTP를 새로운 송출로 잘못 판정하지 않도록 처리된 취소/BYE 기준과 송출 시점을 구분한다.

결함 의심(미실행·확정 아님):

- `inbound.py:404`는 `_terminate`를 추적되지 않는 create_task로 실행한다. 410행에서 `_dialog=None`으로 만든 뒤 core/retention 정리와 440행 gate 해제를 기다린다. 그 사이 `close():442~464`가 실행되면 `_dialog`가 없어서 그 종료 task를 기다리지 않고 반환할 수 있다. `bootstrap.py:102~104`는 inbound.close 반환 직후 retention.close로 ready를 내린다.
- 결정적 재현안: 활성 착신에 fake retention의 record_call_end를 Event로 차단 → BYE → 종료 저장 진입 확인(이때 _dialog=None/gate 점유) → service.close → 반환 시 gate 점유/종료 task 미완료인지 확인 → Event 해제·청소. 현재 shutdown 단위 시험에는 이 동시성이 없다. Gate 2 후 먼저 재현 FAIL 여부를 확인하고, 확정되면 별도 BUG 기록/재현 FAIL→수정 PASS 절차를 따른다.
- 원격 모델 취소의 한계: orchestrator `_guarded`는 로컬 HTTP/송출 task를 취소하지만 model-serving/server.py:108~125는 `_NeverCancelled()`로 추론한다. HTTP 대기 취소를 실제 GPU 작업 중단으로 표현할 수 없다. M10은 로컬 대기/송출 취소·gate/회선 회수와 다음 통화 처리를 검증하며 서버 측 계산 취소는 따로 증거가 필요하다.

메타데이터 wrapper 조립 권고:

1. `bootstrap.create_app(settings)`를 그대로 호출한 직후, lifespan 시작 전에 `app.state`의 실제 객체에만 관측을 붙인다(bootstrap.py:119~123). 새 gate/core/retention을 만들거나 원본 router closure를 우회하지 않는다. 본문·번호·키가 설정 또는 이벤트에 있으므로 객체 전체 repr/JSON 출력 금지.
2. 착신은 `app.state.inbound.events`를 원래 sink에 정확히 한 번 전달하는 tee로 감싼다. 발신은 `app.state.operator_calls.manager.call`의 원래 bound method에 들어가는 events를 tee로 감싸 원래 OperatorCalls 상태 sink와 SequencedCallEvents 동작을 그대로 보존한다. inbound.events 대체만으로 발신 이벤트가 수집되지는 않는다.
3. SIP는 발신 `_peer_factory`로 생성되는 실제 peer의 send/receive/close를 위임 관측하고, 착신 handle_packet/_send는 원래 함수를 1회 호출한다. 별도 socket 수신기나 패킷 소비자를 추가하지 않는다. 원본 패킷·Request-URI·headers는 기록하지 않고 method/status/trusted/direction만 기록한다.
4. RTP는 발착신 `_media_factory`가 반환하는 실제 media의 start/send_audio/close를 위임 관측한다. `send_audio` 호출 수·완료/취소 수는 실제 UDP 패킷 수가 아니다. 생산 RTP 루프 복제 또는 전역 loop.sock_sendto monkeypatch로 계측하지 않는다. 실제 패킷 수/종료 후 추가 패킷은 loopback 시험 peer에서 검증하고, live 근거는 audio callback/close/사용자 청취로 범위를 정확히 표시한다.
5. gate는 기존 동일 객체의 acquire/release를 위임 관측한다. release 원본 반환 뒤 active_session_id를 읽어 회수 완료 시각을 남긴다. outbound CallStatus.ENDED는 outbound.py:268에서 media.close:283보다 먼저, inbound ENDED는 inbound.py:429에서 retention/gate 해제:434~440보다 먼저 나오므로 ended를 회수 완료로 간주하지 않는다. timer 10초는 FXO 사용자 관찰까지 합친 최후 시각이다.
6. SessionState의 LISTENING/PROCESSING/SPEAKING은 그대로 관측하되 SPEAKING은 TTS HTTP 시작 전이며 실제 첫 RTP 재생 신호가 아니다(core:152~154). 처리/재생 종료 트리거를 분리한다. 정확한 STT/task/TTS invocation 계수는 기존 runner의 adapter 호출을 body 비관측 위임 proxy로 감싸거나 기존 stage span에서 얻되 새로운 adapter/client를 만들지 않는다.
7. 관측기는 동기 I/O나 await로 production 경로를 지연시키지 않는 bounded queue에 allowlist 메타데이터만 put_nowait한다. 관측 실패/queue overflow는 evidence_lost로 표시해 그 시험을 미검증 처리하고 원래 반환값/예외/취소를 바꾸지 않는다. wrapper의 출력 순서·payload identity·호출 횟수·취소 전파를 fake 경계로 비교한 뒤 live에 사용한다.

부모에게 기존 커버리지 공백과 `_terminate`/close 경쟁 의심을 전달했다. 다음 행동은 Gate 2 명시 승인 후 부모의 시험 범위 배정이다. 본인 정적 조사 상태는 done이다.

### BUG-009 단위 재현·수정 완료 (2026-10-16 KST)

부모가 생성한 VOIC-BUG-009와 추가 위임에 따라 소유 범위를 inbound.py 및 inbound.test.py로 확대했다. 최신 AGENTS·how-to-work·create-testcase·BUG-009·컴포넌트 README를 읽고, 기존 fixture와 Event만 사용한 단위 재현을 먼저 실행했다.

- 재현: BYE와 초기 CANCEL 뒤 fake retention 종료 저장을 Event로 막아 gate 점유를 유지하고 close를 호출한다. 수정 전 close가 먼저 반환해 두 경우 모두 같은 assertion 실패를 관측했다.
- 수정: BYE/CANCEL이 생성하는 종료 task를 `_terminations`에 등록하고, close가 packet 처리 종료 이후 해당 task들을 취소하지 않고 기다린 다음 socket을 닫는다. 기존 통화 정책/API/보존 형식은 변경하지 않았다.
- 시험: 종료 저장 해제 후 gate 해제·정상 ended 저장 1회·중복 close 안전성까지 검증한다. 실제 socket·파일 보존·모델·통합시험·실전화는 사용하지 않았다.
- RED: 2026-10-16 23:22:48.313813 KST 시작, 0.329초, 2 failed / 18 deselected. `/tmp/m10-bug009-red.xml`.
- GREEN: 2026-10-16 23:23:12.707534 KST 시작, 0.250초, 2 passed / 18 deselected. `/tmp/m10-bug009-green.xml`.
- REGRESSION: 2026-10-16 23:23:26.181019 KST 시작, 0.628초, 해당 파일 20 passed. `/tmp/m10-bug009-regression.xml`.
- 공통 명령: `PYTHONPATH=apps/orchestrator/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/units/orchestrator/testcodes/channels/ht813/inbound.test.py`; RED/GREEN은 `-k voic_bug_009 --junitxml=/tmp/m10-bug009-{red,green}.xml -q`, 회귀는 `--junitxml=/tmp/m10-bug009-regression.xml -q`를 추가했다.
- `git diff --check` 통과. 기존 audioop Python 3.13 deprecation warning 1건이며 시험 실패와 무관하다.
- 표준 TRY 로그·이슈/영속 로그 갱신·커밋은 부모가 담당한다. Git index/공유 문서는 수정하지 않았다. 수정은 BYE/CANCEL 별도 종료 task 경쟁에 한정하며 현재 실장 회수 검증을 대신하지 않는다.

### BUG-009 공통 종료 경로 보강 및 최종 인계

부모 리뷰에서 `_accept`/`_conversation`/`_watch_media`의 직접 `_terminate` 호출도 같은 close 경쟁을 가짐을 확인해 앞의 BYE/CANCEL 한정 수정은 최종안에서 대체했다. 테스트를 ACK 응답 송신 실패·대화 종료·미디어 실패로 확장하자 한정 수정에서 추가 3건 FAIL을 관측했다. Event 진입·해제로 순서를 고정하며 고정 시간 sleep은 추가하지 않았다.

최종 구현은 `_terminate`가 `_dialog`를 제거하는 동일 lock 구간에 cleanup 완료 future를 등록하고, 기존 정리 본문을 `_finish_termination`으로 분리해 finally에서 future를 완료한다. close는 실제 caller task가 아니라 shield한 cleanup 완료 future들을 기다린다. 이로써 task 간 상호 await 없이 BYE/CANCEL 및 accept/conversation/media 직접 종료 모두 기다린다. 원래 task 취소·3초 conversation 정리 제한·보존 실패 처리·gate release 정책은 그대로다.

추가 실행(기존 XML은 덮어쓰지 않음):

- `/tmp/m10-bug009-direct-red.xml`: 2026-10-16 23:25:01.487696 KST 시작, JUnit 0.449초, 3 failed + 2 passed. 세 직접 종료 경로에서 동일한 조기 close assertion 실패.
- `/tmp/m10-bug009-complete-green.xml`: 2026-10-16 23:26:04.039558 KST 시작, JUnit 2.219초, 재현 5 passed.
- `/tmp/m10-bug009-complete-regression.xml`: 2026-10-16 23:26:22.076552 KST 시작, JUnit 2.499초, 해당 파일 전체 23 passed.
- 명령은 위 공통 pytest 명령을 유지하고 XML 이름을 해당 이름으로 지정했다. 재현은 `-k voic_bug_009`, 전체 회귀는 필터 없음. 모든 실행 `-q` 사용.
- 최종 `git diff --check` 통과. 최종 변경은 inbound.py 24행, inbound.test.py 73행 추가/변경 범위 및 본 STATUS이며 index/커밋은 건드리지 않았다.

범위 한계: 프로세스 강제 종료·호출 task의 외부 강제 취소를 내구성 저장 보장으로 확대하지 않는다. 실제 보존/통화·HT813 Idle은 미검증이다. 부모가 표준 TRY 로그·BUG-009 판정·영속 로그·커밋을 담당한다.

### BUG-009 패킷 오류 종료와 close 취소 경계 최종 보강

부모 추가 리뷰의 `_dispatch_packet` 오류→직접 종료 경계를 fake runner/media/retention과 Event로 재현했다. runner가 취소 토큰을 받은 뒤 정리 대기 중 close를 실행하면, 패킷 task를 무조건 cancel하던 동작이 `_finish_termination`을 끊어 media가 열린 상태로 close가 반환했다. 단위 재현 1건에서 실제 FAIL을 관측했으며 BUG-009의 잔류 자원 회수 범위에 포함한다.

최소 수정은 기존 완료 future 집합을 `owner task → completion future` 사전으로 바꾸고 close에서 정리 소유 task를 cancel 대상에서 제외하는 것이다. 소유 등록은 `_dialog` 제거와 같은 lock 구간에 있다. 나머지 패킷은 기존대로 취소하고 모든 패킷을 기다린다. cleanup future 대기/3초 conversation 제한/retention 처리/외부 인터페이스는 유지했다. 외부의 임의 task 취소나 프로세스 강제 종료까지 보장하지 않는다.

시험은 실제 `_dispatch_packet` 오류 처리와 `_conversation` 정리를 실행하되 socket·모델·파일 보존 경계는 fake로 유지한다. close 진입 Event 뒤 정리 대기를 해제하고 media close·gate 해제·failed 종료 저장 1회·중복 close를 검증한다. 고정 시간 sleep을 추가하지 않았다.

- RED `/tmp/m10-bug009-dispatch-red.xml`: 2026-10-16 23:30:40.764524 KST 시작, JUnit 1.288초, 1 failed / 23 deselected. media 미회수 assertion 실패.
- GREEN `/tmp/m10-bug009-dispatch-green.xml`: 2026-10-16 23:31:05.490529 KST 시작, JUnit 0.687초, 기존 5건 포함 재현 6 passed / 18 deselected.
- REGRESSION `/tmp/m10-bug009-final-regression.xml`: 2026-10-16 23:31:17.449713 KST 시작, JUnit 0.824초, 해당 파일 전체 24 passed.
- 공통 명령은 앞의 pytest 명령과 같다. RED는 `-k voic_bug_009_close_preserves_packet_error_cleanup --junitxml=/tmp/m10-bug009-dispatch-red.xml -q`; GREEN은 `-k voic_bug_009 --junitxml=/tmp/m10-bug009-dispatch-green.xml -q`; 회귀는 `--junitxml=/tmp/m10-bug009-final-regression.xml -q`를 추가했다.
- `git diff --check` 통과. 기존 audioop deprecation warning 1건만 발생했다. Git index/공유 문서/운영 환경은 변경하지 않았다.

부모가 Gate 2 로컬 격리 통합시험 승인을 수신했다고 전달했으나 본 추가 위임에서는 단위시험만 수행했다. 실제 통화/운영 접속은 여전히 미승인·미실행이다. 본 단위 수정 상태 done, 부모의 표준 TRY 로그/최종 검토와 별도 후속 위임 대기.

## 로컬 통합 Gate 2 후 수명 경계 위임

사용자 승인된 로컬 loopback 수명 시험 보강. tests/integrations/ht813/test_loopback_sip_rtp.py 및 필요하면 test_call_lifecycle.py만 소유. 실제 app core/Operator API/UDP RTP/합성 retention을 결합해 처리·재생 중 BYE/운영 취소→정리→다음 전화 수락을 검증. 모델/장비는 loopback fake, 실제 데이터 금지. 앱 코드는 현재 부모 검토/커밋 대상이므로 추가 수정 전 통보. JUnit /tmp/m10-lifecycle-TRYn.xml, 표준로그/커밋 부모 담당.

### 로컬 통합 수명 경계 완료 — 2026-10-16 23:38 KST

BUG-009 앱/단위 파일 ownership은 부모에게 반환했다. 본 위임은 `tests/integrations/ht813/test_call_lifecycle.py` 신규 파일만 작성했고 기존 `test_loopback_sip_rtp.py` helper를 패키지 import로 재사용했다. AGENTS/how-to-work/create-testcase, OPS-008 이슈/계획 M10-S1/S2, orchestrator README, PRD/SRS 0.1.0과 ADR-007/008/009/012를 참조했다. Gate 2는 사용자 23:30 KST 로컬 격리 생성·실행 승인 범위다.

검증 범위:

- `processing`/`playback` × `inbound-bye`/`outbound-bye`/`operator-cancel` 총 6건. 실제 VoiceOrchestrator + 전화 채널 + UDP SIP/RTP + EncryptedRetention 파일 + 인증된 Operator ASGI HTTP를 결합했다. 모델과 SIP/RTP 상대는 합성이며 주소는 127.0.0.1로 한정했다.
- 처리 중은 adapter 진입 Event로 고정하고 완료되지 않은 상태에서 종료한다. 재생 중은 실제 RTPMedia send 진입 Event와 첫 RTP 수신 후 send 미완료를 확인해 종료한다. RTP 송신 로직은 바꾸지 않고 관측 subclass가 원본을 위임한다. 실제 50패킷 분량의 답변을 끝까지 보내기 전에 중단함을 검증한다.
- gate 해제·media close·RTP 포트 재바인딩, 중단된 작업 완료, 처리 중 RTP 0개, 재생 중 1~49개, 이미 큐에 있던 RTP를 배출한 뒤 추가 수신 없음(50ms 관측 창)을 검증한다. 단계 진입은 Event로 동기화하며 고정 sleep으로 종료 시점을 추측하지 않는다. 기존 rtp_turn의 20ms pacing은 실제 PCMU 입력 생성에만 사용한다.
- 같은 인스턴스/포트로 두 번째 실제 loopback SIP 통화를 연결하고 RTP 질의/답변을 완료한다. 다른 session_id·빈 이전 문맥·다음 통화 종료 후 포트 회수를 확인한다.
- 실제 암호화 보존을 읽는 HTTP 조회에서 처리 중 종료는 user만, 재생 중 종료는 생성된 user+assistant 텍스트, 두 번째 통화는 별도 user+assistant를 검증한다. 첫 통화 조회가 변하지 않고 착신 목록은 두 ID 모두 ended/ended_at을 갖는다.
- PRD-02/03/06/08, SRS-C03~C05/T04/T06/I03/I04/O04/O12를 테스트 docstring에서 추적한다. physical FXO Idle, 운영 모델 내부 연산 취소, 실전화 품질/10초 종료 목표의 증거로 확대하지 않는다.

실행 원본/JUnit:

1. `/tmp/m10-lifecycle-TRY1.xml`: 2026-10-16 23:36:28.001651 KST, 0.669초, 수집 오류 1. pytest importlib mode에서 bare helper module import 불가. `tests.integrations.ht813.test_loopback_sip_rtp` 패키지 경로로 수정했다.
2. `/tmp/m10-lifecycle-TRY2.xml`: 2026-10-16 23:36:39.449003 KST, 9.341초, 4 PASS/2 FAIL. 신규 시험의 착신 목록 응답 필드 `calls`가 실제 계약 `items`와 달랐다. 두 착신 사례가 마지막 목록 assertion에서 실패했으며 앱 결함은 아니다. HTTP 200 및 `items` 계약으로 수정했다.
3. `/tmp/m10-lifecycle-TRY3.xml`: 2026-10-16 23:37:16.980410 KST, 10.556초, 기존 loopback 2건+신규 수명 6건 전체 8 PASS. audioop deprecation warning 1건만 있으며 `git diff --check` 통과.

공통 명령: `PYTHONPATH=apps/orchestrator/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml`. TRY1/2는 `tests/integrations/ht813/test_call_lifecycle.py --junitxml=/tmp/m10-lifecycle-TRYn.xml -q`, TRY3는 `tests/integrations/ht813/test_loopback_sip_rtp.py tests/integrations/ht813/test_call_lifecycle.py --junitxml=/tmp/m10-lifecycle-TRY3.xml -q`를 붙였다.

앱 코드·기존 unit·공유 문서·index/커밋·운영환경 변경 없음. 부모가 표준 TRY 로그/영속 결과 로그와 최종 통합 검토/커밋을 담당한다. 본 위임 done.

## 후속 독립 검토 위임

부모가 작성한 `tests/integrations/ht813/m10_live_app.py`와 `test_m10_observer.py`를 읽기 전용으로 검토한다. 운영 접근/실전화/파일 변경은 하지 않는다. 기존 객체 동작 보존, 민감정보 비출력, 창 만료/종료·미디어 계측 타당성에 집중한다. 발견 시 부모에게 구체 경로/영향을 보고한다. 승인 범위는 기존 M10 로컬 Gate 2이며 검토 자체는 정적이다.

## 관측 검토 결함 수정 위임

읽기 검토의 4개 결함을 `m10_live_app.py`와 `test_m10_observer.py` 두 파일에서 수정한다. 두 파일 소유권을 부모로부터 이전받는다. 23:30:40 KST 로컬 Gate 2 아래 fake/임시 파일만 검증한다. 운영 접근/실전화 없음. 검증 JUnit /tmp/m10-observer-TRY3.xml부터 증가, 실패/성공·정확 명령/시각 보고. 공유 계획/로그/부모 STATUS/Git은 부모가 처리한다. 앱 제품 코드 변경 없음.

### 관측 결함 4건 수정 완료 — 2026-10-16 23:53 KST

소유한 두 observer 파일만 수정했다. 부모의 Gate 2 로컬 합성 승인 범위이며 운영 접근/실전화/제품 앱 코드/Git index 변경은 없다.

구현 결과:

- `Metadata.emit`는 callback 시각과 allowlist 메타데이터를 최대 1024개 queue에 `put_nowait`한다. UUID alias 매핑 저장/fsync와 stdout write/flush는 daemon worker만 수행한다. 시작 전 private directory/새 mapping 파일 검증·초기 빈 매핑 생성은 동기 수행한다.
- queue overflow·worker I/O 오류·bounded close timeout은 `evidence_lost`를 설정하고 최종 종료값을 nonzero로 판정한다. 출력이 가능하면 evidence_lost 표식도 기록한다. 차단된 출력에는 제한 시간 join만 수행해 통화 callback과 event loop를 막지 않는다. 저장/출력 예외 메시지·본문은 기록하지 않는다.
- 서버는 lifespan='on'이며 started뿐 아니라 startup_failed/shutdown_failed/error_occurred/shutdown_event 완료를 확인한다. 정상 cleanup만 stopped, timeout·실패는 shutdown_failed다. window 만료의 should_exit는 관측보다 먼저 설정하고 Metadata 생성 시점부터 창을 센다. graceful timeout은 정리 성공이나 물리 회수의 증거가 아니다.
- inbound는 현재 dialog Call-ID와 일치한 SIP만 session alias를 붙인다. 초기 INVITE 또는 다른 Call-ID는 matched=false/alias 없음이며 direction=inbound를 기록한다. outbound peer는 최초 INVITE의 Call-ID와 생성 시 session을 비공개 closure에 보관하고 일치 여부를 판정한다. raw Call-ID/번호/헤더/본문은 출력하지 않는다. SIP 상태도 100~699 범위만 허용한다.
- media는 output_attempted/completed/cancelled/failed 및 close 시점 inflight snapshot을 구분한다. 원래 send 반환값·예외·CancelledError를 보존한다. output_chunk_complete는 callback 완료 지표이며 RTP packet 수·첫 청취시각이 아니다. outbound는 media close 이후 cancellation callback이 끝날 수 있으므로 close snapshot과 후속 cancellation event를 함께 읽는다.
- DTMF는 계획된 test_symbol='5'|'#'|'other'와 duration만 기록한다. 다른 digit은 출력하지 않는다.

시험은 기존 3건과 출력 실패 원래 호출/lease 보존, 실제 차단된 thread sink+queue overflow+bounded drain, 매핑 저장 오류, media 취소/실패 예외 identity 보존, 다른 Call-ID inbound/outbound 오귀속 방지, 정상/timeout/startup 실패/output 실패 종료 판정, 5/#/기타 DTMF 구분을 합쳐 18건이다. 실제 uvicorn network/server 대신 fake server로 lifespan 분기를 검증했고 실제 모델/장비는 사용하지 않았다.

실행 기록(각 번호 `.xml`, `.json`, `.out` 원본을 `/tmp/m10-observer-TRY{n}`에 보존):

- TRY3: 2026-10-16 23:48:08.230320 KST 시작, JUnit 1.289초, 3 PASS/2 FAIL. 변경 전 출력 OSError가 통화에 전파되는 실패와 shutdown_failed인데0을 반환하는 실패를 재현했다.
- TRY4: 2026-10-16 23:50:19.427903 KST 시작, JUnit 1.234초, 13 PASS/1 FAIL. 짧은 fake startup 창(10ms)보다 고정 ready poll(100ms)이 길어 window_expired 없이 상위 timeout이 먼저 실행됐다. poll을 남은 창과 min으로 제한해 수정했다.
- TRY5: 2026-10-16 23:51:15.597771 KST 시작, JUnit 2.893초, 18 PASS.
- TRY6: 2026-10-16 23:52:36.103953 KST 시작, JUnit 1.246초, 18 PASS. 창 기준을 Metadata 시작으로 정합화하고 media close의 inflight snapshot을 명시한 최종본이다. `git diff --check` 통과.
- 모든 실행 명령: `PYTHONPATH=apps/orchestrator/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/integrations/ht813/test_m10_observer.py --junitxml=/tmp/m10-observer-TRY{n}.xml -q`. stdout/stderr는 같은 prefix `.out`에 저장했고 XML testsuite의 실제 timestamp/time/count를 `.json`으로 추출했다. 기존 audioop deprecation warning 1건 외 경고 없음.

최종 ownership은 부모에게 반환한다. 부모가 표준 TRY/영속 로그·후보 설명·최종 검토/커밋을 담당한다. 외부 출력이 완전히 막히면 evidence_lost 표식 자체도 전달되지 않을 수 있으므로 종료코드 nonzero를 반드시 확인한다. blocked daemon worker는 프로세스 수명까지만 남을 수 있으며 실제 장비/FXO 회수와 startup/shutdown 무한 대기를 강제 종료하는 OS watchdog의 증거를 이 로컬 시험이 대신하지 않는다.
