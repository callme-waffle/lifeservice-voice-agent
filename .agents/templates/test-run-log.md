# 0. 테스트 실행 정보

|key|value
|---|---
|실행 ID|M000_S000_T000-TRY1
|작업 단위|M000-S000-T000 <!-- Milestone/Slice 범위 실행이면 해당 범위까지만 -->
|관련 계획|[VOIC-{{ISSUE_TYPE}}-000-plan](../../../../docs/records/1_plans/VOIC-{{ISSUE_TYPE}}-000-plan.md)
|세션 ID|YYYYMMDD-short-slug
|실행 에이전트|???
|실행 명령|`{{test command}}`

---


# 1. 테스트 진행 시간

|key|value
|---|---
|시작|YYYY-MM-DD HH:MM:SS
|종료|YYYY-MM-DD HH:MM:SS
|소요 시간|MM분 SS초

---


# 2. 진행된 테스트케이스 목록

|#|테스트케이스|테스트 파일
|---|---|---
|1|{{test_case_name}}|testcodes/{{path}}/{{ORIGIN_FILE_NAME}}.test.{{ext}}
|2|{{test_case_name}}|testcodes/{{path}}/{{ORIGIN_FILE_NAME}}.test.{{ext}}

---


# 3. 테스트케이스 별 통과 여부

- [ ] {{test_case_name}} — PASS/FAIL
- [ ] {{test_case_name}} — PASS/FAIL

<!-- 통과한 케이스는 체크([x])하고 PASS 표기, 실패한 케이스는 미체크([ ])로 두고 FAIL 표기 -->

---


# 4. 실패 원인분석 결과

<!-- 실패 케이스가 하나라도 있으면 필수 작성. 실패가 없으면 "해당 없음"으로 기재. -->

## A. {{실패한 테스트케이스 이름}}

- 증상:
- 원인 분석:
- 조치 방향:

---


# 5. 비고
