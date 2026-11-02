# 0. 로그 정보

|key|value|
|---|---|
|로그 ID|VOIC-FEAT-010-log-05|
|원본 이슈|[VOIC-FEAT-010](../0_issues/VOIC-FEAT-010.md)|
|실행 계획|[승인 계획](../1_plans/VOIC-FEAT-010-plan.md)|
|기록 시간|2026-11-02T01:14:13.202422+00:00|
|세션 ID|20261031-voice-provider-planning|
|기록 에이전트|Codex|

# 1. 실행 요약

사용자의 “테스트를 진행 후, PR을 업데이트하세요” 지시로 M15 검증을 재개했다. PR #5 기준 c3c2740에서 단위 152건, 로컬 통합 고유 14건 통과. 실제 Live 발신 1회는 사용자 정상 대화·직접 종료 확인과 서버 ended 상태가 일치했다. 실제 업무 API는 HTTP 403으로 실패했다. 전체 인수 완료가 아니며 Draft를 유지한다.

# 2. 수행 내용

## 대상 마일스톤: M15-S2. 승인된 통합 검증과 인수

- 실제 주 작업 폴더가 work/VOIC-FEAT-012로 변경되어 /tmp/voice-provider-acceptance에 codex/voice-providers worktree를 생성했다. 대시보드 변경은 수정·커밋하지 않았다.
- 기존 단위·로컬 통합·localhost SIP/RTP를 재실행했다. 추가 로컬 WebSocket 장애 4종은 모의 서버를 사용하며 실제 OpenAI 장애 재현과 구분한다.
- 사용자의 “지금 가능합니다” 응답으로 기존 허용 대상 1개에 정확히 1회 발신했다. 승인된 기존 이미지, SSH 터널, 120초 관측 상한, 재발신 없음. 사용자는 “정상적으로 통화 완료했고, 제가 끊었습니다”라고 확인했다.
- 시험 컨테이너를 중지·삭제하고 전화 UDP 포트 반환을 확인했다. 기존 모델 컨테이너는 계속 healthy다. 암호화 기록은 별도 voice-live-outbound-test-data 볼륨에 남으며 지속 만료 작업 연결은 후속이다.
- 업무 API 합성 문맥 요청 1회 실패 후 HTTP 분류 진단 1회만 추가했다. 키·전화번호·전사·응답 본문은 기록하지 않았다.
- 종료조건: 부분 충족. 전체 실제 인수·업무 위임·반복 성능·장시간 시험은 미완료.

# 3. 검증 결과

## A. 실행한 검증

공통 명령 접두사: `PYTHONPATH=apps/orchestrator/src /tmp/voice-provider-venv/bin/python -m pytest -c apps/orchestrator/pyproject.toml`.

|대상|결과|
|tests/units/orchestrator/testcodes|152 passed, 8.82초|
|tests/integrations/voice_provider/test_local_live.py 기존 2건 + call_history/test_call_conversation.py + retention/test_retention_file_boundary.py|8 passed, 7.22초|
|tests/integrations/ht813/test_loopback_sip_rtp.py|2 passed, 1.58초|
|test_local_live.py 추가 장애 4종 포함 첫 실행|5 passed / 1 failed, 2.83초|
|동일 파일 재실행|6 passed, 2.28초|

첫 실패는 단절 시 Python 예외 재전파를 요구한 시험 가정 때문이었다. runner가 실패 토큰을 취소하면 상위 cancellation 경로가 먼저 끝날 수 있다. 사용자 계약은 공개 오류·자원 회수·다음 세션 수락이므로 이를 모두 명시적으로 검증하도록 수정했다. 앱 구현이나 합격 기준은 변경하지 않았다. 인증 401·한도 429·접속 시간초과·단절에서 공개 오류, 자동 재시도 없음, 슬롯 회수, 두 번째 세션 성공, 암호화 파일 및 worker 정리를 확인했다.

단위별 결과는 [M015_S002-TRY1](../../../tests/units/orchestrator/logs/M015_S002-TRY1.md)에 기록했다. audioop 및 Starlette/httpx 사용 중단 예정 경고는 남아 있다.

## B. 실제 발신

|항목|관측|
|발신 횟수|1, 재발신 없음|
|dialing|요청 후 0.044초|
|active|요청 후 7.225초|
|ended|요청 후 74.174초|
|사용자 확인|정상 대화, 사용자 직접 종료|
|같은 세션 조회|segments 128건, legacy turns 0건|
|입력 음성|66.7199375초|
|생성 음성 / 실제 송신 음성|63.80초 / 63.72초|
|출력 큐→송신 완료 지표|3,186 표본, 합계 161.517초, 평균 약 50.696ms|
|히스토그램 구간|≤20ms 475개, ≤50ms 1553개, ≤100ms 3030개, ≤200ms 3186개|

히스토그램으로 판정 가능한 p50 구간은 (50,100]ms, p95 구간은 (50,100]ms다. 정확한 분위수나 발화 종료→유효 답변 지연은 아니다. 출력 지연 200ms 기준은 이 1회 표본에서 충족했지만 I08의 제공자별 10회 비교를 대체하지 않는다. 사용자 종료 버튼 시각·FXO Idle 관측이 없어 종료 지연 목표를 합격시키지 않는다. 최종 API 사용량 확인을 확보하지 못했으며 읽은 usage gauge 0을 무과금으로 해석하지 않는다.

## C. 실제 업무 API

기존 `tests/integrations/task/test_real_context_api.py`의 합성 같은 통화 문맥 시험을 현재 주입 환경으로 실행: TaskBackendError. 별도 진단 1회: HTTP 403, `task backend authentication failed`, 0.110초. 사용자에게 업무 API 키·API/모델 접근 정책 확인을 요청했다. 인증 오류 문자열은 앱의 정제된 분류이며 공급자 내부 원인은 확정하지 않는다. 업무 성공·Live 위임 인수로 표시하지 않는다.

## D. 인수 항목별 상태

I는 단위가 아니라 계획의 Integration(통합시험) 식별자다.

|ID|사용자 관점 항목|현재 판정|
|I01|온프레미스 웹·착신·발신|단위 및 localhost 전화 회귀 통과, 실제 회선 전체 재검증 미완료|
|I02|Live 웹 동시 입출력·취소|localhost 웹→모의 Live→저장 경계 통과; 실제 API 웹 전체 인수는 부분|
|I03|Live 착신·발신|착신 과거 대화 확인, 이번 발신 정상 대화·종료 확인. 겹말 3회 정량·정정·에코 전체 기준 미완료|
|I04|업무 API 위임|실제 업무 API HTTP 403으로 차단. 모의 위임 통과가 실제 성공을 대체하지 않음|
|I05|장애·회수·재수락|로컬 WebSocket 4종 장애 통과. 실장 전체 장애 매트릭스 미완료|
|I06|암호화·조회·만료|로컬 경계 통과, 실제 발신 segments 조회. 원격 시험 볼륨의 지속 삭제 연결 미완료|
|I07|제공자 전환·원복|기존 구성·기동 검증 증거 유지. 실제 양방향 전환 인수 미완료|
|I08|지연·연속성·사용량|이번 발신 출력 지연 히스토그램 확보. 양 제공자 10회·장시간·최종 사용량 미완료|

# 4. 계획 대비 이탈 사항

사용자 테스트 지시를 이번 실행 승인으로 적용했다. 발신은 별도 시점 확인 후 1회만 수행했다. 반복 10회·최대 10분 Live 시험은 구체 상한 질문에 응답이 없어 실행하지 않았다. 새로운 실장 소스 전송은 하지 않았다.

# 5. 미해결 사항 / 후속 작업

- 업무 API 403 해결 후 실제 위임 및 정정 문맥 검증.
- 반복·장시간 API 시험 상한 응답 후 수행. 전화 추가 발신은 매회 별도 확인.
- 이전 착신 종료 불일치 VOIC-BUG-011은 이번 발신 성공만으로 종결하지 않음.
- 실제 겹말 정량·온프레미스 실회선·환경 전환 원복·사용량 수집 및 원격 보존 삭제 연결.

# 6. 참고자료

- [이전 실제 API·착신 결과](VOIC-FEAT-010-log-04.md)
- [운영 가이드](../../guides/voice-provider-operation.md)
- [PR #5](https://github.com/callme-waffle/lifeservice-voice-agent/pull/5)

## 설정 갱신 후 재확인 — 2026-11-02T10:27:28.913380+09:00

사용자가 “기록 완료”로 설정 갱신을 알렸다. 현재 환경을 다시 읽어 합성 정정 문맥 요청 1회를 준비했으나 어댑터 생성 단계에서 중단됐다. HTTPS 및 /v1 경로는 유효하지만 VOICE_AGENT_TASK_API_BASE_URL의 hostname과 VOICE_AGENT_TASK_APPROVED_HOST가 다르다. 외부 HTTP 요청은 0회이며 키 유효성·403 해소 여부는 판정하지 않았다. 승인 호스트를 임의 변경하지 않고 의도한 업무 API 서버에 맞춰 두 설정을 일치시키도록 안내했다.
