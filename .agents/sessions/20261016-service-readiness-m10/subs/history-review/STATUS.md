# Sub-agent Status

|key|value
|---|---
|Agent Name|history-review
|Parent Session|20261016-service-readiness-m10
|State|done <!-- static review only -->
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
