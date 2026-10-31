# 0. 이슈정보

|key|value|
|---|---|
|이슈 ID|VOIC-FEAT-010|
|생성 시간|2026-10-31 01:24:03 KST|
|생성자|사용자|
|생성 에이전트|Codex|

---

# 1. 이슈 내용

## A. 배경

현재 voice-agent는 HT813 직접 SIP/RTP 및 웹 WebSocket 입력을 STT → 작업 API → TTS로 처리한다. config.py는 STT 설정을 필수로 요구하고 bootstrap.py와 GPU Compose는 모델 서비스에 의존한다. 전화 conversation.py는 처리·출력 중 입력을 버린다. Live API 모델명만 바꾸어서는 동시 음성 입출력이 성립하지 않는다.

## B. 이슈 설명

사용자는 env 옵션으로 OpenAI Live API와 온프레미스 음성 모델 기반 소통을 모두 지원하는 구현 개선계획을 요청했다. Live 모드는 상대 발화 중에도 출력 음성을 전화로 송출하며 입력을 계속 전달해야 한다. 온프레미스 STT/TTS 경로는 계속 선택 가능해야 한다. 웹·전화 공통 세션 제한, 종료, 작업 처리와 보존·조회 계약의 회귀를 방지해야 한다.

---

# 2. 결정 사항

## A. 결정 내용

두 음성 경로의 env 선택은 사용자 확정 요구다. 변수명·연결 방식·보존 형식은 연결된 계획과 ADR에서 정의하며, 사용자 후속 응답 “승인하빈다”로 계획 실행·ADR·Gate 1이 승인됐다. 실제 구현 및 통합시험 완료와는 구분한다.

## B. 결정 사유

클라우드 연속 대화 기능과 기존 온프레미스 음성 모델 운용을 함께 제공한다. 온프레미스 범위는 STT/TTS이며 작업 API 전체의 로컬화는 별도 요구가 없다.

## C. 참고자료

- [개선계획](../1_plans/VOIC-FEAT-010-plan.md)
- [설계 제안](../3_decisions/ADR-014-selectable-voice-provider.md)
- [기존 기능](VOIC-FEAT-001.md)
- [운영 준비 계획](../1_plans/VOIC-OPS-008-plan.md)
- [오케스트레이터](../../../apps/orchestrator/README.md)
- [공식 Live 문서](https://developers.openai.com/api/docs/guides/live)
