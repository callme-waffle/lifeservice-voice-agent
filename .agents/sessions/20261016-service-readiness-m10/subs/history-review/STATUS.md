# Sub-agent Status

|key|value
|---|---
|Agent Name|history-review
|Parent Session|20261016-service-readiness-m10
|State|done — approved isolated tests passed|
|Started|2026-10-16 KST
|Last Updated|2026-10-16 KST

---

## 1. Delegated Objective

조회·인증·PRD/SRS 요구사항 및 기존 통합시험의 정적 매핑

## 2. Permitted Scope / Ownership

operator/retention·조회 시험·PRD/SRS를 읽기만 한다. 쓰기 소유권은 이 STATUS 파일만. 시험 생성/실행·운영 접근·Git 변경 금지.

## 3. Required References

AGENTS.md, how-to-work/work-planning/create-testcase, OPS-008 issue/plan, 해당 component README, service-readiness-contract/baseline, m6-remaining-test-runbook, PRD/SRS 0.1.0, 관련 ADR/BUG-003. 모두 /tmp/voice-agent-m10 병합 소스에서 읽는다.

## 4. Work Completed

부모가 작성한 계획 부록 A1~A7의 조회/격리/승인 경계 후속 정적 리뷰 완료. 세 수정 권고 전달 후 부모 수정본을 재확인해 모두 해소됐음을 기록했다.

필수 workflow, OPS-008/BUG-003, PRD/SRS, README, 운영 기준/계약/실행서, ADR-008/012, 조회·보존 코드 및 기존 시험 정적 검토 완료.

## 5. Findings

- API 인증: operator.py:88 loopback 403 우선, Bearer 불일치 401. 대화 :120 UUID 422/없음 404/저장소 503, 목록 :133 limit 1~100, offset≥0.
- 요구: PRD-07/08 → SRS-I06/O04/O01/O12; M10-S2-T1/T2. 시작만 있는 목록 incomplete, 텍스트 없는 대화 404, 응답 없는 부분 턴을 구분한다.
- 기존 call_history 2개와 retention 5개는 총 7개. inbound는 FakeMedia/runner=object로 INVITE→CANCEL, conversation은 record_text 직접 저장. 실제 음성 코어/운영 배포 연결 증거가 아니다.
- pytest 설정 python_files=['*.test.py'] 때문에 test_*.py인 통합 시험은 개별 파일 경로나 명시적 패턴 override가 필요하다.
- 추가 승인 후 필요한 합성 경계: HTTP 손상 503 및 원문 비노출, 무발화 목록+대화404, 시작만 incomplete, 전화 두 session_id 격리. 기존 대화 시험의 다른 ID는 WEB이다.
- F02/F03의 발신 POST ID와 착신 목록 ID를 실제 파일/대화 2턴/시각/상태에 연결. Caller ID 및 원문 일치는 운영자 메모리에서 판정하고 공유 증거에는 boolean만 기록.
- core/orchestrator.py:99에서 전사 저장, :149에서 응답을 TTS 전에 저장한다. 처리 중 종료는 user만 가능하나 재생 중 종료는 assistant도 존재할 수 있다.
- 손상/30일 만료/종료 누락은 격리 합성 저장소에서만 검증. 운영 키·파일 손상/삭제 및 가짜 시계 적용 금지.

## 6. Verification Performed

읽기 전용 파일·줄 대조만 수행. 부록 후속 리뷰에서도 동일하며 어떤 시험도 생성/실행하지 않음. 시험 생성/수집/실행, 운영 접속, 배포, Git 조작 없음. 기본 exec bwrap 실패로 require_escalated 읽기 사용. STATUS 수정 명령의 python 미설치로 첫 시도 실패 후 python3 사용.

## 7. Unresolved Concerns

후속 재검토: 기존 수정 권고 3건이 모두 문서에 반영됐다. 검토 범위 내 추가 미해결 사항 없음.
- A5: 0600 비추적 case-state.json의 사례 ID→session_id/상태/시도 소비 여부를 CLI가 공유하며 번호·토큰·본문을 저장하지 않는다.
- H01: F03 직후 실제 새 착신 1건 한계를 명시하고 합성 페이지 검증과 F04/F05 뒤 실장 재조회를 구분하며 표본 부족은 미검증으로 기록한다.
- A6: 기존 call_history 파일 확장 우선, 새 query 파일은 미커버 HTTP/파일 경계에 한정, lifecycle은 보존→HTTP 및 부족한 종료 경계만 추가해 기존 loopback 복제를 피한다.

승인·격리 경계 자체는 적절하다: 미완성 초안 병합을 Gate 2로 간주하지 않음, 운영 API 노출 없이 remote-client 403 격리 검증, 손상·만료는 합성 저장소만, 운영 키/데이터 보존, 본문 비출력, 재생중 assistant 존재 의미가 명시됨.

Gate 2 및 현장 준비 전 통합시험 생성·실행 불가. 현재 후보의 실제 전화→파일→조회 미검증.

## 8. Handoff to Parent

변경 파일은 이 STATUS뿐이다. 부모가 발견을 M10 실행안에 반영했고 재검토에서 확인했다. 승인 후 재사용할 기존 시험 명령(미실행):

```sh
PYTHONPATH=apps/orchestrator/src python -m pytest -c apps/orchestrator/pyproject.toml tests/integrations/call_history/test_inbound_call_history.py tests/integrations/call_history/test_call_conversation.py tests/integrations/retention/test_retention_file_boundary.py
```

실제 조회 도구는 토큰을 보호 파일/getpass로 메모리에서 읽고 번호·본문·토큰을 출력하지 않으며 상태코드/ID 상관관계/턴 역할·시각/일치 boolean만 기록하도록 승인 후 만든다.

## 2026-10-16 관리 정정 후 재개 범위

조회·보존 경계 기존 통합시험의 누락 사례 정적 조사. Gate 2 전 새 통합시험 생성/실행 금지. 앱·공유 문서 수정 금지. 본인 STATUS만 수정 가능. 부모의 현재 승인 방식은 담당 채팅 명시 응답이며 MR 선행 병합은 불필요하다.


### 재개 정적 검토 결과 — 완료

현재 승인 방식은 담당 채팅의 Gate 2 명시 응답이다. MR #4 선행 병합은 조건이 아니며 과거 부록 리뷰의 병합 전제는 최신 관리 정정에 의해 대체된다. 부모가 Gate 2 응답 대기 중임을 전달했으며 이 하위 작업에서는 코드/시험 생성·실행·수집·운영 접속을 하지 않았다. 변경 파일은 이 STATUS뿐이다.

기존 시험/요구 재대조:
- PRD-07/08 (`docs/ideas/prd/0.1.0.md:56,60`) 및 SRS-I06/O04 (`docs/ideas/srs/0.1.0.md:68,89`)는 무음 착신 목록, 대화 없음404, 부분/종료 누락, 원문 없는 손상503, 다른 통화 내용 배제를 요구한다.
- `test_inbound_call_history.py:82`는 두 INVITE→CANCEL 뒤 목록/페이지/만료만 검증한다. 같은 통화 ID의 텍스트 없음404 및 종료 전 incomplete HTTP 계약은 미검증이다.
- `test_call_conversation.py:33`의 다른 ID는 WEB이며 전화 두 ID 격리가 아니다. 기존 user-only 부분 턴, 401, remote403, unknown/expired404는 재사용한다.
- `retention.test.py:249,294`의 손상/incomplete는 저장소 호출이다. 기존 retention 통합5건은 암호화·만료·권한·삭제 경계이며 HTTP503 증거가 아니다.

최소 보강안(승인 후; 신규 파일 불필요):
1. 기존 inbound 시험에서 INVITE 수락 후 `gate.active_session_id`를 포착한다. CANCEL 이전의 인증된 목록에 해당 ID/status=incomplete/ended_at=null을 정확히 확인하고, CANCEL/lease 해제 뒤 동일 ID=status=ended 및 conversation404를 확인한다. 텍스트 아티팩트0, 가짜 시계의 시작/종료 시각도 대조한다. 이 검증은 시작만 존재하는 조회 의미이며 실제 프로세스 크래시 재현 근거는 아니다.
2. 기존 conversation 시험에 별도 HT813_FXO ID B를 추가한다(WEB 다른 ID/같은ID 차단 사례 유지). A/B에 구별되는 합성 최종 텍스트를 저장하고 두 HTTP 응답의 session_id와 전체 turns를 각각 정확히 비교한다. A 조회에서 B가 없다는 부정 검사만으로 끝내지 않고 B 조회 성공도 확인한다. 기존 턴/시각 정렬 및 30일 만료도 유지한다.
3. inbound 파일에 실제 call 암호문 손상→목록503 케이스를 추가한다. startup과 정상200 확인 후 반환된 .va1의 암호문/인증태그 1byte만 변조한다(0600 유지). HTTP body가 일반화된 detail이고 번호/경로/토큰이 없는지 검증한다. store.start 이후 손상시켜 startup 실패와 HTTP 읽기 실패를 혼동하지 않는다.
4. conversation 파일에 같은 방식의 손상503 케이스를 자기 통화 파일/다른 전화 파일 2조건으로 매개변수화한다. 기존 정상 두 통화의200을 먼저 확인한다. 다른 전화 파일 손상도 현재 `retention.py:284` 전수 스캔/복호화 구조에서503이므로 파일을 건너뛰도록 동작을 바꾸지 않는다. 원문·경로·키·토큰 비노출을 응답 및 수집 로그에서 확인한다. 각 조건은 독립 tmp_path/시험키/시계 및 finally close를 사용한다.

예상 증분: 기존2개 테스트 확장 + 손상3개 실행 사례(목록1, 대화2). 결정적 시작-only 별도 케이스가 필요하면 기존 inbound 파일에 단일 record_call_start→HTTP 테스트를 추가하되 의미가 중복되는 검사를 늘리지 않는다. given/when/then과 VOIC-OPS-008/M10-S2, PRD/SRS 추적을 보강한 테스트 docstring에 명시한다. retention 통합5건·기존 조회2건은 회귀로 재사용한다. 정확한 실행 수는 실제 수집 후 기록하며 지금은 시험 결과가 아니다.

실전화 F02/F03 두 ID의 실제 파일/조회 연결과 청취·문맥은 위 합성 케이스로 대체하지 않는다. 손상은 tmp_path에서만 적용하고 운영 키·파일 복호화/이동은 별도 명시 승인 경계를 따른다. 미해결 사항은 Gate 2 및 실제 전화 경계 검증 대기다.

## Gate 2 후 구현 위임

사용자 2026-10-16 23:30:40 KST 로컬 격리 통합시험 생성/실행 명시 승인. tests/integrations/call_history/test_call_conversation.py와 test_inbound_call_history.py 두 파일만 코드 소유. 기존 파일 확장·손상503/무발화404/incomplete/두 HT813 세션 격리 검증 수행. 실제 데이터/외부 네트워크 접근 금지. 원본 JUnit은 /tmp/m10-history-*.xml, 표준 로그/Git은 부모 담당.


### Gate 2 후 구현·검증 완료 — 2026-10-16 23:32 KST

이 절이 이전 정적 검토 상태를 대체한다. 사용자 23:30:40 KST Gate 2 및 부모 위임에 따라 두 소유 시험 파일만 보강했다. 앱/운영 파일/외부 네트워크/Git 변경 없음.

- test_call_conversation.py: 기존 WEB 격리/정렬/인증/만료 검사를 보존하며 두 HT813_FXO 통화의 양방향 조회를 추가했다. 고유 질문·답변과 생성시각/턴을 검증한다. 실제 암호문 자기 통화/다른 통화 손상 2조건에서 HTTP503 및 응답·수집 로그의 원문/경로/토큰/키 비노출을 검증한다.
- test_inbound_call_history.py: 기존 합성 SIP INVITE 수락 후 incomplete/ended_at=null, CANCEL 뒤 ended·정확 시각과 동일ID 대화404·텍스트파일0을 확인한다. 기존 목록/페이지/번호null/암호화/만료 검사를 유지한다. call 메타데이터 실제 암호문 손상→HTTP503·비노출 1건 추가.
- 합성 키/고정 시계/tmp_path/ASGITransport만 사용했다. 손상은 정상 startup/조회200 이후 인증태그의 1byte를 변경했고 파일0600을 확인했다. 신규 대화 손상 케이스는 요청/다른 통화 모두 원래 정상200임을 먼저 확인한다.

실행 TRY1:
- 시작 UTC 2026-10-16 14:32:23.498662 / KST 23:32:23.498662
- 종료 UTC 2026-10-16 14:32:28.539417 / KST 23:32:28.539417
- 실제 경과 5.04075초; pytest 4.58초
- 결과 5 passed, 1 warning, exit0. warning은 기존 audioop의 Python3.13 제거 예정 경고.
- 원본 /tmp/m10-history-TRY1.xml, 시간/정확명령 /tmp/m10-history-TRY1.json, 출력 /tmp/m10-history-TRY1.txt

```sh
PYTHONPATH=apps/orchestrator/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/integrations/call_history/test_call_conversation.py tests/integrations/call_history/test_inbound_call_history.py -q --junitxml=/tmp/m10-history-TRY1.xml
```

부모가 표준 시험 로그/영속 로그와 Git 커밋을 처리한다. 본 하위 작업은 보존 기존5건/실제 전화/운영 배포 시험을 수행하지 않았다. 실제 전화→파일→조회와 사용자 청취는 미검증이며 이5건으로 대체하지 않는다. 실패 수정/재실행 없음. 후속 AST compile 및 JUnit 사례별5 PASS 대조 완료(시험 재실행 아님).

## 로컬 검증용 운영 probe 구현 위임

기존 조회 파일 소유권 부모 반환. tests/integrations/ht813/m10_probe.py와 test_m10_probe.py만 소유. 승인된 로컬 합성 HTTP 검증으로 probe 안전 동작을 확인하며 실전화 실행은 금지. 구체 CLI/비공개 설정 계약은 부모 메시지를 따른다. 부모는 m10_live_app.py와 해당 관측 시험을 소유해 파일 충돌을 피한다.


### 운영 probe 구현·검증 인계 — 2026-10-16 23:44 KST

소유 두 파일 `tests/integrations/ht813/m10_probe.py`, `test_m10_probe.py` 구현 완료. 기존 조회 파일은 부모에게 반환했으며 이후 수정하지 않았다. Git/index/운영호스트/실전화/외부 네트워크 접근 없음. 부모가 표준로그·문서·커밋을 담당한다.

구현 계약:
- commands: preflight, reject-dial, dial, cancel, confirm-ring, observe, history. `--config-file` 필수, dial은 `--case F02|C --approval-id <응답참조> --max-seconds <=240`. 고정된 number_file 한 번호만 사용하며 별도 target-alias는 받지 않는다. 웹hold는 부모 담당.
- config는 base_url/token_file/number_file/state_file 네 키만 허용. literal loopback HTTP+명시port만 허용, DNS/userinfo/path/query/fragment/HTTPS 거부. CLI httpx는 trust_env=False·redirect=False. 상대경로/심볼릭링크/다른사용자/다중hardlink를 거부하며 파일0600, 직접 부모 디렉터리0700/본인소유 필요. state 파일 초기 내용은 {}.
- State는 fcntl lock과0600 임시파일→원자replace·fsync. case/approval_id 중복을 차단하고 HTTP POST 전에 consumed를 디스크에 확정한다. POST 자동재시도 없음. 응답 소실은 ID가 없으면 정상shutdown 필요로 보고하며 재발신불가.
- 사용자 confirm-ring 외에는 ring_confirmed를 설정하지 않는다. watchdog는 POST시점부터 monotonic15초이며 active도 벨 확인을 대체하지 않는다. helper가15초 전에 확인을 관측하지 못하면 취소한다. 명시 max_seconds도 취소를 유발한다. HTTP 요청 timeout은2초와 남은deadline의 최소값. DELETE202는 회수완료가 아닌 cancel_requested이며 실제 BYE/Idle은 부모 관측 필요.
- 별도 cancel중 들어온 낡은GET active가 cancel_requested를 덮어쓰지 않는다. 이미 취소요청된 사례는 DELETE를 자동중복하지 않는다.
- reject-dial은 config 단일 허용번호와 다른 합성5자리 및 *00/#만 제출한다. 실제 서버allowlist와 config번호의 일치는 P0가 소유한다. 예상외202면 ID저장/DELETE, ID없으면 shutdown_required. 403/422만 통과하고 SIP INVITE0은 별도관측필요로 보고한다.
- observe는 초기 전체목록 baseline 후 신규ID가 정확1개일 때만 저장, 복수신규ID는 실패. 최대100페이지로 제한한다. 수신event와 실제통화상관은 부모가 확인. F04-A busy는 새 수락ID가 없으므로 observe성공 대상이 아니다.
- history는 보관ID 각각의 응답ID/턴순서/최소2개 user-assistant 쌍을 검사하며 IDs/본문을출력하지 않는다. distinct_case_ids와content_comparison_required를 분리한다. 실제의미/청취·문맥일치 및 전화외부경계는 판정하지 않는다.
- stdout은 고정reason/status·사례별칭·boolean 등 메타데이터뿐. 오류문자열/HTTP본문/키/토큰/번호/실제session_id는 출력하지 않는다. CLI가 잠시 HTTP로그를 차단한 뒤 기존로깅상태로 복원한다.

실행 결과(모두 MockTransport·tmp_path·합성비밀, 외부접속0):
- TRY1: UTC 2026-10-16T14:41:04.286962+00:00 ~ 2026-10-16T14:41:11.041458+00:00, 경과 6.754493초; tests=28, failures=0, errors=0, exit=0. 원본 /tmp/m10-probe-TRY1.xml/.json/.txt
- TRY2: UTC 2026-10-16T14:43:27.748236+00:00 ~ 2026-10-16T14:43:37.720242+00:00, 경과 9.971996초; tests=36, failures=0, errors=0, exit=0. 원본 /tmp/m10-probe-TRY2.xml/.json/.txt
- TRY3: UTC 2026-10-16T14:44:41.581295+00:00 ~ 2026-10-16T14:44:42.089764+00:00, 경과 0.508461초; tests=1, failures=0, errors=0, exit=0. 원본 /tmp/m10-probe-TRY3.xml/.json/.txt

TRY1 28PASS 뒤 자체검토로 늦은벨확인·동시취소·정상종료·잘못된상한 검증을 추가했다. TRY2 전체36PASS. 이후 CLI로깅복원 변경의 영향시험만 TRY3 1PASS/35deselected(새실패아님). 각정확명령은 JSON에저장됐다.

```sh
PYTHONPATH=apps/orchestrator/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/integrations/ht813/test_m10_probe.py -q --junitxml=/tmp/m10-probe-TRY2.xml
PYTHONPATH=apps/orchestrator/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/integrations/ht813/test_m10_probe.py -k argument_errors -q --junitxml=/tmp/m10-probe-TRY3.xml
```

부모에게 두파일 소유권 반환. 실제환경 도구기동/실전화는 실행하지 않았으며 watchdog 실시간지연과 SIP/FXO회수는 가짜시간검증으로 합격을대신할수없다. 승인참조문자열은 사용자가실제로승인했다는증거 자체가아니므로 부모가응답을확인한뒤에만 호출한다.

## F04 최소 WebSocket 제어 보강

부모가 m10_probe.py 소유권을 회수했다. 후속 소유 파일은 `tests/integrations/ht813/m10_web_probe.py`, `test_m10_web_probe.py` 두 개뿐이다. 기존 wsproto 의존성으로 loopback `/voice`에 인증 연결해 hold/busy 두 명령을 제공한다. 신규 라이브러리/제품 변경 없음. 로컬 fake/loopback 승인 범위만 검증하며 운영 접속0. 부모는 표준 로그와 Git을 담당한다.


### F04 웹 제어 보강 완료 — 2026-10-16 23:55 KST

`m10_web_probe.py`, `test_m10_web_probe.py` 두 파일만 추가했다. 기존 m10_probe는 부모 소유로 수정하지 않았다. 신규 의존성·음성 프레임·실전화·운영 접속·Git 변경 없음. 지정 두 파일 소유권을 부모에게 반환한다.

- CLI는 hold|busy, --config-file, --seconds(0초 초과·최대60초)만 제공한다. 기존 Config를 direct script/package 양쪽에서 재사용하며 loopback /voice에 wsproto로 연결한다.
- 인증 subprotocol은 voice-agent와 token.<비공개 token>이다. 서버의 voice-agent 선택을 검사하고 start JSON을 전송한다.
- 실제 라우터는 gate 획득 이전에 started를 보내므로 이것만으로 점유 성공을 알리지 않는다. 같은 메모리 session_id의 starting/listening 이벤트 뒤 session_started=true를 즉시 flush한다. UUID는 파일·출력에 남기지 않는다.
- hold는 음성/무음 PCM 없이 시간을 기다린 뒤 cancel·close를 보낸다. busy는 실제 error/busy를 받아야 성공하며 빈 슬롯의 started/starting은 busy 성공으로 보지 않는다. socket close는 2초 내 정상1000/1001 acknowledgement를 확인한다. 조기 종료·오류·예상치 않은 음성/처리 이벤트는 실패다.
- stdout은 고정 reason/boolean뿐이며 HTTP debug 로그를 차단하고 종료 뒤 복원한다. 예외 원문·서버 텍스트·번호·token·UUID는 출력하지 않는다.
- 로컬 시험은 실제 web_voice_router와 가짜 SilentRunner·SingleSessionGate·127.0.0.1 임시 포트를 사용했다. hold 중 실제 두 번째 웹 busy 및 cancel 후 다음 hold를 검증했고 오디오 수신0을 확인했다. direct/package --help는 접속 없이 import 확인한다.

실행 결과:
- TRY1: UTC 2026-10-16T14:53:18.671245+00:00 ~ 2026-10-16T14:53:21.571904+00:00, 경과 2.900642초; tests=13, failures=1, errors=0, exit=1. 원본 /tmp/m10-web-TRY1.xml/.json/.txt
- TRY2: UTC 2026-10-16T14:54:11.821819+00:00 ~ 2026-10-16T14:54:14.725101+00:00, 경과 2.903289초; tests=13, failures=0, errors=0, exit=0. 원본 /tmp/m10-web-TRY2.xml/.json/.txt
- TRY3: UTC 2026-10-16T14:55:07.992683+00:00 ~ 2026-10-16T14:55:10.840265+00:00, 경과 2.847573초; tests=14, failures=0, errors=0, exit=0. 원본 /tmp/m10-web-TRY3.xml/.json/.txt

TRY1 실패 원인: busy JSON과 close 프레임이 같은 TCP 읽기에 도착하면 wsproto는 이미 REMOTE_CLOSING인데 cleanup이 cancel부터 전송하려 해서 close_acknowledged=false가 됐다. 큐의 peer close부터 처리하고 정상 close만 acknowledgement로 인정하도록 수정했다. TRY2 13PASS 후 동일 TCP 읽기를 강제하는 결정적 fake-wsproto 회귀 사례를 추가해 TRY3 14PASS를 확인했다. 기존 assertion은 약화하지 않았다.

```sh
PYTHONPATH=apps/orchestrator/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/integrations/ht813/test_m10_web_probe.py -q --junitxml=/tmp/m10-web-TRY3.xml
```

부모가 표준 로그·영속 기록·Git을 처리한다. 실제 전화↔웹 충돌 및 운영 키/모델 환경은 미검증이다. 이 결과는 가짜 runner를 사용한 실제 로컬 WebSocket/라우터/공유 gate 경계다.
