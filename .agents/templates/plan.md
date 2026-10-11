# 0. 계획 정보

|key|value
|---|---
|계획 ID|VOIC-{{ISSUE_TYPE}}-000-plan
|원본 이슈|[VOIC-{{ISSUE_TYPE}}-000](../0_issues/VOIC-{{ISSUE_TYPE}}-000.md)
|상태|proposed
|작성 시간|YYYY-MM-DD HH:MM:SS
|작성 에이전트|???
|승인자|(승인 전)
|승인 일시|(승인 전)

---


# 1. 개요

## A. 목표


## B. 범위


## C. 제외 범위 (Non-goals)


---


# 2. 영향 컴포넌트

<!-- 이 목록은 "애플리케이션 레이어에 대한 수정부"만을 의미한다.
     docs/, AGENTS.md, .agents/ 등 문서·거버넌스 파일은 계획이 수정하더라도 여기에 포함하지 않는다
     (범위와 WBS에만 명시할 것).
     apps/ 하위의 실제 컴포넌트 디렉토리명으로 기재한다. -->

- [ ] apps/{{component}}
- [ ] deploy/
- [ ] tests/


---


# 3. 작업 분해 구조 (Milestone / Slice / Task)

<!--
번호 규칙:
- Milestone(M<n>): 프로젝트 전체 누적 번호. 기존 계획들을 스캔해 max+1부터 시작.
- Slice(M<n>-S<m>): 부모 Milestone 내에서만 고유. Milestone마다 S1부터.
- Task(M<n>-S<m>-T<k>): 부모 Slice 내에서만 고유. Slice마다 T1부터.
모든 Milestone/Slice/Task에 진행 배경·진행 목적·AS-IS & TO-BE·작업 종료조건을 명시할 것.
Milestone에는 하위 Slice의, Slice에는 하위 Task의 진행 순서 mermaid를 포함할 것.
-->

## M{{n}}. {{마일스톤 이름}}

- 진행 배경:
- 진행 목적:
- AS-IS:
- TO-BE:
- 작업 종료조건:

### Slice 진행 순서

```mermaid
flowchart TD
    S1[M{{n}}-S1 {{이름}}] --> S2[M{{n}}-S2 {{이름}}]
    S1 --> S3[M{{n}}-S3 {{이름}}]
    S2 --> S4[M{{n}}-S4 {{이름}}]
    S3 --> S4
```

### M{{n}}-S1. {{슬라이스 이름}}

- 진행 배경:
- 진행 목적:
- AS-IS:
- TO-BE:
- 작업 종료조건:

#### Task 진행 순서

```mermaid
flowchart TD
    T1[M{{n}}-S1-T1 {{이름}}] --> T2[M{{n}}-S1-T2 {{이름}}]
    T1 --> T3[M{{n}}-S1-T3 {{이름}}]
```

#### M{{n}}-S1-T1. {{태스크 이름}}

- 진행 배경:
- 진행 목적:
- AS-IS:
- TO-BE:
- 작업 종료조건:

#### M{{n}}-S1-T2. {{태스크 이름}}

- 진행 배경:
- 진행 목적:
- AS-IS:
- TO-BE:
- 작업 종료조건:


---


# 4. 의존성

## A. 내부 의존성


## B. 외부 의존성


---


# 5. 리스크 및 대응

|리스크|영향|대응 방안
|---|---|---


---


# 6. 검증 전략

## A. 단위 테스트 (tests/units/)


## B. 통합 테스트 (tests/integrations/)

<!-- 통합 테스트는 다중 스택 결합으로 규모·토큰 소모가 크므로 기본 실행 대상이 아님.
     create-testcase.md 4장의 이중 승인(계획 시 사전승인 + 실행 직전 최종승인) 필요. -->

- 통합 테스트 필요 여부 검토 결과: 필요 / 불필요
- 검토 사유:
- 사전승인 (Gate 1): 미승인 <!-- 승인 시 승인자/일시 기재. 실행 직전 Gate 2 최종승인 별도 필요 -->
- 대상 시나리오:


---


# 7. 롤아웃 / 마이그레이션


---


# 8. 완료 게이트

- [ ] 모든 마일스톤 검증 통과
- [ ] 관련 테스트 실행 및 통과
- [ ] 실행 로그 기록 (docs/records/2_logs/)
- [ ] 관련 문서(README/guides) 갱신


---


# 9. 참고자료

- [관련 ADR](../3_decisions/)
- [REF](REF_URL_OR_PATH)
