# 0. 이슈정보

|key|value|
|---|---|
|이슈 ID|VOIC-BUG-009|
|생성 시간|2026-10-16 23:21:05 KST|
|생성자|김화균 — 승인된 M10 검증 중 발견|
|생성 에이전트|Codex|

---

# 1. 이슈 내용

## A. 배경

VOIC-OPS-008 M10은 상대 종료·운영 중단에서 SIP/RTP·세션을 회수하고 다음 전화 수락을 검증한다. 정적 조사에서 상대 BYE/CANCEL 후 시작된 비동기 종료 작업과 앱 close가 겹치는 경계를 발견했다. 실전화 재현은 하지 않았다.

## B. 이슈 설명

InboundSIPService는 BYE/CANCEL 처리에서 _terminate를 별도 task로 시작하며 _terminate 초기에 _dialog를 제거한다. 대화/보존 정리가 끝나기 전에 close가 호출되면 현재 _dialog가 없어 진행 중인 종료 작업을 기다리지 않고 반환할 가능성이 있다. 종료 저장·gate 해제가 앱의 보존 서비스 종료 뒤에 남을 수 있다. fake media/retention을 사용한 단위 재현으로 실제 실패 여부를 확인해야 한다.

---

# 2. 결정 사항

## A. 결정 내용

현재는 결함 의심이며 재현 미실행이다. 승인된 OPS-008 M10-S1/S2 종료·회수 검증 범위에서 단위 재현을 우선 수행한다. 별도 기능·마일스톤·외부 인터페이스 확장은 없다. 수정은 실패 재현과 영향 단위 검증을 근거로 판정한다.

## B. 결정 사유

앱 close 반환은 진행 중인 전화 정리의 완료와 일치해야 한다. 실제 회선·민감 데이터 없이 fake 경계와 Event로 재현 가능한지 먼저 확인한다.

## C. 참고자료

- [승인된 M10 계획](../1_plans/VOIC-OPS-008-plan.md)
- [orchestrator 계약](../../../apps/orchestrator/README.md)
- [착신 구현](../../../apps/orchestrator/src/voice_agent/channels/ht813/inbound.py)
