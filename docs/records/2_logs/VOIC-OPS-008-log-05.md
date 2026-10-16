# 0. 로그 정보

|key|value|
|---|---|
|로그 ID|VOIC-OPS-008-log-05|
|원본 이슈|[VOIC-OPS-008](../0_issues/VOIC-OPS-008.md)|
|실행 계획|[VOIC-OPS-008-plan 부록 A](../1_plans/VOIC-OPS-008-plan.md#부록-a-m10-gate-2-실행안) — 전체 approved, M10 실행안 proposed|
|기록 시간|2026-10-16 KST|
|세션 ID|20261016-service-readiness-m10|
|기록 에이전트|Codex M10 담당|

# 1. 실행 요약

M9 MR #3 병합 소스에서 M10 전용 worktree를 만들고 정적 조사·시험 매핑·구체 Gate 2 실행안을 작성했다. 첫 산출물은 draft 실행안 MR이며 M10 결과 MR이 아니다. 현장 일정·참여자·접속·실제 배포 SHA/이미지·FXS 준비가 미확정이다. 필수 입력 없이 실전화/배포가 승인됐다고 처리하지 않는다.

통합시험 생성/실행·단위 재실행·운영 접속·시험 배포·실전화·키 전달·VM 조작은 수행하지 않았다. 새로운 시험 경로/CLI/배포 overlay는 승인 후 생성 범위로 문서에 제시했으며 구현물로 세지 않는다.

# 2. 수행 내용

## 대상 마일스톤: M10. 실제 전화·조회 사용 흐름 완결

### M10-S1. 발신·착신·회선 수명 검증 준비

- 원격 `dev/v0.0.1`을 fetch해 `f1c208811fb0e04208e384242f674ebd670c8857` 확인. M9 병합 포함 검사 후 `/tmp/voice-agent-m10`, `codex/ops008-m10-telephony` 생성. M9 이후 차이 없음.
- 부모 관리 브랜치·미추적 OPS-002/GPU 세션과 M9 worktree는 변경하지 않았다. 부모 log-04만 검토 후 선택 이관했고 부재한 부모 로컬 링크 두 곳을 일반 참조로 바꾸고 이관 주석을 추가했다. 부모 이력은 통합하지 않았다.
- P0/D01~D03/F01~F05, 통화 수·회수 기준·원복·30분 창·발신별 요청/응답 기록을 실행안에 매핑했다. D03/F02는 동일 통화다. 기본 후보에 처리 중 상대 종료·발신 운영 취소를 추가해 최대 8시도로 제안했다. 확정 일정/승인이 아니다.
- 종료조건 충족 여부: 준비 문서 작성. S1 실제 전화 종료조건은 미검증이며 완료 처리하지 않는다.
- 스캐폴드/더미 사용: 없음. 실행안의 향후 도구는 미구현 제안이다.

### M10-S2. 내역·충돌·실패 검증 준비

- 조회 계약과 기존 합성 시험을 실제 통화 경계와 구분했다. 착신·대화 2건과 보존 5건은 코드상 7개 사례이며 이번 실행 PASS 수가 아니다.
- 기존 착신 시험은 fake 미디어 INVITE→CANCEL, 대화 시험은 직접 텍스트 보존이므로 실전화 ID→파일→조회 증거가 추가로 필요하다.
- 현재 발신 이벤트 수집은 CallState만 처리하고 live_app은 발신 허용 목록을 비우므로 그대로 F02에 사용할 수 없다. Gate 2 후 메타데이터 관측 wrapper/driver 생성 범위를 제안했다.
- DELETE 운영 API는 발신만 취소한다. 착신은 상대 종료 또는 backend 정상 종료가 필요하다. 로컬 BYE 이후 장비 응답 대기를 보장하지 않으므로 `202`·ended·RTP 해제와 현장 FXO Idle을 별도로 기록하도록 했다.
- 최종 응답은 TTS 전에 저장될 수 있어 재생 중 종료에도 assistant 텍스트가 남을 수 있다. 부분 턴과 착신 `incomplete`를 구분했다.
- 종료조건 충족 여부: 정적 매핑 완료. S2 실장/조회·실패 경계는 미검증이다.
- 스캐폴드/더미 사용: 없음.

### 승인 상태 정합화

M9 MR #3은 GitHub 연결로 merged=true, merge SHA와 head/병합 시각을 재확인했다. 병합자 callme-waffle은 사용자 인계 및 부모 log-04의 API 대조 근거를 사용한다(현재 연결 응답에는 merged_by 필드가 없음). M9 수치·ADR-013 B안 설계는 인수 상태로 현재 계획·계약·이슈·PRD/SRS에 반영했다. PRD/SRS 변경은 각각 독립 커밋으로 분리한다. 과거 log-01~03과 M9의 소유 STATUS는 수정하지 않고 현재 M10 STATUS에 병합 전 표기와의 차이를 기록한다. ADR-013 구현은 M11이다.

# 3. 검증 결과

## A. 실행한 검증

```text
codex_app list_threads — M10 thread/host 및 부모·M9와의 구분 확인
git -c safe.directory=/workspace/voice-agent fetch origin dev/v0.0.1
git -c safe.directory=/workspace/voice-agent merge-base --is-ancestor f1c208811fb0e04208e384242f674ebd670c8857 origin/dev/v0.0.1
GitHub get_pr_info(repository_full_name=callme-waffle/lifeservice-voice-agent, pr_number=3)
git diff 080f5d3 HEAD -- apps deploy scripts tests — M9 실행 코드 변경 없음
```

모든 필수 참조와 기존 시험을 읽었다. BUG-003 독립 plan 파일은 병합 소스에 없으며 BUG-003 이슈·OPS-008 계획·M6 실행서가 진단 순서를 소유한다. 비공개 과거 TRY 원문은 재게시하지 않았다. 두 서브에이전트가 전화 수명/조회 경계를 병렬 정적 조사했고 각자 sub STATUS에 근거를 남겼다. 부록 A의 독립 재검토 및 최종 문서 검증 결과는 아래 게시 추적에 기록한다.

## B. 결과 판정

M10 준비·구체 실행안 작성 상태이며 실제 사용 흐름 완결은 미검증이다. 현재 shell에는 SSH 별칭 파일이 없고 배포 대상이 확인되지 않아 운영 접속을 시도하지 않았다. 사용자에게 시험 일정·역할·PSTN/FXS 준비와 기존 SSH 별칭·배포 디렉터리를 질문했다. 현재 응답 없음. 실제 배포 SHA/이미지를 후보 값으로 추정하지 않았다. M9의 120+3 단위 PASS는 과거 근거로만 참조한다.

# 4. 계획 대비 이탈 사항

실행 순서 이탈 없음. Gate 2 전 정적 조사·문서 작성만 수행했다. 실제 배포/현장 입력이 없어 실행안은 draft로 제출하며, 입력이 채워진 최종 실행안 MR 병합을 기다린다. 새 기본 통화 후보는 추가 중단/취소를 포함하므로 기존 후보 수를 승인받은 수로 재사용하지 않는다.

초기 sandbox는 `bwrap: loopback: Failed RTM_NEWADDR` 오류로 읽기조차 실패했다. 이후 승인 검토를 거친 명령별 escalation 및 `safe.directory`를 사용했고 전역 Git 설정은 변경하지 않았다. 사용자 문체 스킬은 읽었으나 검색 도구가 없어 저장소 한국어 템플릿과 사용자 형식을 따랐다.

# 5. 미해결 사항 / 후속 작업

1. A2의 일정/참여 역할/FXS·PSTN·시각 근거, A3의 실제 배포/이미지·비밀 경로/백업 복원 가능성을 확정해 실행안 MR을 갱신한다.
2. Gate 2 사용자 병합 전 시험 생성/실행·배포·실전화 금지. 별도 매 발신 직전 명시 응답이 필요하다.
3. 승인 후 관측 도구·필요 시험을 만들고 정적/단위 검증 후 승인 범위만 실행한다. 새로운 결함·중대한 변경은 해당 workflow로 추적한다.
4. 결과 MR에서 PASS/FAIL/미검증·BUG-003 잔여 위험·F05 등 현장 불가 예외를 사용자에게 판정받는다. M10 결과 병합 뒤에만 M11 인계문을 작성한다.

## 부모 취합용 보고

|필드|내용|
|---|---|
|단계|M10 준비 / Gate 2 실행안 proposed, 전체 M10 미완료|
|담당 thread|01a1405f-3b4b-7ef2-81cb-016c3a52beb4|
|host|remote-ssh-codex-managed:0535a69a-75b5-4b00-a34d-40c89933dcba|
|부모 thread|01a14007-f09a-7f43-a8c2-253563abfe26|
|STATUS|[M10 STATUS](../../../.agents/sessions/20261016-service-readiness-m10/STATUS.md)|
|브랜치/기준|codex/ops008-m10-telephony / f1c208811fb0e04208e384242f674ebd670c8857|
|실행안 MR·최종 SHA|게시 뒤 아래 추적 기록과 MR metadata로 식별|
|Gate 2 승인 SHA/시각|미승인 / 없음|
|결과 MR|없음 — 미검증|
|통과/실패/미검증|정적 조사 완료; 애플리케이션 시험 실행 0, 실전화 0, 운영 배포 0|
|차단|현장 입력·실제 배포 기준 미확인, Gate 2 미승인|

현재 도구에 send_message_to_thread가 없어 부모 자동 송신은 하지 않았다. 부모는 이 보고·STATUS·MR을 읽어 취합할 수 있다.

# 6. 참고자료

- [M9 인수 log-04](VOIC-OPS-008-log-04.md), [M9 당시 log-03](VOIC-OPS-008-log-03.md)
- [운영 계약](../../guides/service-readiness-contract.md), [공개 기준·과거 증거](../../guides/service-readiness-baseline.md)
- [전화 검토](../../../.agents/sessions/20261016-service-readiness-m10/subs/telephony-review/STATUS.md), [조회 검토](../../../.agents/sessions/20261016-service-readiness-m10/subs/history-review/STATUS.md)

## 정적 검증·검토 결과

- `/tmp/validate-m10-docs.py`: 변경 Markdown 11개, 상대 링크 98개(새 참조 16개), 누락 0, 코드 fence/한국어 검사 오류 0, 부록 shell block 4개 `bash -n` 통과. 명령을 실행한 것이 아니라 문법만 검사했다.
- `git diff --check`: 통과. 변경은 문서만이며 애플리케이션/배포/시험 코드와 운영 값이 포함되지 않는다.
- 독립 검토의 공통 통화 ID 전달 지적과 빌드 경로·원복 중지/부재 분기·watchdog·실제 페이지 표본·시험 중복을 수정했다. 두 검토자가 재확인 후 검토 범위 내 미해결 0건으로 보고했다.
- 원복 `up --no-start` 및 `rm`의 볼륨 보존 의미는 [Docker up](https://docs.docker.com/reference/cli/docker/compose/up/)·[Docker rm](https://docs.docker.com/reference/cli/docker/compose/rm/) 공식 문서로 확인했다. 현장 Compose 버전·실행 결과는 미확인이다.
- PRD/SRS는 각각 독립 커밋하며 나머지 준비 문서와 섞지 않는다. GitHub 게시 트리는 로컬 검증 트리와 비교하고 MR에 연결한다.

## 게시 추적

[M10 실행안 MR #4](https://github.com/callme-waffle/lifeservice-voice-agent/pull/4)를 2026-10-16 01:41:17 KST에 draft로 생성해 이 채팅에 연결했다. base는 dev/v0.0.1 / f1c2088이다. GitHub 연결로 게시했으며 로컬과 원격의 각 tree SHA를 대조했다. 작성자/시각 차이에 따른 commit SHA 차이만 있고 파일 내용·모드는 같다. 로컬 이력은 그대로 보존하고 부모 이력을 게시하지 않았다.

|작업|로컬 검증 커밋|동일 트리 원격 커밋|
|---|---|---|
|PRD 단독|8938c616c67d0998f014bf6d73a14542a37bba85|c9d2a9963ba6b5703ef184623448c3e0e594a9b3|
|SRS 단독|06f9fa62b10ad75564f4981c570aadedd93277db|6f46649e23a00f05ffb7dc6e32acdea9908b3476|
|실행안·정적 증거|76cb5b9822c6aa368ce35721d8a7952b1c74fb77|bce6334a4eb6590c2e75b2fc2acd01a9177eef4a|

본문 검증 tree는 `da70160a71d98b53f8aa4690868e7f8a18a60813`이다. 이후 변경은 본 게시 기록과 M10 STATUS에 MR 링크를 추가하는 문서 커밋뿐이다. 최종 head는 이 기록을 포함한 MR metadata로 식별한다. 현재 Gate 2 미승인·현장 입력 대기·결과 MR 없음·M10 미완료 상태를 유지한다. 부모 직접 메시지 대신 이 로그와 MR을 조회할 수 있게 남겼다.
