# ADR 0002 — Isaac 쪽은 `std_msgs/String` JSON 토픽, 계약 타입은 시스템 ROS 어댑터가 변환한다

- 상태: proposed
- 날짜: 2026-09-17
- 결정자: 재범. 승인 전이다. 9/17 부터 코드가 이 방식을 쓴다
- 승인 PR: 없음(이 ADR 의 PR 에서 검토)
- 관련 issue / RFC / evidence review: PR #100(조제실 스테이지와 JSON 표, 머지됨), PR #108(`isaac_adapter`, 머지됨), 계약 v1 2.1절·7절
- 대체 관계: 없음

## 맥락

관측과 제약. 출처가 따로 없는 줄은 전달받은 관측이며 이 문서를 쓸 때 확인하지 않았다.

- Isaac Sim 5.1 의 내부 Python 은 3.11 이다. 시스템 ROS 2 Jazzy 는 Python 3.12 다([네트워크 문서 6번](../setup/ros2-wired-network.md#6-환경-변수-등록), [5.1 ROS 설치 안내](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_ros.html)).
- Isaac 내부 ROS 라이브러리는 공통 인터페이스만 싣는다. `rokey_p3_interfaces` 는 시스템 Jazzy(3.12)로 빌드되므로 Isaac 안에서 import 되지 않는다고 판단했다. **import 실패를 직접 확인한 기록은 없다(추정).**
- 커스텀 메시지를 Isaac 안에서 쓰려면 IsaacSim-ros_workspaces 로 Python 3.11 빌드가 필요하다. `master02` 설치 작업이다.
- 관측(9/17, `master02`): Isaac 내부 rclpy 로 `std_msgs`·`sensor_msgs` 는 실제로 돌았다.
- 미확인: `std_srvs` 는 확인하지 않았다.
- 계약 v1 의 Isaac 입출력은 `/pharmacy/dispense`(서비스), `/sim/reset`(서비스), `/pharmacy/belt`(`BeltState`), `/events`(`Event`)처럼 커스텀 타입이다.

## 대안

| 안 | 내용 | 비용·한계 |
| --- | --- | --- |
| A | IsaacSim-ros_workspaces 로 `rokey_p3_interfaces` 를 Python 3.11 로 빌드해 Isaac 이 계약 타입을 직접 낸다 | `master02`(와 `master01`) 설치 작업, 인터페이스가 바뀔 때마다 두 빌드를 맞춘다. 설치 권한은 재범. 반증 조건: 3.11 빌드가 한 번에 되고 유지 비용이 작다고 확인되면 A 가 낫다 |
| B | Isaac 은 `std_msgs/String` 에 JSON 을 싣고, 시스템 ROS 쪽 어댑터 노드가 계약 이름·타입으로 바꾼다. 서비스는 요청·응답 토픽 쌍 | 노드 하나가 늘고 변환 지연·형식 오류 경로가 생긴다. JSON 표와 계약을 둘 다 맞춰야 한다. 서비스 시한은 어댑터가 잰다 |

## 결정과 이유

**B안.**
- 오늘 `master02` 에서 돌아간 것(`std_msgs`)만으로 된다.
- 마스터 설치 작업을 기다리지 않는다.
- `std_srvs` 가 미확인이라 서비스 대신 토픽 쌍으로 한다.
- 계약 v1 의 이름·타입은 어댑터 바깥에서 그대로다. 오케스트레이터·팔·스텁은 바뀌지 않는다.

적용 환경: Isaac Sim 5.1(내부 Python 3.11), ROS 2 Jazzy, 조제실 스테이지(`sim/standalone/pharmacy_stage.py`, PR #100).

## 결과

- **어댑터 노드**: `rokey_p3_bringup` 의 `isaac_adapter`. PR #108 로 `main` 에 들어왔다. 어댑터는 `sim/` 을 import 하지 않는다.
- **JSON 표의 기준 문서**: `sim/README.md` 의 "Isaac ↔ ROS 어댑터 인터페이스 (JSON, v1)" 절([Simu README](../../sim/README.md#isaac--ros-어댑터-인터페이스-json-v1), PR #100). 토픽 여섯 개(`/isaac/pharmacy/dispense_request`·`_response`, `/isaac/sim/reset_request`·`_response`, `/isaac/pharmacy/belt`, `/isaac/events`), 모든 메시지에 `"v": 1`. 표를 바꾸면 `v` 를 올린다.
- **계약 v1 은 바꾸지 않는다.** `Dispense` 2 s, `Reset` 30 s 시한은 어댑터가 잰다(PR #100 표 설명).
- **감수할 부채**: 형식 오류는 Isaac 이 응답하지 않고 로그만 남긴다. 그래서 어댑터 시한 초과로만 보인다. JSON 표와 계약 사이의 대응은 사람이 맞춘다.
- **미결정**: 세준의 병원 씬(저장소 밖)이 같은 JSON 방식을 따를지.
- **재검토 조건**: A안의 3.11 빌드가 `master02` 에 설치되고 유지된다. 또는 어댑터 지연·형식 오류가 run 에서 문제로 관측된다.

## 롤백

- 조건: A안으로 계약 타입을 Isaac 이 직접 내게 되거나, 어댑터가 계약 시한을 못 맞춘다.
- 방법: Isaac 쪽 발행을 계약 타입으로 바꾸고 어댑터를 launch 에서 뺀다. JSON 표는 지우지 않고 "superseded" 로 둔다.
- 영향 범위: `sim/standalone/` 의 ROS 입출력, `rokey_p3_bringup` launch, JSON 표. 오케스트레이터·팔·스텁은 계약 타입만 보므로 영향이 없다.
