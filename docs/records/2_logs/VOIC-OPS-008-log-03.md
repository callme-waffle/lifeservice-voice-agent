# 0. 로그 정보

|key|value|
|---|---|
|로그 ID|VOIC-OPS-008-log-03|
|원본 이슈|[VOIC-OPS-008](../0_issues/VOIC-OPS-008.md)|
|실행 계획|[VOIC-OPS-008-plan](../1_plans/VOIC-OPS-008-plan.md) — approved|
|기록 시간|2026-10-16 KST|
|세션 ID|20261016-service-readiness-m9|
|기록 에이전트|Codex|

# 1. 실행 요약

M9 기준 버전·운영 계약을 작성하고 기존 단위 시험 123건을 통과했다. 결과 문서와 ADR은 사용자 MR 리뷰·병합 인수 대상이며 상시 운영 완료가 아니다. M10~M12는 실행하지 않았다.

사용자 입력은 운영 담당자 김화균, 매 실전화 발신 직전 먼저 요청이다. 후자는 Gate 2 승인과 별도이며 응답 전 발신하지 않는다. 실제 운영 시간·장애 연락 경로·시험 시간대는 미정이다.

# 2. 수행 내용

## 대상 마일스톤: M9. 기준 버전·운영 계약 확정

### M9-S1. 소스·증거 기준 정리

- T1: 원격 최신 `080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244`를 재조회·fetch하고 `/tmp/voice-agent-m9`의 `codex/ops008-m9-baseline` worktree를 생성했다. 부모 관리 `6245ba2` 이력을 합치지 않았다. 두 조회 API·retention·Caller ID와 `/data/calls` Compose 매핑을 확인했다.
- T2: root/component README의 오래된 미래형을 현재 소스 계약으로 바꿨다. 공개 가능한 과거 실장 요약·요구 추적·버전명 관계를 정리했다. PRD/SRS 0.1.0을 유지하고 각각 독립 커밋했다. M6 부분 완료, M7/M8 구현·합성 검증 완료, 운영 미검증을 구분했다.
- 종료조건: 소스 확인·문서 준비·기존 단위 회귀 검증 완료. 과거 운영 로그 원문·부모 세션·비밀 파일은 이관하지 않았다.
- 스캐폴드/더미 사용: 없음. 기존 fake 단위 시험은 실장 성공으로 표시하지 않았다.
- 관련 커밋: 아래 커밋·게시 추적표 참조.

### M9-S2. 개시 계약·비밀 복구 설계

- T1: 전화 우선 범위와 품질 수치·측정 분모·판정 실패 조건, 담당자·발신 직전 요청, Gate 1/2 경계와 현장 입력을 운영 계약 및 PRD/SRS에 추적했다. 기존 계획 수치는 사용자 병합 전 제안으로 유지했다.
- T2: 수동 재주입/보호된 호스트 원본/외부 저장소를 비교하고 ADR-013을 proposed로 작성했다. 같은 키 유지·별도 키 사본·암호문 백업·30일 만료·복원 순서·실패 시 시작 차단·restart 우회 방지·빈/잘못 마운트된 경로에서 정본 키·데이터 연속성을 확인할 수 없는 한계를 명시했다.
- 종료조건: 리뷰 가능한 계약·설계 준비 완료. 수치·설계 선택 및 미정 현장 입력의 최종 확정은 남아 있다. 사용자 MR 병합 전 M9 최종 인수로 표시하지 않는다.
- 스캐폴드/더미 사용: 없음. 제안된 부팅 로더·백업·경보는 M11 구현 대상이며 이 단계 구현물로 세지 않는다.
- 관련 커밋: 아래 커밋·게시 추적표 참조.

# 3. 검증 결과

## A. 실행한 검증

```text
git ls-remote origin refs/heads/dev/v0.0.1
git fetch origin dev/v0.0.1
GitHub get_pr_info #1/#2
PYTHONPATH=apps/model-serving/src:apps/orchestrator/src /workspace/voice-agent/.venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/units/orchestrator/testcodes --junitxml=/tmp/m9-orchestrator.xml -q
PYTHONPATH=apps/model-serving/src:apps/orchestrator/src /workspace/voice-agent/.venv/bin/python -m pytest -c apps/model-serving/pyproject.toml tests/units/model-serving/testcodes --junitxml=/tmp/m9-model-serving.xml -q
git diff --check
```

- 원격 SHA 일치, PR #1/#2 merged 및 각각 c2d0280/080f5d3 확인.
- orchestrator 120 PASS/5.80초, model-serving 3 PASS/2.73초, 실패·skip 0건. 각각 기존 의존성의 사용 중단 예정 경고 3건(audioop, Starlette TestClient, BlockingPortal).
- Python 3.12.3·pytest 9.1.1의 기존 가상환경을 읽기 재사용했고 source path는 격리 worktree로 지정했다. 시스템 Python에는 pytest가 없어 실행 환경을 바꿨다. 의존성 설치·앱/시험 코드 수정은 없다.
- [orchestrator 케이스별 결과](../../../tests/units/orchestrator/logs/M009_S001-TRY1.md), [model-serving 케이스별 결과](../../../tests/units/model-serving/logs/M009_S001-TRY1.md).
- 소스 조사와 요구사항 조사를 병렬 위임했고 파일 소유권을 README 3개와 PRD/SRS로 나눴다. 별도 검토 에이전트가 변경 문서·설계를 독립 검토했고 P2 두 건을 수정한 뒤 재검토에서 미해결 지적 0건을 확인했다. stage/commit은 본 세션만 직렬 처리한다.

## B. 결과 판정

이번 단위 시험은 기준 소스와 같은 앱/시험 코드로 실행했다. PR #2에 있는 과거 122건과 별개의 실행이며 통합 시험을 포함하지 않는다. 실전화 0건, 장비 변경·운영 서버 조회·배포·비밀 전달·VM 재부팅 없음. 새 통합 시험 생성/실행도 없다. 실제 배포 SHA·이미지·현장 포워딩과 회선 상태, 성능·복구·알림은 미검증이다.

변경 Markdown 19개·상대 링크 173개를 검사해 끊어진 경로 0건, 비 Markdown 변경 0건, git diff --check 통과를 확인했다. 부모 관리 브랜치 6245ba2와 기존 미추적 파일 두 항목은 그대로 보존됐다. 독립 검토·커밋 분리 결과는 아래 추적표에 기록했다.

# 4. 계획 대비 이탈 사항

계획 범위의 문서·설계 단계만 수행했다. S1 조사 두 작업을 병렬로 진행하고 소스 기준 확인 후 README·요구 문서의 소유권을 나눴다. 운영/수치 확정은 사용자 MR 리뷰로 남긴다는 인계 조건을 적용했다. 운영 시간·장애 경로의 입력 부족을 임의로 승인된 값으로 만들지 않았다.

샌드박스는 `bwrap: loopback: Failed RTM_NEWADDR`로 기본 명령 실행에 실패했다. 승인 검토를 거친 명령별 sandbox escalation과 명령별 safe.directory를 사용했으며 전역 Git 설정을 바꾸지 않았다. 사용자 문체 스킬의 검색 도구는 노출되지 않아 검색된 문체라고 주장하지 않고 저장소 템플릿을 따랐다.

# 5. 미해결 사항 / 후속 작업

- M9 결과 MR 사용자 병합 대기. 계획 approved, ADR-013 proposed, OPS-008 Gate 2 미승인 유지.
- 운영 시간·장애 연락/대체자·시험 일정·백업 매체/접근자·대표 요청·실제 통화량·현장 상태는 후속 실행 전에 확정한다.
- 실제 번호·키는 Git/채팅에 수집하지 않는다. 매 실전화 발신 직전에 김화균에게 요청한다.
- 부모가 사용자 병합의 SHA·주체·시각·검증 head 일치를 확인한 뒤에만 새 독립 M10 채팅을 착수한다. M9 채팅은 M10을 실행하지 않는다. M10 인계문은 M9 인수 후 작성한다.
- send_message_to_thread 도구가 없어 자동 부모 회신은 수행하지 못한다. 아래 보고와 STATUS·MR 링크를 부모에서 조회할 수 있게 남긴다.

## 부모 취합용 보고

|필드|내용|
|---|---|
|단계/상태|M9 문서·검증 완료, MR #3 리뷰·사용자 병합 대기; 사용자 인수 미완료|
|담당 thread|01a14026-e634-7fa3-b392-958f75b2b8e0|
|host|remote-ssh-codex-managed:0535a69a-75b5-4b00-a34d-40c89933dcba|
|STATUS|`.agents/sessions/20261016-service-readiness-m9/STATUS.md` (M9 worktree)|
|브랜치|codex/ops008-m9-baseline → dev/v0.0.1|
|기준 SHA|080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244|
|결과 HEAD/MR|[MR #3](https://github.com/callme-waffle/lifeservice-voice-agent/pull/3). 결과 HEAD는 MR의 head_sha 및 이 로그를 포함한 원격 최종 커밋으로 식별; 아래 추적표 참조|
|검증|기존 단위 120+3 PASS, 상대 링크·diff 통과, 독립 검토 지적 두 건 수정 후 미해결 0건|
|병합 SHA/주체/시각|미병합 — 해당 없음|
|다음 단계|부모의 사용자 M9 병합 확인→별도 M10 채팅. 실행 묶음 Gate 2·매 발신 직전 요청은 별도|

# 6. 참고자료

- [기준·공개 증거](../../guides/service-readiness-baseline.md), [운영 계약](../../guides/service-readiness-contract.md), [ADR-013](../3_decisions/ADR-013-secret-recovery-and-backup.md)
- [PRD](../../ideas/prd/0.1.0.md), [SRS](../../ideas/srs/0.1.0.md)
- [M9 상태](../../../.agents/sessions/20261016-service-readiness-m9/STATUS.md)

## 커밋·게시 추적 및 최종 검토

Git push는 HTTPS 자격 증명 부재로 실패했다. 비밀 탐색 없이 GitHub 연결의 tree/commit/branch 도구를 사용했다. 로컬과 원격은 커밋 작성 시각·작성자 때문에 SHA가 다르지만 각 단계의 Git tree SHA가 동일함을 검증했다. 기존 README의 실행 모드 100755도 보존했다. 부모 관리 이력은 게시하지 않았다.

|작업|로컬 검증 커밋|동일 트리의 원격 게시 커밋|
|---|---|---|
|기준·계약·ADR 초안·검증 기록|12144af2e18d19dfcecd2335848e39627bca3ef6|6e0a9e6db05ea44129e97d726ebeb5bb968461b3|
|README 별도 계약 커밋|0b770b2603984262277c15082004681a338d926c|815cc768690cfa1c3094819f3e4175d7cd91158d|
|PRD 단독 커밋|b767db66ac2a0b0938e6eb83c3f09ff0532f97db|49b0d914a082238f00064636a86fe64a20c14888|
|SRS 단독 커밋|9cfa44f84f73851d157496c8b63b6954a0e27881|1a814a0b03378549490e30719131ea6f56db241e|
|독립 검토 수정·게시 결과/상태|이 로그의 최종 기록 커밋|MR #3 최종 head 커밋; 직전 원격 parent는 1a814a0b03378549490e30719131ea6f56db241e|

수정된 P2는 (1) 기존 retention 시작 스윕의 AEAD 키 인증 보호를 설명하고 빈/잘못 마운트된 경로의 한계로 좁힘, (2) 복원 시 착신 시작 누락은 목록 없음·전체 텍스트 누락은 404임을 명시하고 백업 목록·수량·무결성 대조를 요구한 것이다. 실행 코드 변경은 없어 단위 시험 재실행은 하지 않았다. 긴 합성 PCM 매개변수의 시험 이름은 함수명+이름 해시로 줄여 케이스별 120건 결과를 보존했다.

최종 검사: Markdown 19개·상대 링크 174개 누락 0건, PRD/SRS 각각 단독 커밋, 기준 대비 앱/배포/시험 코드 무변경, 커밋의 AI 공동저자 표기 없음, 120+3개 케이스 결과 일치를 확인했다. 전체 diff 공백 검사에서 subagent STATUS의 EOF 빈 줄 1건을 발견해 제거한 뒤 재검사했다. 동일 원격 트리로 게시한 뒤 MR의 head/base·draft 해제·미병합을 재확인한다. 결과 HEAD의 자체 해시를 같은 커밋 본문에 넣을 수 없으므로 MR metadata와 Git 이력을 최종 식별자로 사용한다.
