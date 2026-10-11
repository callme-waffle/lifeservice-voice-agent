# 0. 이슈정보

|key|value|
|---|---|
|이슈 ID|VOIC-OPS-007|
|생성 시간|2026-10-11 12:36:41 UTC|
|생성자|사용자|
|생성 에이전트|Codex|

---

# 1. 이슈 내용

## A. 배경

기존 PR #1·#2의 본문은 변경 결과, 검증 결과, 운영 제약을 문단으로 작성해 리뷰어가 필요한 정보를 찾기 어렵다. 저장소에 새 PR을 위한 공통 본문 양식도 없다.

## B. 이슈 설명

사용자가 지정한 `작업개요`·`작업내용` 구조의 PR 양식을 저장소에 추가하고, 기존 PR #1·#2의 본문에도 동일한 구조를 적용한다. 이미 수행된 검증과 미검증 범위를 정확히 구분해야 한다.

---

# 2. 결정 사항

## A. 결정 내용

사용자가 이전 제안을 거절하고 제공한 Markdown 양식을 그대로 `.github/PULL_REQUEST_TEMPLATE.md`에 사용한다. PR #1·#2 본문은 각 기능의 실제 변경·검증·운영 제약으로 채운다.

## B. 결정 사유

향후 PR 작성 시 동일한 형식을 제공하고, 이미 열린 두 PR도 즉시 읽기 쉽게 만들기 위해서다.

## C. 참고자료

- [착신내역 PR #1](https://github.com/callme-waffle/lifeservice-voice-agent/pull/1)
- [대화내역 PR #2](https://github.com/callme-waffle/lifeservice-voice-agent/pull/2)
