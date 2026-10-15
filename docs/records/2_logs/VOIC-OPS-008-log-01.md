# 0. 로그 정보

|key|value|
|---|---|
|로그 ID|VOIC-OPS-008-log-01|
|원본 이슈|[VOIC-OPS-008](../0_issues/VOIC-OPS-008.md)|
|실행 계획|[VOIC-OPS-008-plan](../1_plans/VOIC-OPS-008-plan.md) — proposed; 이번 작업은 실행 전 현황 조사|
|기록 시간|2026-10-16 00:02:39 KST|
|세션 ID|20261015-service-readiness|
|기록 에이전트|Codex|

---

# 1. 실행 요약

사용자가 프로젝트의 현황과 서비스 개시까지 남은 작업의 계획을 요청했고, 첫 범위를 전화 착신·허용 번호 발신·통화내역 조회로 지정했다. 저장소 문서·소스·배포·기존 시험 증거와 GitHub PR 상태를 읽기 전용으로 대조했다. 서비스 개시를 위한 OPS-008 이슈와 M9~M12 제안 계획을 작성했다. 구현·기동·실전화·시험 실행·배포·원격 문서 게시·커밋은 수행하지 않았다.

현재 판정은 **핵심 기능 구현과 일부 실전화 성공은 있으나 상시 서비스 개시는 미검증**이다. 소스 병합과 운영 적용을 구분했다.

---

# 2. 수행 내용

## 대상 마일스톤: M0. 현황 조사·계획 수립

M0는 조사 세션 표시이며 새 실행 마일스톤을 할당한 것이 아니다. 제안된 M9~M12는 실행하지 않았다.

### 현황 대조

- 수행 작업: AGENTS.md, 이슈/계획/ADR/시험 워크플로, 템플릿, 기존 세션, 컴포넌트 README, PRD/SRS, 관련 결정·계획·로그, 배포와 스크립트 및 원격 병합 소스를 조사했다.
- 종료조건 충족 여부: 구현·시험·배포·운영 공백을 분리하고 과거 세션과 현재 원격의 불일치를 확인했다.
- 스캐폴드/더미 사용 여부: 없음.
- 관련 커밋: 로컬 HEAD `ec5f5dc`; 원격 추적 `080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244`.

### 계획 작성

- 수행 작업: 기존 이슈 001~007과 중복되지 않는 릴리스/상시 운영/개시 판정 작업을 VOIC-OPS-008로 등록했다. 기존 M8 다음 M9~M12를 배정하고 마일스톤 4개·Slice 9개·Task 18개를 작성했다.
- 종료조건 충족 여부: 전화 우선 범위·진행 순서·담당 역할·공수 가정·검증/개시 게이트·실패 시 복구·후속 제외 범위를 명시했다.
- 스캐폴드/더미 사용 여부: 없음. 수치 수용 기준은 승인 전 제안으로 표시했다.
- 관련 커밋: 없음; 작업 폴더에 신규 문서로 작성했다.

---

# 3. 검증 결과

## A. 실행한 검증

```text
git -c safe.directory=/workspace/voice-agent status --short
git -c safe.directory=/workspace/voice-agent log -5 --oneline
git -c safe.directory=/workspace/voice-agent log -1 --oneline origin/dev/v0.0.1
git -c safe.directory=/workspace/voice-agent show origin/dev/v0.0.1:<대상 파일>
git -c safe.directory=/workspace/voice-agent ls-tree -r --name-only origin/dev/v0.0.1 <대상 경로>
GitHub get_pr_info: callme-waffle/lifeservice-voice-agent #1, #2
GitHub fetch_file: dev/v0.0.1 / apps/orchestrator/src/voice_agent/channels/ht813/operator.py
```

|검증 대상|관측 결과|해석/한계|
|---|---|---|
|작업 폴더|dev/v0.0.1 ec5f5dc. 기존 미추적 OPS-002와 GPU 세션 존재|기존 파일은 변경하지 않음|
|원격 PR #1|merged=true, c2d0280, 2026-10-11 21:44:36 KST 병합|착신내역 구현 병합 확인|
|원격 PR #2|merged=true, 080f5d3, 2026-10-11 21:50:08 KST 병합|대화내역 구현 병합 확인|
|원격 조회 소스|operator.py blob e2b687981fe954d11b8fabe0d3d936b486208c91, 로컬 origin 추적 객체와 동일|두 API 공존·localhost Bearer 제한 직접 확인. 전체 원격 트리의 재동기화는 수행하지 않음|
|원격 계획 M7/M8|두 계획 모두 executed|로컬 세션의 “미구현/승인 대기” 설명을 최신 현황으로 쓰지 않음|
|PR 시험 결과|#1 117건, #2 최초 111건, 병합 조합 122건 통과라고 PR 본문에 기록|서로 더해 누적 커버리지로 계산하지 않음. 이번 조사 재실행 아님|
|원격 실행 증거|origin/dev/v0.0.1의 docs/records/2_logs·과거 세션/시험 로그가 로컬보다 빠져 있음|공개 안전화 이력 차이. 과거 자료를 무분별하게 다시 게시하지 않고 안전한 요약 필요|
|배포 자원|STT/TTS/backend Compose·restart·healthcheck·secrets 경로 존재|키 파일의 재부팅 후 준비까지 보장하지 않음|
|운영 패키지/자동 검사|원격 deploy/package에는 .gitkeep, .github에는 PR 템플릿 확인|릴리스 패키지와 저장소 내 CI workflow는 확인되지 않음. 외부 CI 유무는 미확인|
|관측|Prometheus 설정에 scrape 4개 존재, 경보 규칙/전달 설정 없음|가시화와 장애 알림은 구분. 외부 운영자 알림 수단 존재 여부는 미확인|
|과거 착신|log-55에서 2통화·두 번째 2턴·BYE/RTP/Idle|정밀 종료시각·장기 신뢰성 미검증|
|과거 발신|log-58에서 실제 수신/연결·상대 종료 1회|음성 두 턴·DTMF 미실행. BUG-003 원인 미확정|
|과거 모델|log-49에서 동시 ready·TTS 워밍업 후 0.327초·격리 상태 복구|합성 TTS 단독 값. 실제 전화 전체 지연 합격 근거 아님|
|과거 보존|보존 TRY1의 실제 파일 경계 5건 PASS|운영 키 복구·재부팅 성공 증거 아님|
|과거 웹|Chrome 합성 PCM 경계 TRY3 PASS|실사용 마이크 UI 검증 아님, 첫 전화 개시 범위 제외|

## B. 결과 판정

현재 기능 상태는 읽기 전용 조회로 대조했다. 오늘의 GPU VM·HT813 실제 가동 상태, 서비스 성능, 비밀값과 운영 데이터는 조회하지 않았다. 마지막 현장 기록의 임시 백엔드 정리를 오늘의 실시간 상태로 표현하지 않았다. 새 이슈·계획·로그에 대해 WBS 4개 마일스톤/9개 Slice/18개 Task의 고유 ID와 필수 5개 필드, 각 Milestone/Slice 하위 순서 도식, 로컬 링크 33개, proposed/Gate 미승인 상태, 미치환 템플릿 없음, Git 공백 검사를 통과했다. 애플리케이션 변경이 없으므로 코드 테스트는 실행하지 않았다.

---

# 4. 계획 대비 이탈 사항

새 제안 계획의 실행이 아니므로 실행 순서 이탈은 없다. 초기 셸 샌드박스가 bwrap 네트워크 초기화 오류로 실패해 승인 검토를 거친 명령으로 파일을 읽었다. Git 소유권 검사에는 명령별 safe.directory를 사용했으며 전역 Git 설정은 변경하지 않았다. 사용자 문체 지침을 읽었으나 해당 검색 도구가 노출되지 않아 개인 문체를 검색했다고 주장하지 않고 저장소의 한국어 템플릿을 따랐다.

---

# 5. 미해결 사항 / 후속 작업

1. 제안 계획 실행 및 새 통합 시험 Gate 1 승인 대기. 현재 계획 작성 요청만으로 배포·실전화 승인을 추정하지 않는다.
2. M9에서 현장 상태·실제 배포 SHA·키 복구 대안·품질 목표·운영 담당/시간을 확정한다.
3. M10에서 발신 두 턴·DTMF·정밀 종료·충돌·실제 조회 경계를 검증한다.
4. M11에서 재현 가능한 배포·경보·성능·재부팅·데이터/키 복구를 완성한다.
5. M12에서 72시간 제한 운영과 운영 인수를 거쳐 개시를 판정한다. 웹/FXS는 후속으로 남긴다.

---

# 6. 참고자료

- [계획](../1_plans/VOIC-OPS-008-plan.md), [이슈](../0_issues/VOIC-OPS-008.md)
- [과거 모델·관측 검증 — 비공개 원문 대신 공개 요약](../../guides/service-readiness-baseline.md), [착신 성공 — 비공개 원문 대신 공개 요약](../../guides/service-readiness-baseline.md), [발신 부분 성공 — 비공개 원문 대신 공개 요약](../../guides/service-readiness-baseline.md)
- [보존 경계 시험 — 비공개 원문 대신 공개 요약](../../guides/service-readiness-baseline.md), [브라우저 경계 시험 — 비공개 원문 대신 공개 요약](../../guides/service-readiness-baseline.md)
- [PR #1](https://github.com/callme-waffle/lifeservice-voice-agent/pull/1), [PR #2](https://github.com/callme-waffle/lifeservice-voice-agent/pull/2)
- [원격 조회 소스](https://github.com/callme-waffle/lifeservice-voice-agent/blob/080f5d3472d58d6bfdbbb3a2b5fa4b922bcec244/apps/orchestrator/src/voice_agent/channels/ht813/operator.py)

## M9 공개 이관 주석 (2026-10-16 KST)

위 본문은 당시 조사·승인 상태를 보존한다. 공개 기준에 없는 과거 세션/시험 원문 링크만 공개 요약으로 바꿨다. M9 독립 채팅은 이후 실제 시작됐으며 최신 상태는 [M9 실행 로그](VOIC-OPS-008-log-03.md)를 따른다.
