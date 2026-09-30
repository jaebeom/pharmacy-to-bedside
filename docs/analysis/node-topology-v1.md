# v1 노드 수와 실행 소유권 점검

- 상태: **unreviewed**. 2026-09-17 `main` `ce9c2d2`의 launch·계약·웹 백엔드 코드를 읽은 정적 점검이다.
- 작성: cloud developer. 검토자: 미지정. 대응 run: 없음. 실제 전체 그래프·자원 사용량은 측정하지 않았다.
- 범위: AMR 1대의 배송 v1. 추가 AMR이나 이후 기능의 노드 수는 이 표로 확정하지 않는다.
- 기준: [배송 계약 v1 1절](../architecture/delivery-contract-v1.md#1-노드와-배치), [스텁 launch](../../src/rokey_p3_bringup/launch/stub_loop.launch.py), [주행 launch](../../src/rokey_p3_navigation/launch/navigation.launch.py), [Nav2 launch](../../src/rokey_p3_navigation/launch/nav2.launch.py), [웹 ROS 브리지](../../web/backend/app/ros_bridge.py).

## 몇 개로 보는가

여기서 수는 **동시에 실행하는 ROS 노드**의 계획상 개수다. Python 파일 수, 토픽 수, OS 프로세스 수와 다르다. launch의 `Node(...)` 항목을 세었으며, 조건부 항목은 해당 구성에서 켜질 때만 센다.

| 구성 | 계산 | 합계 | 의미 |
| --- | --- | ---: | --- |
| 현재 기본 스텁 한 바퀴 | orchestrator·order_generator·event_logger 3 + 스텁 4 | 7 | [stub_loop.launch.py](../../src/rokey_p3_bringup/launch/stub_loop.launch.py) 기본값. 전체 실물 구성 아님 |
| 스텁 + Isaac 어댑터 | 위 7 + isaac_adapter 1 | 8 | 스텁의 조제·리셋·벨트 기능만 어댑터로 넘기는 구성. 스텁 노드 자체는 남음 |
| v1 전체 목표 구성 | 오케스트레이션 3 + 주행 자체 노드 3 + Nav2/AMCL/맵/lifecycle 8 + 팔 2 + 인식 1 + Isaac 어댑터 1 | **18** | 계약상 AMR 1대, 스텁 4개를 실물 노드로 교체한 계획치. 이 조합의 동시 실행 검증은 아직 없음 |
| 선택 화면 포함 | 위 18 + status_monitor 1 + 웹 백엔드 `web_gateway` 1 | **20 예상** | status_monitor는 선택 실행. 웹 백엔드 [실물 모드](../../web/backend/app/ros_bridge.py)는 ROS 노드 1개를 만들고, mock 모드는 ROS 노드를 만들지 않음 |

Isaac 스테이지는 위 숫자 밖의 **별도 프로세스**다. 그 안에서 생성되는 ROS 노드 수는 이 저장소의 launch 항목만으로 확정할 수 없다. 프론트엔드 브라우저도 ROS 노드로 세지 않는다. `order_generator`는 합성 요청용이므로 웹에서 요청을 넣는 운영 구성에서 빼면 계획치가 1개 줄 수 있다. 따라서 **18은 현재 v1 목표 구성의 계산값이지 최종 상한이나 실측값이 아니다.**

### AMR 2대와 M0609

계약의 "2대째는 네임스페이스만 `amr_2`"는 **이름 규칙**이다([계약 1절](../architecture/delivery-contract-v1.md#1-노드와-배치)). 실행 노드 수가 그대로라는 뜻이 아니다. 현재 구현은 [orchestrator 한 노드에 `TripFsm` 하나](../../src/rokey_p3_orchestrator/rokey_p3_orchestrator/orchestrator_node.py), [arm](../../src/rokey_p3_manipulation/rokey_p3_manipulation/arm_node.py)·[pouch_detector](../../src/rokey_p3_perception/rokey_p3_perception/pouch_detector_node.py) 각각 `robot_id` 하나, [주행 launch](../../src/rokey_p3_navigation/launch/navigation.launch.py)도 `namespace` 하나를 받는다.

| 역할 | AMR 2대가 되면 |
| --- | --- |
| 로봇별 주행·팔·카메라 인식 | 현재 구조에서는 AMR별 인스턴스가 필요하다. 주행 launch는 로봇당 3개 자체 노드와 Nav2 8개를 생성한다. arm·pouch_detector도 각각 로봇 하나를 대상으로 한다 |
| 조제기·M0609 | 물리 설비는 각각 하나다. **AMR이 2대라는 이유로 `m0609_arm`을 추가하지 않는다.** 같은 조제기와 M0609에 대한 배출·보충 요청은 한 소유자가 조정해야 한다 |
| Isaac 스테이지·run 기록·웹 | 프로세스·노드 공유는 가능하지만, 현재 코드의 2대 동시 처리와 로봇별 표시·기록 분리는 확인되지 않았다. 2대가 된다고 반드시 두 벌로 복제하는 대상은 아니다 |
| orchestrator | 현재 단일 FSM·단일 `robot_id`·전역 `/deliver` 서버라 두 프로세스를 그대로 띄울 수 없다. [ADR 0001](../adr/0001-orchestrator-trip-fsm.md)의 확장안은 FSM 인스턴스 둘과 배차기 하나이며, 한 ROS 노드 안에 둘 수 있지만 아직 구현되지 않았다 |

현재 주행 launch를 두 번째 AMR에 그대로 한 번 더 실행하면 로봇별 노드 13개(주행 11 + arm 1 + 인식 1)가 늘지만 `zones_tf`도 다시 떠 같은 정적 TF를 발행하고, 전역 이름 `base_driver`·`fleet`·`zones_tf`도 중복된다. 이는 유효한 2대 배포안이 아니다. `zones_tf`를 공유하고 나머지 주행/Nav2·arm·인식을 로봇별로 둔다는 **가정** 아래에는 핵심 18개에 약 12개가 더해져 **30개 안팎**이다. 맵·Nav2 구성, 배차기 구현, 화면 배치에 따라 달라지므로 2대의 최종 수는 아직 미결정이다. 로봇 모델 둘을 한 Isaac 프로세스에 넣을지는 별개이며, M0609 실물은 한 대다.

두 AMR이 공유 조제기·벨트·M0609를 요청할 때는 재고·배출·보충·적재 구역의 소유권과 대기/취소 순서를 먼저 정해야 한다. 현재 orchestrator를 두 개 띄우면 `/deliver` 서버와 재고·epoch·리셋 소유권이 중복되므로 노드 수 계산 이전에 배차/공유 자원 계약이 필요하다.

한 배송에 여러 노드가 참여하는 것은 의도된 흐름이다: 요청 클라이언트 → orchestrator(`Deliver` 서버) → fleet·arm·조제기 서버 → orchestrator 결과, 별도로 event_logger·화면이 이벤트를 소비한다. 충돌 여부는 참여 노드의 총수보다 명령·상태 신호의 소유권과 시간 경계에 달려 있다.

## 지금 확인된 위험과 빈틈

| 항목 | 정적 근거·재현 조건 | 영향 | 현재 방어와 남은 일 |
| --- | --- | --- | --- |
| `/clock`·M0609 관측 작성자 중복 가능 | Isaac ROS 스테이지가 이 신호를 내는 동안 `stub_loop.launch.py use_isaac_adapter:=true`만 주면 `publish_clock`·`emulate_m0609` 기본값이 모두 true다. [launch 81–95행](../../src/rokey_p3_bringup/launch/stub_loop.launch.py), [bringup 인자 표](../../src/rokey_p3_bringup/README.md) | 시간·관절 관측의 출처가 둘이 되어 stale 판정·동작 해석이 불명확해진다 | launch는 **경고만** 출력한다. 현행 runbook은 두 인자를 false로 지정한다. 구성별 작성자 목록과 기동 전 중복 확인이 필요하다 |
| 스텁과 실물 액션 서버의 동시 기동 가능 | 스텁 교체는 `use_stub_arm`·`use_stub_fleet`·`use_stub_detector`·`use_stub_m0609` 수동 인자다. 별도로 실물 노드를 켜면서 해당 스텁을 끄지 않으면 같은 서버/상태 이름을 맡을 수 있다 | 어느 서버가 goal을 수락하거나 어느 상태가 최신인지 예측할 수 없다 | [계약 v1 2절](../architecture/delivery-contract-v1.md#2-토픽서비스액션)은 이름·방향을 정한다. 실제 배포 조합별로 서버와 단일 작성자 목록을 확인하는 기동 검사가 필요하다 |
| M0609 시연 제어와 운영 제어의 모드 혼합 | Isaac `--ros-refill-selfdemo`는 `/m0609/*` 명령을 무시하고 자체 보충한다. 동시에 `m0609_arm`으로 오케스트레이터 보충을 시도하면 목표와 물리 동작이 연결되지 않는다([스테이지 인자](../../sim/standalone/pharmacy_stage.py), [bringup 설명](../../src/rokey_p3_bringup/README.md)) | 보충 성공·실패를 운영 제어의 결과로 해석할 수 없다 | run마다 selfdemo 또는 orchestrator 제어 중 하나를 명시하고, 운영 제어 검증에서는 selfdemo를 끈다 |
| 전체 구성의 동시 실행·부하 미검증 | 위 18개는 서로 다른 launch와 계약을 합산한 값이다. [주행 README](../../src/rokey_p3_navigation/README.md)는 기본 맵 파일이 아직 없다고 적는다 | 노드 수만으로 CPU·네트워크·지연·교착 가능성을 판단할 수 없다 | 전체 배포 inventory와 그래프를 실제 run에서 수집하고, 카메라·scan·joint_states 전송량, CPU·메모리, 액션 완료·취소·리셋 지연을 측정한다. 합격선은 측정 전 임의로 정하지 않는다 |

위 표는 코드에서 가능한 조합과 검증 공백을 적은 것이며, 중복 기동이나 제어 충돌이 현장에서 실제 발생했다는 관측은 아니다. 기존 계약에는 한 TF 변환의 작성자 하나, `/clock` 작성자 하나, stale/unknown에서 동작 거부, `epoch`·goal token으로 늦은 결과 무시가 이미 있다([계약 3–5절](../architecture/delivery-contract-v1.md#3-프레임과-단위)). 이 규칙이 모든 배포 조합에서 지켜지는지는 별도 확인이 필요하다.

부하에 관한 경쟁 설명도 남긴다. 문제가 생기면 노드 수 자체가 원인일 수도 있고, 소수 노드의 카메라·scan 전송률이나 연산이 원인일 수도 있다. 같은 구성에서 노드별 CPU·메모리와 토픽 전송량을 함께 재면 구분할 수 있다. 현재는 해당 수치가 없어 어느 쪽도 결론 내리지 않는다.

## 다음 통합에서 확인할 조건

1. 실행 조합마다 토픽·TF·액션·서비스의 작성자/서버와 구독자를 한 표로 확정한다. 스텁과 실물의 같은 역할이 동시에 켜지면 기동을 거부하거나 배포 검사를 실패 처리한다.
2. 하나의 구동 대상에는 활성 제어 주체 하나만 둔다. 요청 진입은 여러 클라이언트가 가능해도 `Deliver` 서버는 하나이고, `request_id` 중복·진행 중 트립 거부는 그대로 확인한다.
3. 노드 종료·재시작, 늦은 goal 결과, heartbeat 단절, 리셋 중 명령을 주입해 guard·취소·복구를 통합 테스트한다. 새 기능은 기존 소유권 표에 추가하고 순환 대기 여부를 검토한다.
4. 같은 구성의 master L3 run에서 실제 `ros2 node list`, 작성자·서버 수, CPU·메모리·네트워크와 지연을 기록한 뒤 증설·노드 통합 필요성을 판단한다.

이 문서는 현행 구현 점검이다. 노드 통합, 배포 배치 또는 안전 규칙을 새로 확정하는 ADR·계약 변경은 아니다.
