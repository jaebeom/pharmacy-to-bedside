# ROS2 연동 표 (병원 시연, as-built)

상태: **현황 기록**. 기준: main `f316197`(v1.1.0). 그 커밋의 코드를 읽어 적었다. 계약을 바꾸지 않는다.
행 번호는 모두 `f316197` 의 것이다. 대조하지 않은 것은 8절에 적는다.
코드와 [계약 v1](delivery-contract-v1.md)이 다르면 7절에 적는다. 어느 쪽이 맞는지는 이 문서가 정하지 않는다.

대조한 범위:

- Isaac 쪽: `sim/standalone/p3sim/bridge.py`, `pharmacy_stage.py`(preset·인자·주 루프·`JsonBridge`), `minimal_clock.py`, `p3sim/amr_base.py`, `p3sim/canister_qr.py`, `p3sim/sensors.py`, `p3sim/truth_sensors.py`.
- 어댑터: `src/rokey_p3_bringup/rokey_p3_bringup/isaac_adapter.py`, `isaac_json.py`, `launch/stub_loop.launch.py`(인자와 노드).
- 노드: orchestrator, arm, m0609_arm, pouch_detector, navigation 노드(base_driver·fleet·dock_origin_tf·speed_governor·map_activation_guard).
- 웹: `web/backend/app/ros_spec.py`, `live_sensors.py`, `ros_bridge.py`.
- 기동: `tools/demo_v2.sh`.

## 0. 기준 기동

- 기준 기동은 병원 시연이다(`tools/demo_v2.sh`, `P3_WORLD=hospital`, [hospital-demo 런북](../runbooks/hospital-demo.md)). 로봇 네임스페이스는 `amr_1` 이다.
- v1.1.0 의 병원 기본은 카메라 집기다. `P3_CAMERA_POUCHES` 는 1 이다. `P3_CAMERA_TAGS` 는 그 값을 따른다(`demo_v2.sh` 126·162–163행).
- 이 문서의 "병원 기본"은 이 구성이다. 참값 센서 구성(`P3_CAMERA_POUCHES=0`)은 명시할 때만 뜬다.
- 병원 기본에서 뜨는 노드:
  - 스테이지: `isaac_pharmacy_stage`(JSON), `isaac_amr_1_base`(합본 AMR), `isaac_m0609_stage`(M0609·레일·선반). `pharmacy_stage.py` 1157–1182·3672행이다.
  - stub_loop: orchestrator, event_logger, isaac_adapter, arm, pouch_detector, m0609_detector(`stub_loop.launch.py` 302–387행).
  - demo_v2 가 따로 띄우는 m0609_arm(`demo_v2.sh` 401–408행).
  - navigation: base_driver, fleet, zones_tf, dock_origin_tf, Nav2, map_activation_guard, speed_governor.
  - 웹: `web_gateway`(`ros_bridge.py` 119행).
- stub_sim·stub_fleet·stub_arm·stub_detector·order_generator 는 병원 기본에서 끈다(`demo_v2.sh` 435·437·449·463행).
- status_monitor 는 병원 기동에서 띄우지 않는다. stub_loop 와 demo_v2 에 없다.

## QoS 약어

- QoS 약어는 계약 2절이다. 코드의 함수는 `rokey_p3_orchestrator/ros_qos.py` 17–34행이다. 모두 KEEP_LAST 다.

| 약어 | 함수 | reliability | durability | depth |
| --- | --- | --- | --- | --- |
| S | `sensor_qos` | best effort | volatile | 5 |
| R | `reliable_qos` | reliable | volatile | 10 |
| H | `heartbeat_qos` | reliable | volatile | 1. 5 Hz 로 낸다. 1.0 s wall 동안 안 오면 unknown 이다 |
| L | `latched_qos` | reliable | transient local | 인자 |

- "wall" 주기는 스테이지 주 루프의 `time.monotonic()` 기준이다(`pharmacy_stage.py` 3502행). sim 시간 기준이 아니다.
- "미측정"은 코드에서 계산한 값이라는 뜻이다. 회차에서 잰 적이 없다.

## 1. `/clock` 과 `use_sim_time`

| 항목 | 값 | 근거 | 계약 |
| --- | --- | --- | --- |
| 발행자 | Isaac OmniGraph `OnPlaybackTick → ROS2PublishClock`. 스테이지 PC 하나뿐이다 | `sim/standalone/minimal_clock.py` 41·172–195행, `pharmacy_stage.py` 1129행 | [2.1](delivery-contract-v1.md#21-시뮬레이터가-내고-받는-것-simulation) |
| QoS | rmw 기본(reliable·volatile), queue 10 | `minimal_clock.py` 43–46행 | 계약은 R |
| 주기 | 렌더 틱마다. 병원 preset `render_every` 는 2 다. 그래서 약 30 Hz 로 계산된다. **미측정** | `pharmacy_stage.py` 206·612·616·694–700·1188–1191행 | 계약 목표 60 Hz 와 다르다 |
| 발행자 하나 확인 | 스테이지가 다른 PC 면 `Publisher count` 가 1 이어야 한다. 2 s 안에 sim 시간이 흘러야 한다. 같은 PC 면 기동 전 0 이어야 한다. 기동 뒤에는 수만 찍는다 | `tools/demo_v2.sh` 556–590·697–715·858·925행 | [1.1](delivery-contract-v1.md#11-실제-배치-924) |
| 스텁 시계 | 병원은 stub_sim 을 끈다(`use_stub_sim:=false`). `publish_clock:=false` 도 준다. stub_sim 의 `use_sim_time` 은 `not publish_clock` 이다 | `demo_v2.sh` 435·476행, `stub_loop.launch.py` 326–336행 | |
| `use_sim_time` | 아래 노드는 true 다. 예외는 아래에 적는다 | 아래 | [4](delivery-contract-v1.md#4-시간epochstale) |

`use_sim_time: true` 를 넣는 곳:

- `stub_loop.launch.py` 282행의 `sim_time`: orchestrator, order_generator, event_logger, isaac_adapter, stub_fleet, stub_arm, arm, stub_detector, pouch_detector, m0609_detector(302–387행).
- `navigation.launch.py` 42·74행: base_driver, fleet, zones_tf, dock_origin_tf. 99행에서 Nav2 launch 로 넘긴다.
- `nav2.launch.py` 40·68·81행: Nav2 노드, lifecycle manager, speed_governor. `nav2_params.yaml` 16·137행 등에도 있다.
- `demo_v2.sh` 403행: m0609_arm 을 `-p use_sim_time:=true` 로 띄운다. launch 밖이다.
- 팔·M0609 팔·pouch_detector 는 false 면 경고를 남긴다(`arm_node.py` 481행, `m0609_arm_node.py` 307행, `pouch_detector_node.py` 105행).

예외:

- map_activation_guard 는 `use_sim_time` 을 받지 않는다. 파라미터는 `target` 하나다(`nav2.launch.py` 92–94행). 시한은 `time.monotonic()` 으로 잰다(`map_activation_guard_node.py` 36행).
- 웹(`web_gateway`)은 설정하지 않는다(`ros_bridge.py` 에 `use_sim_time` 이 없다). 신선도는 wall 로 잰다. 그래서 표시에는 영향이 없다.
- 하트비트·watchdog 타이머는 wall 이다(`base_driver_node.py` 71–72행, `fleet_node.py` 200–201행, `isaac_adapter.py` 233행). 계약 4절과 같다.

## 2. TF 트리

```
map ─(dock_origin_tf, /tf_static)─ amr_1/odom ─(base_driver, /tf)─ amr_1/base_link
 │                                                                   ├─ amr_1/lidar_link          (Isaac, /tf_static)
 │                                                                   ├─ amr_1/hand_camera_optical (Isaac, /tf)
 │                                                                   └─ amr_1/ur_arm_base_link    (Isaac, /tf_static)
 │                                                                        ├─ amr_1/ur_arm_*_link   (Isaac, /tf)
 │                                                                        └─ amr_1/deck_slot_1..N  (Isaac, /tf_static)
 └─ pharmacy/*, <zone>/cabinet, <zone>/tag, pharmacy/belt_end            (zones_tf, /tf_static)
```

| 변환 | 발행자 | 주기 | 근거 | 계약 |
| --- | --- | --- | --- | --- |
| `map → amr_1/odom` | 병원(`localization:=odom`): `dock_origin_tf`. 도크 x·y 만큼 옮긴 정적 TF, yaw 0. 기본(`amcl`)이면 AMCL | 한 번(`/tf_static`) | `navigation.launch.py` 36–37·64–65·89–93행, `dock_origin_tf_node.py` 37–61행, `demo_v2.sh` 414–417행 | [3](delivery-contract-v1.md#3-프레임과-단위)(시뮬 전용 예외), [ADR 0003](../adr/0003-ward-driving-approach-point.md)(proposed) |
| `amr_1/odom → amr_1/base_link` | base_driver | `joint_states` 새 stamp 마다. `/amr_1/odom` 과 짝이다. 같은 stamp 는 건너뛴다 | `base_driver_node.py` 62–65·83–155행 | 3절 |
| `base_link` 아래 센서·팔·상판 칸 | Isaac(`amr_base.publish_tf`). 정적: `ur_arm_base_link`·`deck_slot_*`·`lidar_link`. 동적: `ur_arm_*_link`·`hand_camera_optical` | 동적은 OmniGraph 틱마다(미측정) | `amr_base.py` 830–903행, `pharmacy_stage.py` 1558–1567행 | 3절 |
| zone 프레임 | zones_tf(`P3_ZONES` 파일) | 한 번(`/tf_static`) | `zones_tf_node.py` 26행 | 3절 |

- 규칙: 변환마다 발행자는 하나다. Isaac 은 `map`·`odom` 을 자식으로 내지 않는다(계약 3절).
- Isaac 은 `amr_1/base_link` 자체를 내지 않는다. 쓰는 쪽은 base_driver 다(`amr_base.py` 15행, 838–855행).
- M0609 손 카메라(`m0609/hand_camera_optical`)의 TF 는 없다(`canister_qr.py` 284·325행 `tf=none`, [QR 배치와 카메라](qr-camera-layout.md) 2절).
- 도크 자리: 병원 zones 두 파일 모두 `load` 와 `dock_1` 이 같은 자세다(#790, #797). 그래서 `dock_origin_tf` 의 평행이동도 적재 자리다.
  - 카메라 기본은 `zones.hospital-receiver.yaml` 이다. `dock_1` = `load` = (−8.266, 4.102)이다(`demo_v2.sh` 131–133행).
  - 참값 구성은 `zones.hospital.yaml` 이다. `dock_1` = `load` = (−8.995, 4.686)이다(`demo_v2.sh` 138·143행).
- 카메라 기본의 `pharmacy/belt_end` 는 롤러 끝이 아니다. 봉투가 정착하는 A1 모듈 탁자 위 점(−8.266, 4.902, 0.366)이다(`sim/standalone/hospital_nav_files.py` 19–20·45–46행).

## 3. 이미지·스캔

| 토픽 | 발행자 | 해상도 | 주기 | QoS | 구독자 | 근거 | 계약 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/amr_1/hand_camera/image_raw`·`camera_info` | Isaac `amr_base.add_hand_camera`(합본 AMR, D455 컬러) | 1280×800(`P3_CAMERA_RESOLUTION` 기본). 스테이지 인자 기본은 640×480 | ≤ 10 Hz(`--camera-max-hz` 10, render 30 Hz → 2틱 건너뜀). 미측정 | best effort, volatile, depth 2 | pouch_detector(병원 기본 켬). 웹은 `--live-sensors` 일 때만 구독한다. demo_v2 는 그 인자를 주지 않는다 | `amr_base.py` 728–827행, `sensors.py` 15–17·42–50행, `pharmacy_stage.py` 593–596·1548–1557행, `demo_v2.sh` 193·346·449·483–495행 | [2.1](delivery-contract-v1.md#21-시뮬레이터가-내고-받는-것-simulation) 손 카메라(S depth 2, ≤ 10 Hz) |
| `/m0609/hand_camera/image_raw`·`camera_info` | Isaac `canister_qr.M0609HandCamera` | 960×600 | ≤ 10 Hz | best effort, volatile, depth 2 | m0609_detector | `canister_qr.py` 255–334행, `pharmacy_stage.py` 527·1496–1505행, `demo_v2.sh` 191·368·473행(`P3_CONTAINER_QR=1`) | [QR·DB·카메라 계약](qr-db-camera-contract-v1.md) 3절 |
| `/amr_1/hand_camera/qr_view`·`/m0609/hand_camera/qr_view` | pouch_detector·m0609_detector(#787) | 폭 ≤ 640(bgr8) | 구독자가 있을 때만 처리한 프레임마다 그려 낸다 | best effort, volatile, depth 2 | 촬영 창 `rqt_image_view`(`P3_CAMERA_VIEW=1`, AMR 쪽만). 웹 `amr_qr`·`m0609_qr`(`--live-sensors` 일 때) | `pouch_detector_node.py` 47–49·125–127·239–247행, `qr_overlay.py` 15행, `demo_v2.sh` 773–783행, `live_sensors.py` 42–51행 | 계약에 없다 |
| `/amr_1/scan` | Isaac RTX 2D 라이다(`ROS2RtxLidarHelper`, frame `amr_1/lidar_link`) | — | 헬퍼 기본값. 코드에 없다. 미측정 | 헬퍼 기본값. 코드에 없다 | Nav2 local·global costmap(`topic: <robot_namespace>/scan`), AMCL(`scan_topic: scan`, odom 모드에서는 안 띄움). 웹은 `--live-sensors` 일 때만 | `amr_base.py` 538–647행, `demo_v2.sh` 339행(`--amr-lidar`), `nav2_params.yaml` 20·174·222행, `ros_bridge.py` 177행 | 2.1 `/amr_1/scan`(S, 10 Hz) |

- `a1_pick` 은 ROS 토픽이 아니다. 뷰포트 캡처 시점이다(`p3sim/views.py` 67행, [촬영 샷리스트](../presentation/hospital-demo-shotlist.md)).
- `/amr_1/front_camera`(계약 2.1, 기본 꺼짐)는 Isaac 구현을 찾지 못했다(미확인).
- 원샷 촬영은 구현되지 않았다. 카메라는 계속 낸다([QR 배치와 카메라](qr-camera-layout.md) 2절).
- 검출기 추론 상한 `detector_max_rate_hz` 는 launch 기본 0(상한 없음)이다. 병원 기본 demo_v2 는 이 인자를 주지 않는다(`stub_loop.launch.py` 245–247행, `demo_v2.sh` 449–452행). 5 Hz 는 참값 분기(`P3_CAMERA_POUCHES=0 P3_SIM_SENSORS=1`)에서 `P3_DECK_VISION=1` 일 때만이다(`demo_v2.sh` 453–457행).

## 4. Isaac JSON 토픽 14개

Isaac 은 `std_msgs/String` JSON 을 낸다. 1–13 은 `isaac_adapter` 가 계약 이름·타입으로 바꾼다([ADR 0002](../adr/0002-isaac-json-topics-and-ros-adapter.md)). 14 는 웹이 직접 읽는다.

- 이름과 QoS 는 `sim/standalone/p3sim/bridge.py` 16–47·57–81행에 있다. 그 표의 `/isaac/*` JSON 토픽은 14개다.
- 어댑터 쪽 거울은 `isaac_adapter.py` 99–113·191–235행이다. 어댑터가 다루는 것은 13개다.
- 스테이지 쪽 노드는 `isaac_pharmacy_stage`(`pharmacy_stage.py` 3661–3718행), 어댑터 노드는 `isaac_adapter` 다.
- "병원 기본" 열은 `demo_v2.sh` 기본값에서 스테이지가 내고 어댑터가 옮기는지다.

| # | JSON 토픽 | 방향 | QoS | 주기 | 어댑터 쪽 계약 이름(타입, QoS) | 병원 기본 | 계약 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `/isaac/pharmacy/dispense_request` | ROS → Isaac | R | 호출마다 | 서비스 `/pharmacy/dispense`(`Dispense`)의 요청 | 켬 | [2.1](delivery-contract-v1.md#21-시뮬레이터가-내고-받는-것-simulation) |
| 2 | `/isaac/pharmacy/dispense_response` | Isaac → ROS | R | 요청마다 | 같은 서비스의 응답 | 켬 | 2.1, [7](delivery-contract-v1.md#7-id타임아웃재시도) 시한 |
| 3 | `/isaac/sim/reset_request` | ROS → Isaac | R | 호출마다 | 서비스 `/sim/reset`(`Reset`)의 요청 | 켬 | 2.1, [6](delivery-contract-v1.md#6-리셋-barrier) |
| 4 | `/isaac/sim/reset_response` | Isaac → ROS | R | 요청마다 | 같은 서비스의 응답 | 켬 | 2.1, 6 |
| 5 | `/isaac/pharmacy/belt` | Isaac → ROS | H | 5 Hz wall | `/pharmacy/belt`(`BeltState`, H) | 켬 | 2.1 |
| 6 | `/isaac/events` | Isaac → ROS | L 500 | 바뀔 때(`DISPENSED`·`POUCH_AT_END`) | `/events`(`Event`, L 500) | 켬 | [2.6](delivery-contract-v1.md#26-이벤트-누가-무엇을-내는가) |
| 7 | `/isaac/pharmacy/pick_notice` | ROS → Isaac | R | `POUCH_PICKED` 마다 | `/events` 의 `POUCH_PICKED` 에서 | 끔(`pick_notice:=false`, `demo_v2.sh` 437행) | 계약에 없다(`sim/README.md` JSON 표) |
| 8 | `/isaac/pharmacy/belt_observation` | Isaac → ROS | H | 5 Hz wall(`--belt-observation`) | `/pharmacy/belt/observation`(`BeltObservation`, H) | 끔(스테이지 인자·어댑터 `belt_observation` 둘 다 안 준다) | [11.6](delivery-contract-v1.md#116-병행-관측-토픽) |
| 9 | `/isaac/amr_1/gripper/state` | Isaac → ROS | H | 10 Hz wall(`--gripper-command-seq`) | `/amr_1/gripper/state`(`GripperState`, H) | 끔 | 11.6 |
| 10 | `/isaac/amr_1/gripper/command_seq` | ROS → Isaac | R | 명령마다 | `/amr_1/gripper/command_seq`(`GripperCommand`, R) | 끔 | 11.6 |
| 11 | `/isaac/amr_1/pouches` | Isaac → ROS | H | 10 Hz wall(`--sim-sensors`) | `/amr_1/sim/pouches`(`PouchDetectionArray`, H, `sim_pouches`) | 끔. 카메라 기본은 `P3_SIM_SENSORS=1` 이어도 옮기지 않는다 | 2.x 에 없다. 계약 [2.4](delivery-contract-v1.md#24-인식-perception)의 `hand_camera/pouches` 는 카메라 경로 |
| 12 | `/isaac/amr_1/tag_reads` | Isaac → ROS | H | 5 Hz wall. 인식표가 범위 안일 때만 | `/amr_1/sim/tag_reads`(`TagRead`, H, `sim_tag_reads`) | 끔. `P3_CAMERA_TAGS=0 P3_SIM_SENSORS=1` 이면 옮긴다(`demo_v2.sh` 447행) | 2.x 에 없다(11과 같음) |
| 13 | `/isaac/evaluator/cabinet` | Isaac → ROS | L 50 | 5 Hz wall | `/evaluator/cabinet`(`CabinetObservation`, L 50) | `P3_SIM_SENSORS=1` 일 때만 켬(`demo_v2.sh` 344·445행). 기본 0 이다(177행) | 2.1 |
| 14 | `/isaac/fleet/poses` | Isaac → 웹 | R depth 1 | 5 Hz wall | 어댑터 없음. `web_gateway` 가 `String` 으로 직접 구독한다(`ros_spec.py` 50행) | 켬. preset `hospital` 의 가짜 AMR 2대 때문이다(`pharmacy_stage.py` 93·3721–3724행) | 계약에 없다(웹 [api.md](../../web/api.md) 1.6) |

- 주기 근거:
  - 11–13 은 `truth_sensors.py` 38·40·97행과 `pharmacy_stage.py` 3518–3529행이다.
  - 5·8 은 `pharmacy_stage.py` 3595–3604행, 9 는 3570–3575행, 14 는 3576–3585행(`bridge.FLEET_POSES_HZ`, `bridge.py` 41행)이다.
- `/isaac/*` 밖에서 스테이지가 직접 내는 것이 둘 더 있다. 어댑터를 거치지 않는다.
  - `/m0609/shelf/inventory`(`std_msgs/String` JSON, L 1). `isaac_m0609_stage` 가 바뀔 때 낸다. m0609 팔과 웹이 읽는다(`m0609_refill_stage.py` 931–941행, `pharmacy_stage.py` 2828–2848행).
  - `/p3/sim_running`(`std_msgs/Bool`, JSON 아님). 5절에 적는다.

## 5. 이벤트·주문 상태·그 밖 토픽

| 토픽 | 타입 | 발행자 | 구독자 | 주기 | QoS | 계약 |
| --- | --- | --- | --- | --- | --- | --- |
| `/events` | `Event` | orchestrator(`orchestrator_node.py` 249행), arm(`arm_node.py` 531행), m0609_arm(342행), pouch_detector(124행), isaac_adapter(194행). 어댑터는 Isaac 의 `DISPENSED`·`POUCH_AT_END` 를 옮긴다. `DISPENSER_PAUSED`·`REFILL_REQUESTED` 같은 조제기 상태 이벤트는 orchestrator(`trip_fsm.py`)가 낸다 | event_logger, web, arm·m0609_arm·pouch_detector·isaac_adapter(리셋), fleet. order_generator 는 병원 기본에서 안 뜬다 | 바뀔 때 | L 500. **fleet 만 R 10** — 다시 떠도 `RESET_DONE` 을 재생하지 않게 일부러 그렇게 했다(`fleet_node.py` 194–198행) | [2.5](delivery-contract-v1.md#25-오케스트레이션), 2.6 |
| `/orders/status` | `OrderStatus` | orchestrator(251행) | event_logger, web | 바뀔 때 | L 50 | 2.5 |
| `/pharmacy/dispenser/status` | `DispenserStatus` | orchestrator(252–253·298행) | web | 바뀔 때 + 1 Hz | L 1 | 2.5 |
| `/amr_1/arm/at_home` | `Bool` | arm(`arm_node.py` 513–514·560행) | orchestrator, fleet, web | 5 Hz | H | [2.3](delivery-contract-v1.md#23-팔-manipulation) |
| `/m0609/arm/at_home` | `Bool` | m0609_arm(338·389행) | web | 5 Hz | H | 2.1 |
| `/amr_1/base/stopped` | `Bool` | fleet(`fleet_node.py` 176–177·200–201행) | orchestrator, arm, web | 5 Hz wall | H | [2.2](delivery-contract-v1.md#22-주행-navigation) |
| `/amr_1/gripper/holding` | `Bool` | Isaac(`joint_states` 와 같은 주기) | arm, orchestrator, web | 20 Hz wall | H | 2.1 |
| `/amr_1/joint_states` | `JointState` | Isaac(`isaac_amr_1_base`) | base_driver, arm | 20 Hz wall(`amr_base.COMMAND_HZ`) | best effort 5 | 2.1 |
| `/amr_1/cmd_vel` | `Twist` | Nav2 controller_server, fleet 추종기(마지막 구간) | base_driver(0.5 s 없으면 0) | 20 Hz | R | 2.2 |
| `/amr_1/odom` | `Odometry` | base_driver(62행) | fleet, Nav2, speed_governor | `joint_states` 마다 | R | 2.2 |
| `/amr_1/speed_limit` | `nav2_msgs/SpeedLimit` | speed_governor(`speed_governor_node.py` 54–56·110행) | controller_server, web | 1 Hz 재발행 | reliable, transient local, depth 1 | [10.3](delivery-contract-v1.md#103-amr_1speed_limit-신설-923) |
| `/amr_1/initialpose` | `PoseWithCovarianceStamped` | fleet(178–179행), `RESET_DONE` 뒤 한 번 | AMCL(odom 모드에서는 안 띄움) | 한 번 | R 10 | 2.2 |
| `/amr_1/base/docked` | `DockingState` | fleet, opt-in(`publish_docking_state`, 기본 꺼짐) | 없음 | — | H | 11.6 |
| `/amr_1/hand_camera/tag_reads` | `TagRead` | pouch_detector(`pouch_detector_node.py` 120–121행) | arm(`scan_tag_source:=camera`), orchestrator(`orchestrator_node.py` 283–284행), web(`qr_read`) | 판독마다 | R 10 | [2.4](delivery-contract-v1.md#24-인식-perception) |
| `/amr_1/hand_camera/pouches` | `PouchDetectionArray` | pouch_detector(122–123행). 검출 0건이어도 빈 배열 | arm(`pouch_source:=camera`) | 처리한 프레임마다 | R 5 | 2.4 |
| `/m0609/hand_camera/tag_reads` | `TagRead` | m0609_detector(같은 노드, `robot_id=m0609`) | m0609_arm(`container_check`, `m0609_arm_node.py` 368행), web(`tag_read`) | 판독마다 | R 10 | [QR·DB·카메라 계약](qr-db-camera-contract-v1.md) 2.3 |
| `/p3/alerts` | `std_msgs/String` JSON | orchestrator(250행, `DOCK_*`), map_activation_guard(`map_activation_guard_node.py` 33–35행, `MAP_GUARD_*`) | web | 바뀔 때 | L 20 | 계약에 없다(`rokey_p3_navigation/alerts.py` 1–16행) |
| `/p3/sim_running` | `std_msgs/Bool` | Isaac 스테이지(`pharmacy_stage.py` 3685–3687·3586–3594행) | web | 바뀔 때 + 1 Hz wall | reliable, volatile, depth 1 | 계약에 없다(`bridge.py` 43–47행) |

- 웹의 구독 표는 `web/backend/app/ros_spec.py` 34–66행이다.

## 6. 액션·서비스

| 이름 | 타입 | 서버 | 클라이언트 | 시한 | 계약 |
| --- | --- | --- | --- | --- | --- |
| `/deliver` | `Deliver` | orchestrator(286–288행). cancel 거부 | web. order_generator 는 병원 기본에서 안 뜬다 | 트립 600 s sim | 2.5, 7 |
| `/amr_1/go_to_zone` | `GoToZone` | fleet(205–210행) | orchestrator | 120 s(load·dock)·180 s(병동) sim | 2.2, 7 |
| `/amr_1/pick_pouch` | `PickPouch` | arm(562–567행) | orchestrator | 60 s sim | 2.3, 7 |
| `/amr_1/scan_tag` | `ScanTag` | arm(569–574행) | orchestrator | 30 s sim | 2.3, 7 |
| `/m0609/refill` | `Refill` | m0609_arm(391–396행) | orchestrator | 90 s sim, 3회 | 2.1, 7 |
| `/pharmacy/dispense` | `Dispense` | isaac_adapter(234행) | orchestrator | 2 s wall(기본). 병원은 `P3_DISPENSE_TIMEOUT_S` 30 s | 2.1, 7 |
| `/sim/reset` | `Reset` | isaac_adapter(235행) | orchestrator | 30 s wall | 2.1, 6 |
| `/orchestrator/reset` | `Reset` | orchestrator(289행, `~/reset`). 응답은 곧바로 ok 다. barrier 완료가 아니다 | web | — | 6 |
| `/orchestrator/check_container` | `CheckContainer` | orchestrator(`pharmacy_db:=true` 일 때, 290–295행) | m0609_arm(`container_check` 일 때, 370행) | 팔 쪽 2 s wall | [QR·DB·카메라 계약](qr-db-camera-contract-v1.md) 2.3 |

- 시한 근거: `trip_fsm.py` 158–161·174행(GoToZone·PickPouch·ScanTag·트립), `refill_planner.py` 65행(Refill), `demo_v2.sh` 146·468행(병원 Dispense).
- 적재 자리가 곧 도크이면 orchestrator 는 도크에서 적재 자리로 가는 `GoToZone` 을 보내지 않는다(`trip_fsm.py` 151–154·194행, `load_is_dock`). 병원 zones 두 파일은 모두 그 경우다(2절).

## 7. 코드와 계약이 다른 곳

| 곳 | 계약 | 코드 |
| --- | --- | --- |
| `/clock` 주기 | 60 Hz(2.1) | 렌더 틱마다, 병원 약 30 Hz(계산값, 미측정) |
| `/amr_1/joint_states` 주기 | 30 Hz(2.1) | 20 Hz wall(`amr_base.py` 30행) |
| `/amr_1/gripper/holding` 주기 | 10 Hz(2.1) | `joint_states` 와 같은 20 Hz wall |
| `/evaluator/cabinet` 주기 | 바뀔 때 + 1 Hz(2.1) | 5 Hz wall(`truth_sensors.py` 97행). 병원 기본(`P3_SIM_SENSORS=0`)에서는 아무도 내지 않는다 |
| `/amr_1/speed_limit` QoS | R(10.3) | reliable + transient local, depth 1 |
| `/amr_1/initialpose` depth | R depth 1(2.2) | depth 10 |
| `/pharmacy/dispense` 병원 시한 | 10 s(7) | `P3_DISPENSE_TIMEOUT_S` 기본 30 s(`demo_v2.sh` 146행. 10 s 에서 `not_ready` 거부 3회) |
| `/m0609/arm/at_home` 구독 | orchestrator 가 구독(2.1) | orchestrator 구독을 찾지 못했다(`orchestrator_node.py` 269–284행) |
| 손 카메라 구독자 | `image_raw` 는 pouch_detector **만**(2.1) | 병원 기본은 pouch_detector 만 구독한다. 웹 `--live-sensors` 를 켜면 웹도 `image_raw` 를 구독한다(`live_sensors.py` 42–46행) |
| 계약 밖 토픽 | — | `/<robot>/hand_camera/qr_view`(#787), `/p3/alerts`, `/p3/sim_running`, `/isaac/fleet/poses` 가 있다. 모두 표시용이다. 판정에는 쓰지 않는다 |
| 여벌 AMR 카메라 주기 | — | `P3_AMR_COUNT` > 1 의 여벌은 `1/render_dt` 로 계산해 약 5 Hz 다(`pharmacy_stage.py` 1414–1417행). 첫 대는 10 Hz |
| JSON 토픽 목록 | [ADR 0002](../adr/0002-isaac-json-topics-and-ros-adapter.md)·`sim/README.md` JSON 표는 앞 6–7개만 적는다 | `bridge.py` 에 14개다(8–14 는 나중에 더했다) |
| `use_sim_time` | 모든 노드 sim time(4절) | map_activation_guard 와 web_gateway 는 설정하지 않는다(1절) |

## 8. 확인하지 않은 것

- `/clock`, 동적 TF, `/amr_1/scan`, 손 카메라, `qr_view` 의 실제 주기. 회차에서 `ros2 topic hz` 로 잰 기록이 없다.
- `/amr_1/scan` 의 QoS 와 Nav2 costmap 구독 QoS. 둘 다 저장소에 설정이 없다(헬퍼·Nav2 기본값).
- `/amr_1/front_camera` 의 Isaac 구현.
- 계약 문서의 행 번호. 계약 문서는 절 번호로만 가리킨다.
- v1.1.0 커밋 `f316197` 로 돌린 acceptance 회전은 없다. 이 표의 토픽이 병원 기본에서 실제로 흐르는지는 v1.1.0 에서 L3 로 확인하지 않았다.
  - 카메라 기본 구성의 연습 회차는 `05b8e28` 의 bed_a1 1건이다([실습45](../practice/simworld/practice-45.md)).
