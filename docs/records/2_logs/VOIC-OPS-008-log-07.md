# 0. 로그 정보

|key|value|
|---|---|
|로그 ID|VOIC-OPS-008-log-07|
|원본 이슈|[VOIC-OPS-008](../0_issues/VOIC-OPS-008.md)|
|실행 계획|[VOIC-OPS-008-plan](../1_plans/VOIC-OPS-008-plan.md)|
|기록 시간|2026-10-16 KST|
|세션 ID|20261016-service-readiness-m10|
|기록 에이전트|Codex|

---

# 1. 실행 요약

사용자 관리 정정을 담당 채팅에서 수신하고 M10 실행을 재개했다. MR #4는 draft WIP로 되돌렸으며 선행 병합 요구를 철회했다. 준비 문서 제출은 M10 완료가 아니다. Gate 2는 담당 채팅 명시 응답으로 받으며, 민감 데이터·D02 예외·실제 발신을 이번 정정으로 포괄 승인하지 않는다.

---

# 2. 수행 내용

## 대상 마일스톤: M10. 실제 전화·조회 사용 흐름 완결

### M10-S1. 종료·회수 구현과 검증 준비

- 수행 작업: 계획/운영 계약/STATUS의 승인 방식을 정정했다. P0를 배포 전 P0-A → 후보 기동 → 기동 후 P0-B → 실전화로 분리했다. backend 부재 상태에 backend ready를 요구하는 순환 조건을 제거했다.
- 기존 전화 단위·통합 코드를 조사해 처리/재생 종료·취소 후 다음 전화 수락의 결합 검증 공백을 확인했다. 착신 종료 task와 close가 겹치는 결함 의심을 [BUG-009](../0_issues/VOIC-BUG-009.md)로 추적하고 fake 단위 재현/수정을 위임했다. 해당 코드 소유권은 telephony-review, 공유 문서/Git/운영은 주 담당자다.
- 종료조건 충족 여부: M10 실제 종료·회수는 미검증. 7시도는 예산 상한이며 완료조건이 아님을 명시했다.
- 스캐폴드/더미 사용 여부: 제품 구현의 더미 없음. 기존 시험은 fake 경계를 사용하며 실장 증거로 계산하지 않는다.
- 관련 커밋: 관리자가 남긴 로컬 `986cc21`을 보존하고 이후 담당 변경을 누적한다.

### M10-S2. 조회·오류 경계 준비

- 기존 조회 시험에 무발화404/incomplete, 두 HT813 세션의 상호 격리, 실제 합성 암호문 손상→HTTP503 보강이 필요함을 정적 확인했다. 기존 2개 파일을 확장하는 최소안을 마련했다.
- 담당 채팅에서 로컬 격리 통합시험 Gate 2, 기존 암호문 1건 이동/메모리 인증, D02 생략을 각각 명시 질문했다. 아직 응답이 없어 통합시험 생성/실행·민감 데이터 재시도·실전화는 하지 않았다.
- 종료조건 충족 여부: 실제 통화→내역 조회 미검증. Gate 대기 중 독립 단위 검증·결함 재현 준비를 계속했다.
- 스캐폴드/더미 사용 여부: 새 통합시험 없음.

---

# 3. 검증 결과

## A. 실행한 검증

초기 기존 M4 임시 venv에는 현재 필수 의존성이 없어 orchestrator 7개 모듈/model-serving 1개 모듈이 수집 단계에서 실패했다. 앱 결함으로 판정하지 않았다. M10 전용 venv에 현재 pyproject.toml의 의존성을 설치하여 재실행했다.

|실행|결과|증거|
|orchestrator 단위 TRY1|수집 오류 7, 사례 미실행|[TRY1](../../../tests/units/orchestrator/logs/M010-TRY1.md)|
|model-serving 단위 TRY1|수집 오류 1, 사례 미실행|[TRY1](../../../tests/units/model-serving/logs/M010-TRY1.md)|
|orchestrator 단위 TRY2|120 PASS|[TRY2](../../../tests/units/orchestrator/logs/M010-TRY2.md)|
|model-serving 단위 TRY2|3 PASS|[TRY2](../../../tests/units/model-serving/logs/M010-TRY2.md)|

```sh
PYTHONPATH=apps/orchestrator/src:apps/model-serving/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml tests/units/orchestrator/testcodes -q
PYTHONPATH=apps/orchestrator/src:apps/model-serving/src /tmp/voice-agent-m10-venv/bin/python -m pytest -c apps/model-serving/pyproject.toml tests/units/model-serving/testcodes -q
```

## B. 결과 판정

M10에서 직접 재실행한 단위 120+3 PASS다. 실제 전화·조회·배포 성공을 뜻하지 않는다. BUG-009 재현/수정 검증은 후속 증거로 별도 기록한다.

---

# 4. 계획 대비 이탈 사항

사용자 정정에 따라 준비용 MR 선행 병합 조건을 제거했다. 결과 MR 사용자 병합 이후 다음 마일스톤 진행 및 에이전트 merge 금지는 유지한다. 민감 데이터 인증은 앞선 자동 승인 검토 거절을 우회하지 않으며 명시 응답까지 미실행이다.

---

# 5. 미해결 사항 / 후속 작업

- 로컬 격리 Gate 2 응답 후 조회/수명 경계를 보강·실행한다.
- 기존 암호문 1건 인증과 D02 생략은 각각 사용자 응답을 기다린다.
- 실제 환경 Gate 2는 후보·명령·영향·원복이 준비된 뒤 이 채팅에서 제시한다. 실전화 직전 매회 요청한다.
- BUG-009 단위 재현 결과를 확인하고 수정·회귀 증거를 반영한다.
- 부모 보고: M10 재개, MR #4 WIP, 단위 120+3 PASS, 실전화/실조회 미검증. 고정 일정·참여자 명단·이미 제공된 접속 정보는 차단 조건이 아니다. 직접 채팅 전송 도구가 없어 STATUS/본 로그/MR로 조회 가능하게 남긴다.

---

# 6. 참고자료

- [관리 정정 전달](https://github.com/callme-waffle/lifeservice-voice-agent/pull/4#issuecomment-6217338672)
- [MR #4](https://github.com/callme-waffle/lifeservice-voice-agent/pull/4)
- [이전 준비 기록](VOIC-OPS-008-log-06.md)
