# rokey_p3_interfaces

v1.1.0 병원 한 바퀴의 ROS 노드는 모두 이 패키지의 msg 16·srv 3·action 5 로 말한다. 한 바퀴는 `Deliver` 요청 하나에서 시작한다.
그 안에서 `GoToZone`·`PickPouch`·`ScanTag`·`Refill` 액션과 `Dispense`·`CheckContainer` 서비스가 오간다. 회차 사이 리셋은 `Reset` 이다. 진행은 `/events`(`Event`)에 남는다.
CODEOWNERS 는 `@jaebeom`(임재범)이다. 필드 변경은 보호 경로 검토를 거친다.

P3 메시지·서비스·액션이다. [시나리오 7절](../../docs/planning/scenario.md#7-이-시나리오가-요구하는-계약-항목)의
후보 이름을 파일로 옮겼고, 이름과 규칙은 [계약 v1](../../docs/architecture/delivery-contract-v1.md)이 정한다.
**계약 문서의 상태는 아직 `proposed` 다**(계약 머리). 스텁 한 바퀴는 `v0.2.0` 부터 이 이름들로 돌고, CI 의 L2(`rokey_p3_bringup` 테스트)가 PR 마다 다시 돌린다.
accepted 로 바꾸는 것은 팀 결정이다.
지금 파일 버전은 **v1.1** 이고 v1 과의 차이는 [계약 10절](../../docs/architecture/delivery-contract-v1.md#10-인터페이스-v11-변경-목록)에 있다.

이 패키지는 **orchestration 담당이 소유**한다. 필드를 바꾸려면
[Git 가이드의 공용 파일 절차](../../docs/process/git-start-guide.md#공용-파일을-바꿔야-할-때)를 따른다.
바꾼 메시지를 쓰는 생산자·소비자를 같은 PR에서 고친다.
새 관측 타입(계약 11.6)의 상태 enum 은 모두 0 = UNKNOWN 이다. 기본값으로 만든 메시지는 "모름"이다.
이름 추가는 호환이고 이름 변경·삭제는 v2 다([계약 9절](../../docs/architecture/delivery-contract-v1.md#9-변경롤백)).

인터페이스 파일 안의 주석은 영어다. `rosidl` 이 `.idl` 을 ISO-8859-1 로 쓰기 때문에 한글 주석은 빌드를 깨뜨릴 수 있다.
설명은 이 README 와 시나리오 문서에 한글로 둔다.

## 목록

| 파일 | 무엇 | 만드는 쪽 → 쓰는 쪽 |
| --- | --- | --- |
| `msg/Order.msg` | 주문 = 봉투 1개 | 발행기 → 오케스트레이터 |
| `msg/DeliveryRequest.msg` | 배송 요청. `mode` 상수 4개 | 발행기 → 오케스트레이터 |
| `msg/OrderStatus.msg` | 주문 상태. 주장 `STATE_DELIVERED` 와 종료 상태 4개 | 오케스트레이터 → 메트릭·GUI |
| `msg/Event.msg` | 실행 이벤트 한 줄. 이름 상수 26개(`RESET_BEGIN` 포함, #76) | 모든 노드 → 메트릭 |
| `msg/BeltState.msg` | 벨트 점유·끝 정지·봉투 주문 ID | isaac → 오케스트레이터·manipulation |
| `msg/CabinetObservation.msg` | 평가 전용 보관함 관측 | isaac → `event_logger` **만** |
| `msg/DispenserSlot.msg`, `msg/DispenserStatus.msg` | 조제기 슬롯·상태(`/pharmacy/dispenser/status`) | 오케스트레이터(재고 모듈) → `status_monitor`·관제 웹 |
| `msg/TagRead.msg` | QR 판독 결과. `kind` 는 환자·스테이션·봉투·약통(`cn-`)·모듈(`md-`) 다섯 | perception → manipulation·오케스트레이터 |
| `msg/PouchDetection.msg`, `msg/PouchDetectionArray.msg` | 봉투 검출 + QR | perception → manipulation |
| `msg/BeltObservation.msg` | 벨트 관측(점유·봉투 운동·적용된 구동 명령, epoch·seq·mode). `/pharmacy/belt` 와 병행 | isaac → 오케스트레이터·manipulation |
| `msg/GripperState.msg`, `msg/GripperCommand.msg` | 흡착 관측(HELD/RELEASED, VIRTUAL/PHYSICAL, 적용한 명령 seq)과 seq 붙은 흡착 명령. `gripper/holding`·`gripper/command` 와 병행 | isaac ↔ manipulation |
| `msg/ArmClearance.msg` | 팔·도구·파지물이 통로 밖인가(CLEAR/INTRUDING) | manipulation → 오케스트레이터 |
| `msg/DockingState.msg` | 도킹 공차 안인가. `base/stopped` 와 별개 | navigation → 오케스트레이터·manipulation |
| `srv/Dispense.srv` | 봉투 1개 배출 | 오케스트레이터 → 조제기 |
| `srv/Reset.srv` | 실행 사이 리셋 | 오케스트레이터 → sim |
| `srv/CheckContainer.srv` | 보충 전 약통 QR 로 장착 여부 묻기(QR·DB·카메라 계약 2.3) | m0609/arm → 오케스트레이터 |
| `action/Deliver.action` | 요청 하나를 끝까지 | 발행기·GUI → 오케스트레이터 |
| `action/PickPouch.action` | 봉투 픽·플레이스 | 오케스트레이터 → manipulation |
| `action/ScanTag.action` | 인식표 QR 스캔 | 오케스트레이터 → manipulation |
| `action/Refill.action` | 캐니스터 장착 | 오케스트레이터 → manipulation |
| `action/GoToZone.action` | 구역으로 이동 | 오케스트레이터 → navigation |

## 이 이름들을 정하는 곳

아래 셋은 [계약 v1](../../docs/architecture/delivery-contract-v1.md)이 정한다(상태 proposed).

- QR 내용 형식 — [계약 7절](../../docs/architecture/delivery-contract-v1.md#7-id타임아웃재시도).
  `ord-`, `pt-`, `st-` 접두로 `TagRead.kind` 를 정한다. 약통 `cn-`·모듈 `md-` 는 [QR·DB·카메라 계약](../../docs/architecture/qr-db-camera-contract-v1.md)이 더했다.
- 좌표 프레임 이름과 시간 기준 — [계약 3절](../../docs/architecture/delivery-contract-v1.md#3-프레임과-단위),
  [계약 4절](../../docs/architecture/delivery-contract-v1.md#4-시간epochstale).
- 토픽 이름과 QoS — [계약 2절](../../docs/architecture/delivery-contract-v1.md#2-토픽서비스액션).
  이름 규칙은 [naming.md](../../docs/process/naming.md).

## 주장과 판정은 다른 단어다

`OrderStatus.STATE_DELIVERED` 와 `Deliver` 결과의 `success` 는 오케스트레이터의 **주장**이다.
`STATE_SUCCESS` 는 평가기가 봉투를 보관함 안에서 본 경우에만 `event_logger` 가 run 기록에 쓴다.
오케스트레이터는 `STATE_SUCCESS` 를 발행하지 않고 `/evaluator/cabinet` 을 구독하지도 않는다
([계약 8절](../../docs/architecture/delivery-contract-v1.md#8-검증)).

## 빌드 확인

```bash
source /opt/ros/jazzy/setup.bash
colcon build --packages-select rokey_p3_interfaces
source install/setup.bash
ros2 interface show rokey_p3_interfaces/msg/CabinetObservation
ros2 interface show rokey_p3_interfaces/action/ScanTag
```
