# Model serving component

STT와 TTS는 같은 코드 계약을 쓰지만 각각 별도 컨테이너·프로세스로 실행한다. `MODEL_KIND=stt|tts`가 모델 종류를 정한다. 시작 시 모델을 한 번 로드하며 TTS는 첫 합성까지 수행한 다음 `/ready`를 200으로 전환한다. STT `POST /infer`는 16 kHz mono PCM16 원시 바이트를 받아 `{"text":"..."}`를 반환하고, 인식된 음성이 없으면 422를 반환한다. TTS `POST /infer`는 `{"text":"..."}`를 받아 같은 형식의 원시 PCM 바이트를 반환한다. 추론 API는 GPU VM의 `127.0.0.1`에만 바인딩하고 지표 포트는 관리망 주소에 바인딩한다.

GPU VM의 GTX 1080 Ti에서 Python 3.11, faster-whisper 1.2.1, CTranslate2 4.4.0, MeloTTS 0.1.2, Torch 2.3.1+cu121 이미지를 빌드·기동했다. CTranslate2 공유 라이브러리의 실행 가능 스택 플래그는 이미지 빌드 때 제거한다. 두 모델은 동시에 `/ready`를 유지했고, 모델 출력 음성/전사는 일반 로그나 추적에 기록하지 않는다. 2026-10-07 합성 문장의 TTS 첫 추론은 워밍업 전 60.262초, 반복 추론은 0.401초였고, 준비 전 워밍업을 추가한 뒤 첫 API 요청은 0.327초였다. GPU VM RAM이 약 3.8 GiB여서 실제 통화 부하와 장시간 swap 안정성은 계속 검증해야 한다.

로컬 개발: `PYTHONPATH=apps/model-serving/src:apps/orchestrator/src MODEL_KIND=stt uvicorn voice_models.server:app --port 8101`. 필요한 모델 런타임과 CUDA 환경은 해당 개발 호스트에서 별도로 준비한다. 단위 시험은 `pytest -c apps/model-serving/pyproject.toml tests/units/model-serving/testcodes/server.test.py`로 실행한다.
