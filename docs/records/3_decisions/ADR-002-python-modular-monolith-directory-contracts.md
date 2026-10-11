# 0. 결정 정보

|key|value
|---|---
|ADR ID|ADR-002-python-modular-monolith-directory-contracts
|상태|superseded
|결정 시간|2026-09-22 16:55:03
|결정자|사용자
|기록 에이전트|Codex
|관련 이슈|[VOIC-FEAT-001](../0_issues/VOIC-FEAT-001.md)
|관련 계획|[VOIC-FEAT-001-plan](../1_plans/VOIC-FEAT-001-plan.md)
|대체 대상|(없음)
|대체 문서|[ADR-004](ADR-004-ht813-direct-outbound-telephony.md) (2026-09-24 사용자 승인; 모듈 경계 결정은 ADR-004에 계승)

---


# 1. 배경 및 맥락

FastAPI 메인 코어, STT/TTS 연결부, 작업 처리부, 웹 채널 및 Asterisk 채널을 여러 작업 단위로 나누어 병렬 개발하려면 구현 전에 디렉터리 소유권과 의존 방향이 고정되어야 한다. 그렇지 않으면 각 모듈이 서로의 구체 구현을 직접 참조하거나, 서로 다른 오디오·세션 규약을 만들어 통합 단계에서 충돌할 가능성이 크다.

사용자는 계획 승인 후 첫 구현 마일스톤에 들어가기 전에 애플리케이션 디렉터리 구조를 결정하고, 모듈별 연계 규칙을 구현보다 먼저 확정하도록 요구했다.

---


# 2. 검토한 대안

## A. 기능별 독립 애플리케이션

- 장점: STT, TTS, 코어 및 채널을 독립 배포하고 개별 확장하기 쉽다.
- 단점: 단일 GTX 1080 Ti 환경에서 프로세스 간 통신과 GPU 자원 조정이 복잡하고 초기 운영 비용이 크다.

## B. 단일 Python 패키지의 계층 없는 구조

- 장점: 초기 파일 수가 적고 빠르게 시작할 수 있다.
- 단점: 코어, 모델, 채널 간 의존 방향이 불명확해지고 병렬 개발 시 파일 소유권 충돌과 순환 참조가 발생하기 쉽다.

## C. 단일 FastAPI 컴포넌트 안의 모듈형 모놀리스

- 장점: 하나의 로컬 프로세스에서 GPU 자원을 조정하면서도 코어·계약·어댑터·채널 경계를 분리할 수 있다. 디렉터리 단위로 병렬 개발 소유권을 나누기 쉽다.
- 단점: 모듈 경계를 정적 검사와 테스트로 지키지 않으면 시간이 지나며 계층 간 결합이 다시 증가할 수 있다.

---


# 3. 결정 내용

다음 디렉터리 아키텍처를 채택한다.

    apps/
    └── orchestrator/
        ├── README.md
        ├── pyproject.toml
        └── src/
            └── voice_agent/
                ├── __init__.py
                ├── main.py
                ├── bootstrap.py
                ├── config.py
                ├── api/
                │   ├── app.py
                │   └── health.py
                ├── contracts/
                │   ├── audio.py
                │   ├── events.py
                │   ├── errors.py
                │   ├── session.py
                │   ├── stt.py
                │   ├── task.py
                │   └── tts.py
                ├── core/
                │   ├── orchestrator.py
                │   └── session_manager.py
                ├── adapters/
                │   ├── stt/
                │   ├── task/
                │   └── tts/
                ├── channels/
                │   ├── web/
                │   └── asterisk/
                └── infrastructure/
                    ├── audio.py
                    ├── gpu.py
                    └── telemetry.py

    tests/
    ├── units/
    │   └── orchestrator/
    │       ├── testcodes/
    │       │   └── (apps/orchestrator/src/voice_agent 구조를 반영)
    │       └── logs/
    └── integrations/
        ├── voice_pipeline/
        ├── web_voice/
        └── asterisk_voice/

    deploy/
    └── orchestrator/

모듈 연계 규칙은 다음과 같다.

1. contracts는 오디오, 세션, 이벤트, 오류, STT, 작업 처리, TTS의 타입과 비동기 인터페이스만 소유하며 구체 구현에 의존하지 않는다.
2. core는 contracts에만 의존하고 adapters 또는 channels의 구체 클래스를 직접 import하지 않는다.
3. adapters는 외부 모델·작업 엔진을 contracts 규약으로 변환하며 core 내부 구현을 import하지 않는다.
4. channels는 웹 또는 Asterisk의 입출력을 contracts 규약으로 변환하며 모델 구현을 직접 호출하지 않는다.
5. bootstrap만 구체 어댑터와 채널을 조립하고 수명 주기를 연결할 수 있다.
6. 모든 스트리밍 메시지는 session_id, 순서 정보, 오디오 형식, 취소 및 오류 의미를 보존한다.
7. 오디오 리샘플링과 채널별 코덱 변환은 infrastructure/audio와 각 채널 어댑터의 책임이며 core는 채널 코덱을 알지 않는다.
8. 비동기 큐는 크기가 제한되어야 하고 역압, 시간 제한, 취소 전파 및 자원 정리 규칙을 계약 테스트로 검증한다.
9. 모듈 구현과 대응 단위 테스트는 동일 Slice 안에서 병렬 작성하며, 테스트 파일은 원본 모듈 구조를 반영한다.
10. pytest와 pytest-asyncio를 단위 테스트 기준으로 사용하고, pyproject.toml에서 *.test.py 수집 규칙을 명시한다.

---


# 4. 결정 사유

이 구조는 ADR-001의 FastAPI 기반 확장형 코어 결정을 구체화한다. 단일 프로세스의 단순성과 GPU 자원 통제 능력을 유지하면서도, 계약을 기준으로 모듈 소유권을 분리하여 사용자가 요구한 병렬 개발과 병렬 테스트를 지원한다.

구체 모델이나 Asterisk 프로토콜은 어댑터 내부에서 결정되므로, 모델 검증 결과가 달라져도 코어와 채널 구조를 다시 설계할 필요가 없다.

---


# 5. 결과 및 영향

## A. 쉬워지는 것

- 모듈별 작업 범위와 파일 소유권을 명확하게 나눌 수 있다.
- 계약 확정 이후 코어, STT, TTS, 작업 처리, 웹, Asterisk 모듈을 병렬 개발할 수 있다.
- 모델 및 채널 구현을 교체해도 코어 오케스트레이션을 유지할 수 있다.
- 단위 테스트가 소스 디렉터리 구조와 직접 대응한다.

## B. 어려워지거나 제약되는 것

- bootstrap을 제외한 계층 간 직접 참조를 지속적으로 감시해야 한다.
- 스트리밍·취소·오류·역압 규약을 구현 전에 상세히 정의해야 한다.
- 독립 서비스 수준의 개별 확장은 초기 구조에서 제공하지 않는다.
- 하나의 애플리케이션 장애가 모든 채널에 영향을 줄 수 있다.

---


# 6. 재검토 조건

- STT/TTS 또는 작업 엔진을 별도 장비에서 독립 확장해야 하는 경우
- 단일 프로세스가 목표 동시 세션 수나 지연 시간을 충족하지 못하는 경우
- Asterisk 연동에 별도의 런타임이나 언어가 필수인 경우
- 서로 다른 배포 주기 또는 장애 격리가 필요한 운영 요구가 확정되는 경우

---


# 7. 참고자료

- [VOIC-FEAT-001](../0_issues/VOIC-FEAT-001.md)
- [VOIC-FEAT-001-plan](../1_plans/VOIC-FEAT-001-plan.md)
- [ADR-001: Python/FastAPI 기반 확장형 음성 에이전트 코어](ADR-001-python-fastapi-extensible-core.md)
