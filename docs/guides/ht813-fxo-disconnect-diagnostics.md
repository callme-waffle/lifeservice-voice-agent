# HT813 FXO 상대방 종료 감지 진단

이 절차는 외부 발신자가 먼저 전화를 끊었는데 HT813 FXO가 `In Use`를 유지하고 SIP `BYE`를 보내지 않는 경우에 사용한다. 실제 장비 설정을 변경하기 전에는 현재 설정과 복구값을 기록하고, FXO가 `Idle`인지 확인한다. 이 프로젝트의 회선에서는 전류 단절 감지 단독 시험이 실패했고, `480+620 Hz, 500/500 ms` **종료 톤 감지 단독 설정이 실제 착신 두 건에서 작동했다**. 다른 회선에 적용할 때는 제공 신호를 다시 확인한다.

## 현재 관측과 추정 범위

2026-10-09 실착신에서 발신자 종료 뒤 HT813→GPU `BYE`가 없었고 서버 RTP 소켓과 HT813 FXO `In Use`가 유지됐다. 백엔드 정상 종료 때는 GPU→HT813 `BYE`, HT813→GPU `200 OK`, FXO `Idle` 복귀가 관측됐다. 따라서 SIP 응답이나 서버의 명시적 회선 해제 경로는 작동하며, **PSTN 종료 신호를 HT813가 인식해 SIP 종료로 바꾸는 경로**가 우선 진단 대상이다. 통신사 회선이 어떤 신호를 실제로 보내는지는 이 SIP 기록만으로 알 수 없다. [실착신 기록](../records/2_logs/VOIC-FEAT-001-log-51.md).

사용자 확인에 따르면 FXO는 통신사 전화선·벽면 단자에 연결돼 있다. 시험 전에는 `Enable Current Disconnect`, `Enable PSTN Disconnect Tone Detection`, `Enable Polarity Reversal`이 모두 `No`였다. 세 종류의 대표적 종료 신호를 모두 감지하지 않는 이 기준선은 이전 점유 잔류의 유력한 설명이었으나, 회선 신호 자체의 존재 여부까지 증명하지는 못했다.

후속 전류 단절 감지 단독 시험에서는 상대방 종료 뒤에도 HT813의 BYE가 오지 않아 `Enable Current Disconnect`를 다시 `No`로 원복했다. 같은 통화의 보존된 RTP **입력**에는 처음 8초 동안 `480+620 Hz`가 약 0.5초 켜짐·0.5초 꺼짐으로 반복됐다. 이를 근거로 `Enable PSTN Disconnect Tone Detection=Yes`만 켜고 `PSTN Disconnect Tone=f1=480@-32,f2=620@-32,c=500/500;`를 유지해 두 번의 실제 통화를 시험했다. 두 통화 모두 발신자 종료 뒤 HT813가 BYE를 보내고 FXO가 Idle로 돌아왔다. 아날로그 회선의 전기 신호를 직접 측정한 결과는 아니다. [전류 단절 시험](../records/2_logs/VOIC-FEAT-001-log-53.md), [입력 신호 분석](../records/2_logs/VOIC-FEAT-001-log-54.md), [종료 톤 실착신](../records/2_logs/VOIC-FEAT-001-log-55.md).

## FXO가 종료를 감지하는 방법

|회선이 제공하는 신호|HT813 FXO 설정|확인할 점|
|---|---|---|
|짧은 회선 전류·전압 단절(CPC, power denial)|`Enable Current Disconnect`와 `Current Disconnect Threshold (ms)`|통신사가 단절을 보내는지와 그 지속 시간이 임계값보다 긴지|
|종료 뒤 들리는 통화중·종료 톤|`Enable PSTN Disconnect Tone Detection`, `PSTN Disconnect Tone`|실제 회선의 주파수·켜짐/꺼짐 주기가 설정값과 일치하는지|
|통화 상태에 따른 극성 반전|`Enable Polarity Reversal`|통신사가 해당 서비스를 제공하는지|

HT813 제조사 설명에 따르면 전류 단절 임계값은 50~800 ms, 기본값은 100 ms다. 임계값을 높이면 짧은 잡음성 전압 저하로 인한 오검출은 줄지만, 실제 단절이 더 짧으면 종료를 놓칠 수 있다. 극성 반전은 회선 제공이 확인된 경우에만 켜야 하며, 제공하지 않는 회선에서 켜면 통화가 실패할 수 있다. [HT813 관리 가이드](https://documentation.grandstream.com/knowledge-base/ht813-administration-guide/), [제조사 FXO 연동 절차](https://documentation.grandstream.com/knowledge-base/connecting-ucm6xxxx-with-ht813/).

국제전기통신연합의 **2010년** 한국 통화중 톤 표에는 `480+620 Hz`, `0.5초 켜짐/0.5초 꺼짐`이 실려 있다. 이는 HT813 문서의 기본 톤 형식 `f1=480@-32,f2=620@-32,c=500/500;`과 주파수·주기가 같다. 이 프로젝트에서는 실제 RTP 입력에서 같은 패턴을 확인하고 두 번의 착신에서 종료 감지가 작동했다. 다른 통신사·회선에서 표준값만으로 같은 결과를 보장하지 않는다. [ITU 톤 표, 16쪽](https://www.itu.int/dms_pub/itu-t/opb/sp/T-SP-E.180-2010-PDF-E.pdf), [HT813 관리 가이드](https://documentation.grandstream.com/knowledge-base/ht813-administration-guide/).

## 순차 시험 절차

1. **회선 방식 확인:** 통신사에 상대방이 먼저 끊었을 때 이 아날로그 전화선이 `CPC/전류 단절`, `통화중 톤`, `극성 반전` 중 무엇을 제공하는지 묻는다. 전류 단절이면 지속 시간, 톤이면 주파수·주기, 극성 반전이면 제공 여부를 확인한다. 회선 신호를 알 수 없으면 아래 후보를 단일 변경·즉시 원복 가능한 진단 시험으로만 취급한다.
2. **기준선 준비:** 현 FXO Termination 세 옵션과 톤값·임계값을 기록한다. 백엔드와 SIP 메시지 종류만 기록하는 관측기를 제한 시간 동안 실행하고, 시험 전 FXO `Idle`을 확인한다. 장비 Information Capture는 사용자 보고상 동작하지 않으므로 필수 조건으로 두지 않는다.
3. **전류 단절 후보:** 통신사가 CPC를 제공한다고 확인됐거나 첫 고립 시험으로 선택한 경우 `Enable Current Disconnect=Yes`, `Current Disconnect Threshold=100 ms`로 두고 **톤 검출·극성 반전은 No**로 유지한다. 휴대전화에서 착신·짧은 대화·상대방 종료를 시험한다. 정상 대화 중 오검출이 생기면 원복하고, 실제 전류 단절 제공이 확인된 경우에만 제조사 안내처럼 임계값을 100 ms씩 높여 재시험한다. 종료를 전혀 감지하지 못했다면 임계값을 무작정 높이지 않는다. [제조사 FXO 연동 절차](https://documentation.grandstream.com/knowledge-base/connecting-ucm6xxxx-with-ht813/).
4. **종료 톤 후보:** 통신사가 톤 방식을 안내하거나 실제 회선의 종료 후 톤을 확인했다면 전류 단절을 No로 원복하고 `Enable PSTN Disconnect Tone Detection=Yes`만 켠다. `PSTN Disconnect Tone` 값이 실제 회선의 주파수·주기와 맞는지 확인한다. 이 프로젝트의 회선에서는 위 값으로 두 번 성공했지만 다른 회선에서는 실측 없이 기본값만 믿지 않는다. 정상 통화가 잘못 끊기거나 종료 신호가 오지 않으면 다시 No로 원복한다. [HT813 관리 가이드](https://documentation.grandstream.com/knowledge-base/ht813-administration-guide/), [제조사 FXO 연동 절차](https://documentation.grandstream.com/knowledge-base/connecting-ucm6xxxx-with-ht813/).
5. **극성 반전 후보:** 통신사가 해당 서비스를 제공한다고 명시한 경우에만 다른 두 검출을 원복한 뒤 `Enable Polarity Reversal=Yes`를 별도 시험한다. 제공 여부가 확인되지 않으면 시도하지 않는다. [HT813 관리 가이드](https://documentation.grandstream.com/knowledge-base/ht813-administration-guide/).

각 후보에서 동일한 판정 기준을 사용한다. 발신자가 먼저 끊은 시각부터 운영상 목표인 **10초 이내**에 HT813→GPU `BYE`, GPU→HT813 `200 OK`, RTP 4002/UDP 해제, FXO `Idle`을 확인한다. 이어서 두 번째 착신이 가능한지 확인한다. 10초는 이 프로젝트의 시험 기준이며 제조사 보장 시간은 아니다. 정상 대화 중 오검출이 없는지도 확인한다. 실패하면 백엔드를 정상 종료해 GPU→HT813 `BYE`·FXO `Idle`을 확인하고 해당 설정을 원복한다. 다음 후보를 시험할 때 여러 감지 옵션을 동시에 켜지 않는다.

이번 성공 시험에서는 사용자에게 종료 10초 후 FXO `Idle`을 확인받고 두 번 모두 HT813 발신 BYE와 RTP 해제를 관측했다. 휴대전화 종료 버튼의 정확한 시각을 서버 시계와 동기화하지 않아 **10초 이내 BYE 지연 수치는 직접 계측하지 못했다**. 장시간 오검출 여부도 별도 검증 대상이다. [시험 결과](../records/2_logs/VOIC-FEAT-001-log-55.md).

## 혼동하기 쉬운 항목과 보완책

- FXS 화면의 `Loop Current Disconnect`는 HT813가 **VoIP 쪽 종료를 아날로그 전화기/PBX에 알리는 출력**이다. FXO가 통신사 회선의 상대방 종료를 알아내는 `Enable Current Disconnect`와 방향이 다르므로 이번 첫 변경 대상이 아니다. [HT813 관리 가이드](https://documentation.grandstream.com/knowledge-base/ht813-administration-guide/).
- `PSTN Ring Timeout`은 받기 전 벨이 멈췄는지 확인하는 항목이고, 연결된 통화의 상대방 종료 감지와 다르다. [HT813 관리 가이드](https://documentation.grandstream.com/knowledge-base/ht813-administration-guide/).
- 서버가 RTP 무음만으로 끊는 방식은 사용자의 긴 발화 간격도 종료로 오인할 수 있다. `Incoming Call Duration Limit` 같은 최대 통화시간은 점유 방지용 최후 안전장치일 수 있지만, 실제 상대방 종료를 감지하는 해결책은 아니다. [HT813 관리 가이드](https://documentation.grandstream.com/knowledge-base/ht813-administration-guide/).
- 어느 방법도 작동하지 않으면 통신사에 회선 종료 신호 제공 여부를 확인하고, 필요하면 아날로그 회선 측정을 의뢰한다. SIP/RTP 패킷만으로 회선 전류나 극성 반전을 직접 증명할 수 없다. [Cisco FXO 종료 진단 설명](https://www.cisco.com/c/en/us/support/docs/voice/analog-signaling-e-m-did-fxs-fxo/8120-fxo-disconnect.html).
