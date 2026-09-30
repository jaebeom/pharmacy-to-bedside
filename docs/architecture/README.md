# 구현 계약

상태: **제안된 작성 규칙**. P3 인터페이스가 모두 확정되었다는 뜻이 아니다. 계약 문서는 모두 `proposed` 다.
기준: main `f316197` = 태그 `v1.1.0`(2026-09-30). 아래 문서는 이 커밋의 코드와 대조해 고쳤다.
패키지별 구현 상태는 각 패키지 README 에 있다([src](../../src/README.md)).
메시지·서비스·액션은 [src/rokey_p3_interfaces](../../src/rokey_p3_interfaces/README.md)에 있다. 이름과 규칙은 아래 계약이 정한다.

처음 읽는 사람은 [시스템 그림](system-overview.md) → [ROS2 연동 표](ros2-integration-table.md) → [스테이지 인자·기본값](stage-arguments.md) 순서로 본다.
세 문서가 지금(v1.1.0) 실제로 띄우는 구성이다. 계약 문서는 이름·규칙의 원문이다.

| 문서 | 상태 | 범위 |
| --- | --- | --- |
| [시스템 그림](system-overview.md) | 현황 기록(v1.1.0) | PC ↔ 역할 ↔ 노드 ↔ 토픽. 병원 한 바퀴의 기본 흐름. 기본 한 PC, `P3_ROLES` 두 대. 발표 슬라이드가 같은 그림 파일을 쓴다. 계약을 바꾸지 않는다 |
| [ROS2 연동 표 (병원 시연)](ros2-integration-table.md) | 현황 기록 | `/clock`·`use_sim_time`, TF 트리, 이미지·스캔, Isaac JSON 브리지 토픽, `/events`·`/orders/status`, 액션·서비스의 발행자·구독자·주기·QoS·계약 절. 코드와 계약이 다른 곳 표. 계약을 바꾸지 않는다 |
| [스테이지 인자·기본값 (병원)](stage-arguments.md) | 현황 기록(v1.1.0) | 병원 preset 의 스테이지 인자, `tools/demo_v2.sh` 병원 기본값(카메라 집기·도크 = 적재 자리·레일 후보 순서), 주행 감속 값과 근거 회차. 계약을 바꾸지 않는다 |
| [배송 한 바퀴 v1](delivery-contract-v1.md) | proposed | 노드 배치, 토픽·서비스·액션 이름과 QoS, 프레임, 시간·epoch, 인터락, 리셋 barrier, 타임아웃, 이벤트 순서, 인터페이스 v1.1 변경 목록 |
| [배송 한 바퀴 v1 구현 현황](delivery-contract-v1-status.md) | 현황 기록 | 11절·3절 조항이 어느 PR 에 있는지, 기본인지 opt-in 인지. 계약을 바꾸지 않는다 |
| [예외 → 종료 상태 표 v1](exception-outcomes-v1.md) | 현황 기록 | 조건(PickPouch outcome·GoToZone·시한·인증·복귀·재도킹·리셋)마다 종료 상태·reason·재배차·`trip_fsm.py` 근거 줄. 계약을 바꾸지 않는다 |
| [K5 인증·전달 v0 인터페이스](k5-delivery-interface.md) | proposed | 팔이 필요로 하는 것만. 기존 `PickPouch`·`ScanTag`·`CabinetObservation` 으로 된다. 인증 출처(참값·카메라)와 결정 44(집을 칸 전달) |
| [QR·약 DB·카메라 한 장·흡착 압력 v1](qr-db-camera-contract-v1.md) | proposed | 배송 계약 v1 에 이름만 더한다(#520). `cn-`·`md-` 접두. sqlite 약 DB(orchestrator 소유). 정지 확인 뒤 한 장. `/amr_1/gripper/pressure` kPa |
| [QR 배치와 카메라 구성 (시뮬)](qr-camera-layout.md) | 현황 기록 | 봉투·약통·인식표 QR 이 붙는 곳과 크기. AMR 과 M0609 의 D455 컬러 카메라 장착값과 해상도. 판독 픽셀 계산. 계약을 바꾸지 않는다 |
| [관제 웹 서비스](web-console.md) | proposed | 웹 백엔드·프론트 구성과 띄우는 법. 계약 v1 의 GUI 소비자 자리이며 계약을 바꾸지 않는다. API 원문은 [`web/api.md`](../../web/api.md) |
| [STAT S0 승인·접수·custody v1](stat-delivery-contract-v1.md) | proposed | STAT S0 의 승인 대조·멱등 접수·물리 작업 journal·관측 대조·crash 복구. 순수 파이썬 L1, 배송 계약 v1 을 바꾸지 않는다(#299) |

결정 이력은 [ADR](../adr/README.md)에 있다. ADR 일곱은 모두 `proposed` 다. 지금 코드와 다른 ADR 은 0004(인증·집기 참값)다. v1.1.0 병원 기본은 카메라다. 그 기본은 [ADR 0007](../adr/0007-hospital-camera-qr-dock-at-load.md)이 적는다([ADR README](../adr/README.md#지금-코드와의-관계)).

트립 순서를 미는 방식은 [ADR 0001](../adr/0001-orchestrator-trip-fsm.md).
AMR 1대 v1의 노드 수 추정과 작성자·제어 소유권 점검은 [노드 구성 분석](../analysis/node-topology-v1.md)에 있다(9/17 정적 점검, 지난 기록).
9/17 시점 토픽·서비스·액션의 노드별 연결과 앞으로 정의할 운영 상태는
[통신 경로와 상태 소유권 점검](../analysis/communication-state-inventory-v1.md)에 있다(정적 구현 목록, 지난 기록). 지금 연결은 [ROS2 연동 표](ros2-integration-table.md)를 본다.

| 책임 | 구현 위치 | 경계 |
| --- | --- | --- |
| 메시지·서비스·액션 | src/rokey_p3_interfaces/ | ID·단위·필수 필드·오류 |
| 임무·인터락·재고·약 DB | src/rokey_p3_orchestrator/ | 전이·소유권·timeout·복구 |
| 팔 제어(UR5·M0609) | src/rokey_p3_manipulation/ | 좌표·허용 범위·성공 |
| AMR·Nav2·도킹·감속 | src/rokey_p3_navigation/ | namespace·취소·도킹 |
| 인식(봉투·QR) | src/rokey_p3_perception/ | 추정치·불확실성·누락 |
| 기동·Isaac 어댑터 | src/rokey_p3_bringup/ | 기동 조합·설치 config |
| 구역·경로·씬 자산 | src/rokey_p3_description/ | 버전·상대 참조 |
| 씬·리셋·센서·실험 | sim/standalone/ | Isaac 런타임·JSON 토픽 |
| 관제 웹 | web/ | ROS 를 모르는 프론트, 백엔드가 구독·명령 |
| 한 명령 기동 | tools/demo_v2.sh | 역할·기본값·기동 순서 |

패키지마다 담당 1명이 있고 공용 패키지(interfaces·bringup·config)는 orchestration 담당이 소유한다.
담당 표와 공용 파일 변경 절차는 [Git 가이드](../process/git-start-guide.md#병렬-작업에서-충돌-줄이기).

순수 상태 전이·지표 계산은 ROS/Isaac import 없이 테스트한다.
시간·랜덤·센서/제어 I/O는 경계에서 주입한다.
구체적 재사용 사례 전에 범용 플러그인 플랫폼이나 모든 로봇을 위한 추상 계층을 만들지 않는다.

## 기능 PR 전에
[계약 템플릿](../templates/contract.md)으로 작은 전체 동작에 필요한 것부터 정한다.
변경은 생산자·소비자를 함께 바꾸거나 호환 가능한 단계로 한다.

- 토픽 생산자/소비자, 타입·QoS·rate·timestamp 의미·stale 판정.
- frame 트리·단위·축·변환 소유자. clock/frame 중복 발행 금지.
- command ID와 session/reset epoch. 중복·역순·재시작 후 이전 성공 신호 처리.
- 성공/실패/취소/timeout의 유일한 종결 조건과 제한된 재시도.
- 인터락은 stale/unknown/heartbeat 소실 시 출발 거부. timeout은 진입 허가가 아니다.
- 교차로 lease, 정지 확인, 교착 해제 후 재획득. 오래된 ARM_HOME으로 출발하지 않는다.
- reset 완료 barrier 전에 새 배치 금지. sim time이 되감기면 epoch 변경.

단절된 원격 노드에 stop을 보냈다는 사실만으로 정지를 보장할 수 없다.
실행 주체의 로컬 watchdog·만료 명령 거부와 실패 테스트가 필요하다.
인터락 규칙은 [계약 v1 5절](delivery-contract-v1.md#5-인터락)에 있다.
오케스트레이터 FSM guard와 fleet·arm 수락 거부가 그 규칙을 따른다(#40, #42, #43).
노트북은 쓰지 않았다(계약 1.1). 인터락 실패 주입(heartbeat 소실 등)을 Isaac 에서 돌린 기록은 찾지 못했다(미확인).
