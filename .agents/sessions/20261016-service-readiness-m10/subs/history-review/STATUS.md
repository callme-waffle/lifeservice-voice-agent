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
