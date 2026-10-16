# 0. 로그 정보

|key|value|
|---|---|
|로그 ID|VOIC-OPS-008-log-08|
|원본 이슈|[VOIC-OPS-008](../0_issues/VOIC-OPS-008.md)|
|실행 계획|[VOIC-OPS-008-plan](../1_plans/VOIC-OPS-008-plan.md)|
|기록 시간|2026-10-16 23:57 KST — 로컬 구현·검증 결과|
|세션 ID|20261016-service-readiness-m10|
|기록 에이전트|Codex|

---

# 1. 실행 요약

관리 정정에 따라 준비용 MR #4의 선행 병합 없이 M10 구현·검증을 계속했다. 통화 종료 중 앱 close가 정리를 기다리지 않거나 정리 task를 취소하는 BUG-009를 재현·수정했다. 단위와 승인된 로컬 통합 경계를 실행했으며 실제 환경 기동·실전화는 아직 하지 않았다. MR #4는 draft WIP이고 M10 완료/최종 인수 요청이 아니다.

2026-10-16 23:30:40 KST 수신한 사용자 응답 `call_6195b9fe0f6c4b9f8f705a9cbad2251c`의 범위는 다음과 같다.

- 로컬 격리 조회·보존·loopback SIP/RTP 및 종료/취소·다음 전화 수락 시험 생성·실행, 같은 범위의 실패 수정·재검증 승인.
- 기존 원격 대화 암호문 1건(1 MiB 미만)의 인증된 SSH 이동/메모리 복호화·무결성·형식 검증 승인. 원문·키 저장/출력 없음.
- 현재 FXS 불가에 따른 D02 생략 승인. 물리 회선과 SIP/FXO의 독립 원인 분리 한계는 남는다. 실제 발신 승인과 별개다.

---

# 2. 수행 내용

## 대상 마일스톤: M10. 실제 전화·조회 사용 흐름 완결

### M10-S1. 종료·회수 구현과 시험 도구

- BUG-009: 공통 `_terminate` 완료 Future를 추적하고 close가 정리 소유 task를 취소하지 않도록 했다. BYE/CANCEL, 미디어 실패, ACK 응답 송신 실패, 대화 종료, 패킷 dispatch 오류의 경쟁을 Event로 재현했다. 종료 중 보존·미디어·gate 정리를 기다린다.
- 처리/재생 각각에서 착신 BYE·발신 BYE·발신 운영 취소의 6개 loopback 경계를 검증했다. 정리 후 같은 서비스/포트에서 새 전화가 연결되고 이전/다음 대화가 분리되는지 확인했다.
- `m10_probe.py`: 보호 설정/상태, loopback 인증, 승인/사례 단일 소비, POST 재시도 금지, 15초 벨 확인 watchdog, 점유 상한, 취소, 신규 착신 ID 연결, 실제 대화 조회용 metadata 출력을 구현했다. HTTP202/active가 실제 벨이나 회수 성공을 대신하지 않는다.
- `m10_web_probe.py`: 기존 wsproto 의존성으로 인증 웹 hold/busy를 제공한다. 실제 starting/listening 이벤트 후 점유 확인을 출력하고 음성 없이 cancel/close한다. 60초 상한이며 close 프레임 경합을 수정하고14 PASS를 확인했다.
- `compose.m10.yaml`: 기존 모델 Compose에 backend만 추가하는 일시 overlay. restart=no, loopback 단일 worker, 30분 창, 읽기 전용 관측 코드와 별도 보호 runtime mount. 합성 설정으로 병합 검증했으며 서비스 기동은 0이다.
- 관측 wrapper의 독립 검토에서 출력 I/O/오류가 통화에 전파되는 문제, 종료 실패 판정, 다른 SIP Call-ID의 상관관계, 송출 시도/완료 혼동을 발견했다. bounded queue/daemon writer·evidence_lost 판정, lifespan 종료 결과 확인, Call-ID 매칭, 송출 attempted/completed/cancelled/failed 구분으로 수정하고 최종18 PASS를 확인했다. 종료 중 dialog 제거 후 SIP는 unmatched일 수 있어 같은 창의 종료 이벤트·시각으로 함께 대조한다. chunk 시작/완료는 실제 첫 청취시각이나 RTP 패킷 수가 아니다.
- 종료조건 충족 여부: 앱 종료 경쟁 및 합성 경계 확인. 실제 음성·DTMF·종료 버튼→FXO Idle 수치는 미검증.
- 스캐폴드/더미 사용 여부: 제품 변경은 실제 구현이다. 자동 시험의 fake 모델·SIP 피어·합성 데이터는 격리 검증용이며 실전화 성공으로 계산하지 않는다.
- 관련 커밋: `45556d0`(BUG-009), `3f80f06`(검증·제어).

### M10-S2. 조회·보존 경계와 동일 키 확인

- 기존 조회 시험을 확장해 두 전화 세션의 정확 ID/턴 격리, 시작-only incomplete, CANCEL 후 ended·무발화 대화404, 실제 합성 암호문 손상→목록/대화503을 검증했다. 다른 세션 손상도 전체 스캔 실패가 되는 현재 계약을 보존했다.
- 기존 보존 통합시험 5개를 실행했다. 기존 운영 파일 손상·삭제 주입은 하지 않았다.
- 명시 승인 후 기존 암호문 1건을 읽는 첫 시도는 파일 소유권으로 전송이 실패했다. 키 불일치가 아니었다. 원격 파일은 0600이며 기존 SSH 계정과 소유자가 달랐다. 권한 변경 없이 기존 sudo 관리 권한으로 동일 선택 파일 1건만 메모리로 읽었다.
- 최종 결과: sample_count=1, ssh_ok=true, size_valid=true, magic_valid=true, authenticated=true, json_dict_valid=true, plaintext_persisted=false. 원문·키·원파일명·실제 번호는 로그에 남기지 않았다. 기존 정본 키로 1건을 인증했다는 증거이며 전체 파일 복구/백업 검증이 아니다.
- 종료조건 충족 여부: 합성 조회와 동일 키 1건 확인. 실제 발착신 ID→내역 및 청취/문맥 일치는 미검증.
- 스캐폴드/더미 사용 여부: 조회 파일은 실제 암호화·HTTP 경계이며 입력만 합성이다.

---

# 3. 검증 결과

## A. 실행한 검증

명령의 기준 환경은 `/tmp/voice-agent-m10-venv/bin/python`, Python 3.12다. 개별 실행의 정확 명령·시각·사례별 결과는 아래 TRY 로그에 기록했다. 기존 M4 venv의 수집 실패는 log-07과 TRY1에 보존했다.

|경계|관측 결과|증거|
|---|---|---|
|orchestrator 단위|수정 후 전체 126 PASS|[M010-TRY12](../../../tests/units/orchestrator/logs/M010-TRY12.md), 재현/수정 과정 TRY3~11|
|model-serving 단위|3 PASS, 제품 변경 없음|[M010-TRY2](../../../tests/units/model-serving/logs/M010-TRY2.md)|
|전화 조회 통합|5 PASS|[TRY1](../../../tests/integrations/call_history/logs/M010-TRY1.md)|
|보존 통합|5 PASS|[TRY1](../../../tests/integrations/retention/logs/M010-TRY1.md)|
|SIP/RTP 수명 통합|기존2+신규6 = 8 PASS|[TRY3](../../../tests/integrations/ht813/logs/M010-TRY3.md)|
|제어 probe|보강 후 36 PASS, 최종 logging 복원 영향 1 PASS|[TRY7](../../../tests/integrations/ht813/logs/M010-TRY7.md), [TRY8](../../../tests/integrations/ht813/logs/M010-TRY8.md)|
|관측 wrapper|독립 검토 수정 후 18 PASS|[TRY12](../../../tests/integrations/ht813/logs/M010-TRY12.md)|
|F04 웹 제어|최종 14 PASS|[TRY15](../../../tests/integrations/ht813/logs/M010-TRY15.md)|
|Compose overlay|합성 env config 병합 성공, backend mount3, 기동0|로컬 `docker compose ... config --format json` 결과를 메모리에서 검사|
|기존 암호문 1건|인증·JSON dict 검증 PASS|위 metadata 결과; 실제 원문/키 출력0|

초기 수명 시험의 수집 오류(루트 PYTHONPATH 누락)와 2실패(시험의 calls/items 오타), 관측 시험의 2실패(필수 합성 모델 설정 누락)는 해당 TRY 로그에 남겼다. 통과 수에 실패/수집 오류를 섞지 않는다. BUG-009 재현 FAIL은 제품 결함 증거이며 위 시험 작성 오류와 구분한다.

## B. 결과 판정

로컬 경계가 통과해도 실제 벨·양방향 청취·문맥 이해·DTMF·FXO Idle·실제 Caller ID가 확인된 것은 아니다. probe의 DELETE202는 요청 수락이며 회수 완료가 아니다. 최종 취소 뒤 실제 다음 전화 수락은 별도 실전화 표본이 필요하다. 7회 예산 소진만으로 M10 완료를 선언하지 않는다.

---

# 4. 계획 대비 이탈 사항

- 관리 인계의 준비 MR 선행 병합 요구를 철회한 사용자 정정을 현재 계획/STATUS에 반영했다. 단계 완료 MR의 사용자 병합과 agent merge 금지는 유지한다.
- 새 조회 파일을 중복 생성하는 대신 기존 두 파일을 확장했다. 수명 파일명은 실제 `test_call_lifecycle.py`로 동기화했다. 승인된 검증 의미/범위를 바꾸지 않았다.
- BUG-009는 승인된 M10 종료·회수 범위의 결함 수정이다. 서비스/저장/전화 정책 변경이나 새 마일스톤이 아니다.
- D02 생략은 이번 명시 응답으로만 승인했다. BUG-003 원인 해소/종결 또는 미확정 시험의 포괄 예외로 확장하지 않았다.

---

# 5. 미해결 사항 / 후속 작업

|항목|현재 판정 / 필요한 다음 행동|
|---|---|
|관측·웹 점유 도구|관측 최종18 PASS. 웹 점유14 PASS, 고정 후보에 포함|
|P0-A|고정 후보/이미지, 보호 사본·manifest, 현 장비 설정/Caller ID 헤더·FXO Idle·포트·시계 확인|
|현 장비 읽기|23:53:58 KST SSH 확인: backend 부재, STT/TTS ready, 기존 이미지 ID 유지, 후보 API/SIP/RTP/metrics 포트 미점유, Compose5.6.0. 사용자 설정 유지 확인. FXO Idle/Caller ID 값 확인 남음|
|실환경 Gate 2|backend-only 일시 기동, 기존 비밀의 보호 tmpfs 주입·동일 데이터 마운트·원복·통화 예산을 제시해 명시 응답 필요|
|P0-B/F01|기동 후 ready·인증·발신 거부/INVITE0·타이머 확인|
|F02/F03/H01|각 실발신 직전 응답, 실제 발착신 2턴/문맥/청취/DTMF/내역/종료 지연|
|F04/F05/P/C|점유 충돌·표시 변형 가능 여부·처리/재생 중 종료·운영 취소·다음 전화 수락|
|BUG-003|열림. FXS 독립 진단 불가이며 반복 실전화와 남은 원인 위험 판정 필요|
|부모 보고|실제 코드/검증을 MR4 WIP에 누적한다. 준비 문서 완료나 M10 완료로 보고하지 않는다. M11 실행0|

---

# 6. 참고자료

- [승인·기동 순서·종료조건](../1_plans/VOIC-OPS-008-plan.md#a9-실행-묶음-승인-기록)
- [BUG-009](../0_issues/VOIC-BUG-009.md)
- [이전 재개 기록](VOIC-OPS-008-log-07.md)
- [진행 중 MR4](https://github.com/callme-waffle/lifeservice-voice-agent/pull/4)
