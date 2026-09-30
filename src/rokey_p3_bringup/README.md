# rokey_p3_bringup

v1.1.0 병원 한 바퀴에서 `tools/demo_v2.sh` 의 stack 역할이 `stub_loop.launch.py` 하나로 ROS 쪽 노드 여섯을 띄운다.
그 여섯은 `orchestrator`·`event_logger`·`isaac_adapter`·UR5 `arm`·`pouch_detector`·`m0609_detector` 다. 스텁 넷은 끈다([아래 절](#v110-병원-한-바퀴의-stack-인자)).
`isaac_adapter` 가 Isaac 스테이지의 JSON 토픽을 계약 이름·타입으로 옮긴다.

기동 조합과 스텁 서버 넷. **orchestration 담당**이 소유한다.

## 스텁 한 바퀴

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py
```

오케스트레이션 노드 셋(`orchestrator`, `order_generator`, `event_logger`)과 스텁 넷을 띄운다.
요청 1건이 `Deliver` 결과 `success=true` 로 끝나고 `/events` 가 계약 2.6절의 순서로 찍힌다.

실물이 되는 대로 인자를 하나씩 끈다. 인터페이스 이름은 그대로다.

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py use_stub_fleet:=false
```

| 인자 | 기본값 | 무엇 | 언제 바꾸나 |
| --- | --- | --- | --- |
| `use_stub_arm` | `true` | `PickPouch`, `ScanTag`, `/m0609/refill` 서버와 `arm/at_home`·`/m0609/arm/at_home` | 실물 UR5 `arm` 노드를 띄울 때 `false` |
| `use_stub_fleet` | `true` | `GoToZone` 서버와 `base/stopped` | 실물 fleet(Nav2)을 띄울 때 `false` |
| `use_stub_sim` | `true` | `/clock`, `Dispense`, `Reset`, `/pharmacy/belt`, `gripper/holding`, `/evaluator/cabinet`, `/m0609/joint_states`, `/m0609/gripper/holding` | Isaac 이 이 이름을 **전부** 낼 때만 `false`. 일부만 내면 아래 `publish_clock`·`emulate_m0609` 로 그 기능만 끈다 |
| `use_stub_detector` | `true` | `tag_reads`, `pouches` | 실물 perception 을 띄울 때 `false` |
| `use_stub_m0609` | `true` | stub_arm 의 `/m0609/refill` 서버와 `/m0609/arm/at_home` | 실물 `m0609_arm` 을 `ros2 run rokey_p3_manipulation m0609_arm` 으로 따로 띄울 때 `false` |
| `max_requests` | `1` | 발행기가 보낼 요청 수. 0 이면 주문 풀 전부 | 한 바퀴보다 많이 돌릴 때 |
| `use_order_generator` | `true` | 자동 주문 발행기를 띄운다 | 요청을 웹·curl 로만 넣을 때 `false`. **`max_requests:=0` 은 끔이 아니라 주문 풀 전부다** |
| `log_dir` | 빈 값 | run 기록 위치. 비우면 `$ROS_HOME/rokey_p3/runs` | run 을 모을 곳을 정할 때 |
| `publish_clock` | `true` | `stub_sim` 이 `/clock` 을 낸다 | Isaac 이 `/clock` 을 낼 때 `false`(작성자 하나, 계약 4절) |
| `run_host` | 빈 값 | `event_logger` 의 run ID 호스트 칸. 비우면 hostname | 마스터에서 `master01`·`master02` |
| `emulate_m0609` | `true` | `stub_sim` 이 `/m0609/joint_states`·`/m0609/gripper/holding` 을 낸다 | Isaac M0609 장면이 그 둘을 낼 때 `false` |
| `pharmacy_only` | `false` | `orchestrator` 가 조제실 구간만 돈다. 적재 뒤 도크로 복귀하고 실은 주문은 `HOLD_RETURN`(reason `pharmacy_only`) | protocol `pharmacy-lap-pilot-v1` 을 돌릴 때 `true` |
| `dispenser_file` | 빈 값 | `orchestrator` 재고 파일. 비우면 `rokey_p3_orchestrator` share 의 `config/dispenser.yaml` | 보충을 유도할 때(활성 슬롯 1, 다른 슬롯 0) |
| `order_pool_file` | 빈 값 | 주문 풀 파일. `orchestrator`·`order_generator`·`stub_sim`·`stub_arm`·`stub_detector` 가 같은 파일을 읽는다. 비우면 share 의 `config/order_pool.yaml` | 다른 주문 풀로 돌릴 때 |
| `zones_file` | 빈 값 | `orchestrator` 구역 파일. 병실 테이블(kind station + room)이 있으면 병실 묶음을 그 테이블 한 곳에 놓고, 스테이션 자리(kind station)의 주문은 `st-<zone>` 인식표로 인증한다(재범 9/25). 비우면 예전처럼 병실 묶음이 침상마다 서고 모든 1인 주문이 `pt-` 로 인증한다 | 병원(`tools/demo_v2.sh` 가 `P3_ZONES` 를 준다) |
| `use_isaac_adapter` | `false` | `true` 면 `stub_sim` 의 `Dispense`·`Reset`·`/pharmacy/belt` 를 끄고 `isaac_adapter` 가 Isaac JSON 토픽으로 맡는다(아래) | Isaac 조제실 스테이지(`pharmacy_stage.py --mode ros`)를 붙일 때 `true`. `publish_clock`·`emulate_m0609` 중 하나라도 true 면 launch 가 경고한다 |
| `publish_cabinet` | `true` | `stub_sim` 이 `/evaluator/cabinet`(`CabinetObservation`)을 낸다 | Isaac 이 보관함 참값을 낼 때 `false`(작성자 하나, 계약 2.1절). **끄면 그 회차는 run 기록의 `SUCCESS` 근거가 없다**(계약 8절) — Isaac 쪽이 실제로 낼 때만 끈다 |
| `use_ur5_arm` | `false` | 실물 UR5 팔 노드(`rokey_p3_manipulation` 의 `arm`)를 같이 띄운다. 지금 시연 경로에는 이 노드가 없다 | 실물 UR5 가 Isaac 에서 집는 구성에서 `true`. `use_stub_arm:=false` · `pick_notice:=false` · `ur5_arm_params_file` 과 한 묶음이고, 어긋나면 launch 가 노드를 하나도 띄우지 않고 멈춘다 |
| `ur5_arm_params_file` | 빈 값 | UR5 팔 노드의 현장값 파일(프레임 이름·홈 자세·오프셋). 이 인자로만 준다 | `use_ur5_arm:=true` 면 반드시 준다. 빈 값이면 기동을 거부한다 |
| `deck_slots` | `5` | AMR 상판에 실을 수 있는 봉투 수. 넘치면 그 주문은 `ABORT deck_full` 이다 | 통짜 트레이 상판은 **3**(시뮬 #445). `demo_v2.sh` 의 한 바퀴 월드(emptyworld·hospital)가 그 값을 준다 |
| `belt_timeout_s` | `20.0` | 조제 뒤 봉투가 벨트 끝에 닿기를 기다리는 시한(sim s) | 병원 컨베이어는 A1 롤러 끝까지 34.58 s 였다(#240). `demo_v2.sh` 병원 기본은 60(`P3_BELT_TIMEOUT_S`) |
| `observation_guard` | `false` | orchestrator 의 계약 11.3·11.6 관측 guard(**시험용**). 피킹·다음 배출에 `BeltObservation`·`ArmClearance` 를 더 요구한다 | 관측 생산자(시뮬·팔)가 있는 시험 구성에서만. `ArmClearance` 의 CLEAR 는 L3 FK 대조 전에는 믿지 않는다 |
| `dispense_while_dispatching` | `false` | 적재 위치로 이동하는 동안 첫 봉투 조제를 시작하고, 이동과 조제가 모두 끝난 뒤 적재한다 | 병원 카메라 배송 프로필에서 병행 조제를 시험할 때 `true` |
| `pick_notice` | `true` | `isaac_adapter` 가 적재 픽 `POUCH_PICKED` 를 `/isaac/pharmacy/pick_notice` 로 Isaac 에 알려 벨트 끝 봉투를 치우게 한다 | 진짜 UR5 가 Isaac 에서 봉투를 집는 구성에서 `false` |
| `belt_observation` | `false` | `isaac_adapter` 가 `/isaac/pharmacy/belt_observation`(JSON)을 `/pharmacy/belt/observation`(`BeltObservation`, 계약 11.6)으로 옮긴다 | 스테이지를 `--belt-observation` 으로 띄울 때 `true`. 기존 `/pharmacy/belt` 는 그대로 |
| `sim_pouches` | `false` | `isaac_adapter` 가 `/isaac/amr_1/pouches`(JSON)를 `/amr_1/sim/pouches`(`PouchDetectionArray`)로 옮긴다. **계약 토픽 `hand_camera/pouches` 에는 내지 않는다**(작성자는 perception 하나) | 시뮬 봉투 센서를 쓸 때 `true`. `pouch_source:=sim` 과 한 묶음 |
| `sim_tag_reads` | `false` | 같은 길로 `/isaac/amr_1/tag_reads` → `/amr_1/sim/tag_reads`(`TagRead`) | 시뮬 인식표 센서를 쓸 때 `true`. `scan_tag_source:=sim` 과 한 묶음 |
| `sim_cabinet` | `false` | `isaac_adapter` 가 `/isaac/evaluator/cabinet`(JSON)을 `/evaluator/cabinet`(`CabinetObservation`, L 50)으로 옮긴다(K5b). **계약 토픽 그대로 낸다** — 그 작성자는 isaac 이다(계약 46줄) | 스테이지가 보관함 참값을 낼 때 `true`. `stub_sim` 의 `publish_cabinet` 과 **같이 켜지 않는다**(작성자 둘). 어긋나면 기동 전에 멈춘다 |
| `pouch_source` | `camera` | UR5 팔이 봉투 검출을 어디서 보나(`camera` = 계약 토픽, `sim` = 위 릴레이) | **이 인자가 `ur5_arm_params_file` 보다 우선한다**(묶음을 launch 가 판정하기 위해서다) |
| `scan_tag_source` | `camera` | UR5 팔이 인식표를 어디서 보나 | 위와 같다 |
| `deck_pick_from_frame` | `false` | 상판 칸에서 집을 때 검출 대신 칸 TF 로 파지 자세를 만든다(K5) | `pouch_source:=sim` 과 **같이 켜지 않는다**(검출을 조용히 무시한다). 어긋나면 기동 전에 멈춘다 |
| `gripper_command_seq` | `false` | `isaac_adapter` 가 `/isaac/amr_1/gripper/state` → `/amr_1/gripper/state`(`GripperState`), `/amr_1/gripper/command_seq`(`GripperCommand`) → `/isaac/amr_1/gripper/command_seq` 를 옮긴다(계약 11.6) | 스테이지를 `--gripper-command-seq` 로 띄울 때 `true`. 기존 Bool `gripper/command`·`holding` 은 다루지 않는다 |
| `use_pouch_detector` | `false` | 실물 `pouch_detector` 를 띄운다. color 검출과 QR 을 쓴다. `hand_camera/tag_reads`·`pouches` 를 카메라 이미지에서 낸다 | `use_stub_detector` 와 **같이 켜지 않는다**. 켜면 계약 2.4 작성자가 둘이다. 어긋나면 기동 전에 멈춘다. v1.1.0 병원 기본은 켬(`P3_CAMERA_POUCHES=1`, #796·#797) |
| `vision_check` | `false` | UR5 팔의 비전 교차 확인. `pouch_source:=sim` 으로 상판에서 집을 때 접근 자세에서 `hand_camera/pouches` 를 1 s 기다려 참값과 0.05 m 안이면 검출 좌표로 집는다 | `use_pouch_detector:=true` 와 같이 준다(`P3_DECK_VISION=1`) |
| `detector_max_rate_hz` | `0.0` | `pouch_detector`·`m0609_detector` 의 추론 주기 상한(Hz). 0 이면 상한 없음 | `P3_DECK_VISION=1` 이 5.0 을 준다 |
| `detector_save_reads_dir` | 빈 값 | `pouch_detector` 가 상판 집기 뒤 손 카메라 프레임(초마다 한 장)을 남길 디렉토리 | 비우면 안 남긴다 |
| `use_m0609_detector` | `false` | M0609 손 카메라 QR 판독(`pouch_detector`, `robot_id=m0609`, `detector=none`). `/m0609/hand_camera/tag_reads` 를 낸다 | 보충 전 약통 확인(QR·DB·카메라 계약 2.3). 스테이지 `--m0609-hand-camera` 와 같이 쓴다. 병원 기본 켬(`P3_CONTAINER_QR=1`) |
| `m0609_save_reads_dir` | 빈 값 | `m0609_detector` 가 약통 QR 을 읽은 순간 영상 한 장을 남길 디렉토리 | `demo_v2.sh` 는 `P3_CONTAINER_QR=1` 이면 `<기동시각>-qr-reads/` 를 준다 |
| `pharmacy_db` | `false` | orchestrator 가 약 DB 를 열고 `/orchestrator/check_container` 를 낸다 | 팔 `container_check` 와 같이 쓴다 |
| `dispense_timeout_s` | `2.0` | `isaac_adapter` 가 Isaac 의 `Dispense` 응답을 기다리는 시한(s, wall). 계약 7절 기본 | 병원은 스테이지 틱이 길어 2 s 안에 답이 안 왔다(9/23 거부 ×3). `demo_v2.sh` 병원 기본은 30(`P3_DISPENSE_TIMEOUT_S`) |
| `belt_view_frame` | `pharmacy/belt_end` | UR5 팔이 벨트 픽 전에 손 카메라로 내려다볼 프레임(+z 위) | `belt_view_standoff_m` 이 0 이면 안 쓴다 |
| `belt_view_standoff_m` | `0.0` | 벨트 관측 자세에서 카메라와 프레임 사이 거리(m). 0 이면 끈다(지금 동작) | `pouch_source:=camera` 일 때만 쓴다. **이 인자가 params 파일보다 앞선다.** 계약 2.1 손 카메라 토픽은 그대로다. 그 토픽을 보기 전에 팔만 옮긴다 |
| `belt_view_offset_m` | `0.0` | 벨트 관측점을 `belt_view_frame` 의 x(진행 방향)로 옮긴다(m). 음수 = 상류 | 봉투는 끝 구역에 멈추므로 끝 구역 가운데를 볼 때 쓴다 |
| `detector_pouch_width_m` | `0.0` | `pouch_detector` 의 봉투 실제 폭(m). 거리 추정에 쓴다 | 현장값. 0 이면 안 쓴다 |
| `detector_pouch_distance_m` | `0.0` | `pouch_detector` 의 카메라-봉투 고정 거리(m) | 현장값. 폭·거리가 둘 다 0 이면 검출 자세가 0 이라 팔이 그 검출로 집지 않는다 |

이 표는 `launch/stub_loop.launch.py` 의 `DeclareLaunchArgument` 45개와 이름·기본값이 1:1 이다(v1.1.0 기준). `test_skeleton` 이 이름·기본값을 확인한다(#91).

`/clock` 작성자는 하나다(계약 4절). 기본값에서는 `stub_sim` 이 `/clock` 을 만들고, 그래서 `stub_sim` 만 `use_sim_time` 을 쓰지 않는다.
브릿지가 `/clock` 을 내는 구성에서는 `publish_clock:=false` 를 준다. `stub_sim` 은 `/clock` 을 내지 않고
`use_sim_time=true` 로 브릿지 시계를 따라 `belt`·`cabinet`·이벤트 stamp 를 찍는다. 벨트 이동 시간은 그대로 wall 이다.

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py publish_clock:=false
```

마스터에서 run 을 남길 때는 `run_host` 로 호스트 칸을 정한다. run 디렉토리 이름이 `<UTC>-master02-<hex>` 가 된다([evidence](../../evidence/README.md) run ID 규칙).

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py run_host:=master02
```

protocol `pharmacy-lap-pilot-v1`(조제실 구간 한 바퀴)은 `pharmacy_only:=true` 로 띄운다. 보충을 관측하려면 활성 슬롯 count 1, 다른 슬롯 0 같은 재고 파일을
`dispenser_file` 로 준다(파일은 run 의 config fingerprint 로 남긴다). 시행마다 `/orchestrator/reset` 을 부르고 새 epoch 의 트립을 센다.

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py pharmacy_only:=true dispenser_file:=/path/dispenser_refill.yaml run_host:=master02
ros2 service call /orchestrator/reset rokey_p3_interfaces/srv/Reset "{epoch: 2}"
```

### 대표 조합

① 전부 스텁 한 바퀴(노트북 docker, CI 의 L2 와 같은 조합)

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py
```

② master02 Isaac 보충 장면. Isaac `sim/standalone/m0609_refill_stage.py --mode ros` 가 `/clock`·`/m0609/joint_states`·`/m0609/gripper/holding` 을 내고,
실물 `m0609_arm` 이 그 장면을 움직인다. 조제기·벨트·AMR·UR5 는 아직 스텁이다. 두 명령은 같은 `ROS_DOMAIN_ID` 에서 띄운다.

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py publish_clock:=false use_stub_m0609:=false emulate_m0609:=false \
  pharmacy_only:=true dispenser_file:=/path/dispenser_refill.yaml run_host:=master02
ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true
```

③ Isaac 조제실 스테이지(`sim/standalone/pharmacy_stage.py --mode ros`)가 조제기·벨트·리셋을 JSON 토픽으로 맡는 조합(아래 "Isaac 어댑터").
스테이지가 `/clock`·`/m0609/joint_states`·`/m0609/gripper/holding` 도 내므로 `publish_clock:=false emulate_m0609:=false` 를 같이 준다.
9/17 master02(도메인 117)에서 이 조합으로 두 바퀴를 돌렸다(PR #108 본문).

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=true \
  publish_clock:=false emulate_m0609:=false order_pool_file:=/abs/order_pool.yaml run_host:=master02
```

④ 실물 UR5 팔이 Isaac 에서 봉투를 집는 조합(카드 K4).
지금은 `tools/demo_v2.sh` 의 한 바퀴 월드(emptyworld·hospital)가 이 묶음으로 띄운다(`stack_cmd`). v1.0.0 회전 7(`9760d9d`, #777·#778)도 이 구성이다.
아래는 받침대 UR5 조제실 스테이지로 띄울 때의 명령이다. 스테이지는 `--ur5` 와 함께 `--ros-pick-stand-in-s 0` 을 같이 줘야 뜬다(#244).

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true \
  use_ur5_arm:=true use_stub_arm:=false pick_notice:=false \
  ur5_arm_params_file:=/abs/ur5_arm.yaml publish_clock:=false emulate_m0609:=false
```

네 인자는 한 묶음이다. 하나라도 어긋나면 launch 가 노드를 하나도 띄우지 않고 멈춘다.
스텁 팔이 같이 살면 `PickPouch`·`ScanTag` 서버가 둘이 되고, `pick_notice` 가 켜져 있으면
실물 팔이 집기 전에 Isaac 이 봉투를 치운다(`--ur5` 스테이지는 `pick_notice` 를 세기만 한다).

> **상태: 지난 기록 (2026-09-21 기준).** 아래 YAML 은 그날의 뼈대다. 지금 쓰는 값은 [`rokey_p3_manipulation/config/`](../rokey_p3_manipulation/config/) 의 `ur5_arm.amr-combined*.yaml` 넷이다.
> v1.1.0 병원 카메라 기본은 `ur5_arm.amr-combined.camera-receiver.yaml` 이다(#796, `tools/demo_v2.sh`).

`ur5_arm_params_file` 뼈대(2026-09-21). **채워진 값은 코드·계약에서 나온 것이고,
빈 값은 아직 재지 않은 것이다. 지어낸 값은 없다.**

```yaml
arm:
  ros__parameters:
    # 켜야 하는 것: Isaac 은 deck_slot_1..N, PickPouch.target_slot 은 0 부터다
    deck_slot_frame_base: 1

    # 비우면 {robot_id}/ur_arm_base_link 로 채워진다(결정 47). amr_1/base_link 가 **아니다** —
    # 그 이름은 이동 베이스의 프레임이고 부모가 odom, 작성자가 base_driver 다. 같은 이름을 쓰면
    # 한 child 에 부모가 둘이 된다. 팔의 모든 TF 조회(deck_slot_*·<zone>/cabinet·검출 자세·
    # <zone>/tag)가 이 하나를 쓴다. 시뮬 센서 JSON 의 frame_id 도 같은 값이어야 한다.
    # 스테이지의 --ur5-base-frame 과 **같은 값이어야 한다.** 지금은 양쪽 기본값이 둘 다 결정 47 을
    # 보고 있어 같지만, 한쪽만 바꾸면 팔이 없는 프레임을 조회한다(출처가 하나가 아니다).
    arm_base_frame: ''

    # v0 에서는 비워 둔다. arm_node 가 이 값을 쓰는 곳은 placement_check 와 tag_standoff
    # 뿐이고 v0 는 둘 다 끈다. 집기 경로는 이 프레임을 쓰지 않는다(base 좌표 + 자체 IK).
    # 켤 때 주의: /tf 에 나가는 끝단 프레임은 amr_1/flange 다(Isaac 5.1 ur5.usd 에 tool0
    # prim 이 없다). flange 는 tool0 과 원점은 같고 회전이 다르다. arm_node 는 tool0 규약을
    # 가정하므로 그 회전을 넣지 않으면 조용히 돌아간 자세로 간다.
    # 기동 로그의 `ur5 end_link=… end_to_tool=…` 줄을 먼저 본다.
    tool_frame: ''

    # 0 이 맞다(미측정이 아니다). tool0 아래에 툴·컵 prim 이 없고 --ur5-tcp-offset 기본이
    # 0 이라, 방송되는 프레임의 원점이 곧 스테이지가 보는 흡착면이다. 오프셋을 더하면
    # 스테이지와 어긋난다. 흡착 툴을 장면에 넣기로 하면 이 값도 바뀐다(재범 결정).
    grasp_z_offset_m: 0.0

    # 0.015 확정(시뮬 확인 2026-09-21, 미측정 아님). 놓을 곳 프레임 원점에 z 로 더해
    # TCP 목표를 만든다(arm_node 의 _run_pick, kin.top_down_pose(place_target + [0,0,offset])).
    # deck_slot_* 프레임 원점은 칸 바닥의 윗면
    # (봉투가 얹히는 면)이다 — 결정 23, p3sim/layout.py 의 deck_slot_frames.
    # selfdemo 의 놓기 높이 = slot_floor + rest_gap(0.005) + pouch_height(0.010) 이고
    # slot_floor 가 프레임 원점과 같은 값이라 오프셋이 0.015 다. 이 값이면 ROS 경로가
    # selfdemo(실습12 안착 5/5)와 같은 높이에 놓는다.
    # 단서: pouch_height 는 --pouch-size 의 z 다. 봉투 두께를 바꾸면 이 값도 바뀐다.
    #       rest_gap 0.005 는 우리가 고른 여유이고 계약 값이 아니다.
    place_z_offset_m: 0.015

    # 여기만 미측정이다. 첫 회차에서 잰다.
    # 빈 목록이면 노드가 기동을 거부한다(의도된 것). 길이가 6 이 아니면 ValueError 다.
    # 값을 채우거나 이 키를 지운다. 키를 지우면 기본값 [0.0]*6 으로 뜨는데, 기동 때는
    # 팔이 움직이지 않지만 첫 픽이 끝난 뒤 홈으로 가며 팔을 수평으로 다 편다
    # (start_homing 은 PickPouch goal 이 끝난 뒤에 불린다).
    home_joint_positions: []
```

- K4 의 L3 에서 `in_slot=True` 가 안 나오면 **`place_z_offset_m` 부터 본다.** selfdemo 와 ROS 경로의
  놓는 높이를 맞추는 값이다.
- **위험한 자리는 기동이 아니라 첫 픽 뒤다.** 기본값 `[0.0]*6` 으로 띄우면 기동 때는 팔이 움직이지
  않는다. `start_homing` 은 `PickPouch` goal 이 끝난 뒤에 불리고, 그때 팔을 수평으로 다 편 자세로
  가며 조제기·벽에 닿을 수 있다. **값을 채우기 전에는 픽을 한 번도 끝내지 않는다.**
  - 재는 법: **팔 노드 없이 스테이지만 띄워** `/amr_1/joint_states` 를 한 번 받는다(30 Hz, `--mode ros`
    면 UR5 6축 포함). 스테이지가 내는 토픽이라 팔 노드와 무관하다. `ready` 에 선 순간의 값을 적는다.
  - 시뮬이 계산한 값은 쓰지 않는다. DH 와 Lula 가 다른 가지를 고르는 것이 관측됐다.
    계산값은 "시뮬이 간 자세" 가 아니라 "우리 모형이 고른 자세" 다(판단).
- `robot_id`(기본 `amr_1`)에서 파생되는 프레임 이름들은 기본값이 이미 맞아 적지 않아도 된다.
- `cabinet_frame` 은 보관함 전달(K5) 값이라 이 조합에는 필요 없다.
- `placement_check_enabled`·`arm_clearance_enabled` 는 기본 꺼짐으로 둔다(L3 미실행).

M0609 를 누가 움직이느냐에 따라 `use_stub_m0609` 가 갈린다. 9/17 master02 관측: 기본값이면 `/m0609/arm/at_home` 은 `stub_arm`, 관절·파지는 Isaac 이 내서 둘이 섞인다.
- Isaac 이 보충을 혼자 돌리는 시연(`pharmacy_stage.py --ros-refill-selfdemo`): `use_stub_m0609` 기본값(`true`). 오케스트레이터가 M0609 를 구동하지 않아 섞여도 무해하다.
- 오케스트레이터가 Isaac M0609 를 구동: `use_stub_m0609:=false emulate_m0609:=false` 에 실물 `m0609_arm` 을 같이 띄운다. 스테이지에 맞는 모드로 띄운다.
  자세한 것은 [manipulation README](../rokey_p3_manipulation/README.md) 의 M0609 절.

  | 스테이지 | `m0609_arm` | 무엇 |
  | --- | --- | --- |
  | `m0609_refill_stage.py --mode ros`(고정 받침) | `-p use_sim_time:=true`(+ teach 한 waypoint 파라미터 파일) | teach 자세만 따라간다 |
  | `pharmacy_stage.py --preset demo-ros-refill`(레일 2축) | `-p use_sim_time:=true -p rail_enabled:=true` | 팔이 접힌 자세일 때만 레일을 옮기고, 레일이 닿은 뒤 팔이 움직인다(#154·#165) |
  | `pharmacy_stage.py --preset demo-ros-refill-v2`(레일 3축, 선반 16칸) | `-p use_sim_time:=true -p scene_version:=2 -p v2_seed:=7` | 스테이지의 `/m0609/shelf/inventory` 로 칸·수납·장애물을 받아 실행 중 IK 로 계획한다(#177·#186). 기동 뒤 `v2 계획 캐시: 16/16칸 풀림` 줄을 기다린다 |

## v1.1.0 병원 한 바퀴의 stack 인자

`P3_WORLD=hospital P3_SIM_SENSORS=1 tools/demo_v2.sh cmds` 가 v1.1.0 트리(`f316197`)에서 내는 stack 줄이다.
2026-09-30 에 이 저장소에서 `cmds` 로 뽑았다(띄우지는 않았다). `<…>` 는 환경 변수·경로 자리다.

```bash
ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=false \
  use_stub_sim:=false publish_cabinet:=false deck_slots:=3 \
  use_stub_fleet:=false use_stub_arm:=false pick_notice:=false use_ur5_arm:=true \
  ur5_arm_params_file:=<repo>/src/rokey_p3_manipulation/config/ur5_arm.amr-combined.camera-receiver.yaml \
  scan_tag_source:=camera sim_cabinet:=true \
  use_stub_detector:=false use_pouch_detector:=true pouch_source:=camera \
  belt_view_standoff_m:=0.30 belt_view_offset_m:=0 detector_pouch_distance_m:=0.290 \
  use_order_generator:=false belt_timeout_s:=60 dispense_timeout_s:=30 dispense_while_dispatching:=true \
  use_m0609_detector:=true pharmacy_db:=true m0609_save_reads_dir:=<P3_LOG_DIR>/<기동시각>-qr-reads \
  publish_clock:=false emulate_m0609:=false use_stub_m0609:=false dispenser_file:=<P3_DISPENSER_FILE> \
  order_pool_file:=<repo>/src/rokey_p3_orchestrator/config/order_pool.hospital.yaml run_host:=<호스트> \
  zones_file:=<repo>/src/rokey_p3_description/config/zones.hospital-receiver.yaml
```

- 뜨는 노드는 `orchestrator`·`event_logger`·`isaac_adapter`·`arm`·`pouch_detector`·`m0609_detector` 여섯이다.
- 봉투와 인식표는 손 카메라 QR 로 읽는다(`pouch_source:=camera`, `scan_tag_source:=camera`, #784).
- 보관함 참값(`/evaluator/cabinet`)은 Isaac 이 낸다(`sim_cabinet:=true`). run 기록의 `SUCCESS` 근거다(계약 8절).
- `zones.hospital-receiver.yaml` 에서 `load` 와 `dock_1` 이 같은 자리다. orchestrator 는 이때 도크에서 이동 없이 적재한다(`load_at_dock`, #790).
- `dispense_while_dispatching:=true` 면 적재 자리로 가는 동안 첫 봉투 조제를 시작한다.
- M0609 팔(`m0609_arm`)과 주행(`navigation.launch.py`)은 이 launch 밖에서 따로 뜬다([src README](../README.md#v110-병원-한-바퀴에서-뜨는-노드)).

## Isaac 어댑터

Isaac Sim 5.1 안의 Python(3.11)은 `rokey_p3_interfaces` 를 import 하지 못한다. 조제실 스테이지는 `std_msgs/String` JSON 토픽만 내고,
`isaac_adapter` 가 계약 이름·타입으로 바꾼다. 형식의 기준은 [sim/README](../../sim/README.md) "Isaac ↔ ROS 어댑터 인터페이스 (JSON, v1)" 표다.

| 계약 쪽(어댑터가 제공) | Isaac 쪽 JSON 토픽 |
| --- | --- |
| `/pharmacy/dispense`(srv `Dispense`) | `/isaac/pharmacy/dispense_request` → `/isaac/pharmacy/dispense_response` |
| `/sim/reset`(srv `Reset`) | `/isaac/sim/reset_request` → `/isaac/sim/reset_response` |
| `/pharmacy/belt`(`BeltState`, H) | `/isaac/pharmacy/belt` |
| `/events`(`Event`, L 500) | `/isaac/events`(`DISPENSED`·`POUCH_AT_END`) |
| `/events` 의 적재 픽 `POUCH_PICKED`(읽기) | `/isaac/pharmacy/pick_notice`(어댑터 → Isaac) |
| `/pharmacy/belt/observation`(`BeltObservation`, H), `belt_observation` 켤 때만 | `/isaac/pharmacy/belt_observation` |
| `/amr_1/gripper/state`(`GripperState`, H), `gripper_command_seq` 켤 때만 | `/isaac/amr_1/gripper/state` |
| `/amr_1/gripper/command_seq`(`GripperCommand`, R, 읽기), `gripper_command_seq` 켤 때만 | `/isaac/amr_1/gripper/command_seq`(어댑터 → Isaac) |

- 응답 시한은 어댑터가 wall 로 잰다(파라미터 `dispense_timeout_s` 2.0, `reset_timeout_s` 30.0, 계약 7절). Isaac 구독자가 안 보이는 시간도 들어간다.
  넘으면 `Dispense` 는 `accepted=false`·`not_ready`, `Reset` 은 `ok=false`(`message` 는 `isaac_adapter: …`)로 답하고 로그 한 줄을 남긴다.
- 응답은 `Dispense` 는 (`request_id`, `order_id`), `Reset` 은 `epoch` 로 기다리는 요청에 맞춘다(#247). 기다리는 요청이 없는 응답(`order_id` 가 다른 응답 포함)은 버리고 시한까지 기다린다.
  JSON 형식 오류(필드 빠짐·정의 밖 필드·`v` 가 1 이 아님·타입)는 버리고 로그 한 줄. `request_id` 가 빈 `Dispense` 는 Isaac 에 보내지 않고 거부한다.
  거부 message 가 계약 2.1 의 네 값(`belt_occupied`·`unknown_order`·`not_ready`·`pool_exhausted`) 밖이면 그대로 넘긴다. warn 한다. orchestrator 는 message 와 상관없이 같은 거부로 본다.
- `stamp` 는 JSON 의 sim time 을 `header.stamp` 로 옮긴다. epoch 0(Isaac 이 고치기 전 기동값)은 방어로 어댑터가 `/events` 에서 본 epoch(시작 1)로 바꾸고 warn 한다.
- `/isaac/pharmacy/belt` 의 epoch 가 어댑터의 현재 epoch 보다 작으면 버린다. `BeltState` 에 epoch 칸이 없어 계약 4절 "이전 epoch BeltState 버림"을 어댑터가 대신 지킨다.
- `belt_observation`(파라미터·launch 인자, 기본 false): 형식 오류, epoch 0, 지금 epoch 나 이미 옮긴 관측의 epoch 보다 이전 epoch, 같은 epoch 안의 seq 역행은 버리고
  `dropped` 에 센다(`observation_malformed`·`observation_bad_epoch`·`observation_stale_epoch`·`observation_seq_regression`).
  epoch 0 은 기존 belt 처럼 현재 epoch 로 바꾸지 않는다(계약 11.6: epoch 를 추측하지 않는다). 같은 seq 의 반복은 옮긴다.
- `gripper_command_seq`(파라미터·launch 인자, 기본 false): `GripperState` 는 위와 같은 규칙으로 버리고 센다(`gripper_state_*`).
  `GripperCommand` 는 epoch 0·지금 epoch 보다 이전 epoch 만 버리고 센다(`gripper_command_*`). seq 멱등은 Isaac 이 한다.
- `/isaac/events` 는 transient local 이라 다시 뜨면 지난 이벤트가 또 온다. (epoch, name, stamp, order_id, request_id) 가 이미 옮긴 것이면 버린다.
- `pick_notice`(파라미터·launch 인자, 기본 true): 스텁 팔은 봉투를 실제로 집지 않아 Isaac 벨트에 봉투가 남는다. `/events` 의 `POUCH_PICKED` 중 `robot_id` 가 `amr_*` 이고,
  epoch 가 현재 epoch 이고, 마지막으로 옮긴 belt 가 `at_end` 이며 그 `order_id` 와 같을 때만(적재 픽) 그 stamp·epoch·`order_id` 로 알린다. 같은 (epoch, `order_id`)로는 한 번.
  꺼져 있으면 첫 봉투가 벨트에 남고, orchestrator 는 벨트가 비지 않으면 `Dispense` 를 부르지 않아 같은 epoch 의 두 번째 트립이 적재 위치에서 기다린다.
- Isaac 이 안 보이면 알린다. `/isaac/pharmacy/dispense_request`·`/isaac/sim/reset_request` 구독자가 0 이고 `/isaac/pharmacy/belt` 를
  `isaac_missing_after_s`(5.0 s, wall) 넘게 못 받았으면 `isaac_missing_warn_every_s`(10.0 s)마다 WARN "Isaac 스테이지가 안 보인다(…)", 다시 보이면 INFO 한 줄.
  orchestrator 는 벨트가 unknown 이면 배출을 조용히 기다리므로 스테이지를 안 띄웠거나 도메인이 다를 때 이 줄이 원인을 보인다. launch 는 Isaac 을 기다리지 않는다.
- `stub_sim` 의 나머지(`/clock`, `/amr_1/gripper/holding`, `/evaluator/cabinet`, M0609 흉내)는 그대로 켜져 있다.
  `/sim/reset` 을 어댑터가 맡으면 `stub_sim` 은 새 epoch 의 `RESET_DONE` 을 보고 자기 씬 상태를 같은 규칙으로 비운다.

## 스텁이 지키는 것과 흉내 내는 것

지키는 것은 계약이다. 이름·타입·QoS·인터락이 실물과 같다.

- `stub_fleet` 은 `arm/at_home` 이 true 가 아니거나 1.0 s 보다 오래됐으면 `GoToZone` goal 을 거부한다.
  `GoToZone` result 에는 실패 이유 칸이 없어서 거부가 유일한 신호다.
- `stub_arm` 은 `base/stopped` 가 true 가 아니면, `source=BELT` 인데 벨트 끝에 그 주문의 봉투가
  없으면 픽을 하지 않는다. 다만 **goal 을 받은 뒤 abort 하고 `outcome=rejected_interlock`** 을 낸다.
  계약 5절은 "REJECT" 라고 쓰지만 ROS 2 는 거부한 goal 에 result 를 못 싣고, 계약 2.3절이
  `rejected_interlock` 을 outcome 목록에 두고 있다. 실물 arm 도 같은 선택이다.
  `ScanTag` 는 result 에 outcome 이 없어서 `status=UNREADABLE` 로 닫는다.
  goal 거부는 실물 `arm`·`m0609_arm` 과 같은 순서다. 형식 오류(`order_id`·`zone_id` 없음, 모르는 `source`, Refill 의 item_id·slot),
  이미 활성 goal 이 있음(UR5 는 `PickPouch`·`ScanTag` 가 하나를 나눠 쓰고 M0609 `Refill` 은 따로),
  리셋 barrier 중(`RESET_BEGIN` 뒤 같은 epoch 의 `RESET_DONE` 전, 계약 6절 0). barrier 판정은 실물과 같은 `ResetFence` 다.
- `stub_arm` 은 액션 결과를 먼저 돌려주고 홈 복귀를 그 뒤에 끝낸다. 그래서 `ARM_HOME` 이
  `LOAD_DONE`·`ORDER_DONE` 뒤에 온다. 계약 2.6절의 순서가 그것이다.
- `stub_arm` 은 `/m0609/refill` 을 맡을 때(`serve_refill`) 실물 `m0609_arm` 처럼 `/m0609/arm/at_home` 을 5 Hz(H)로 낸다.
  결과·홈 순서는 실물 #99 와 같다(UR5 스텁 규칙과 다르다). 성공은 `motion_s` 뒤 `REFILL_DONE`, `home_s` 동안 홈으로 간 **뒤** 결과를 내므로 결과를 받을 때 true 다.
  취소는 결과(canceled)를 먼저 내고 `home_s` 뒤 true(스텁은 `motion_s` 끝에서 취소를 본다). 스텁 `Refill` 에는 실패 경로가 없다.
  결과 전 홈 복귀 도중 `RESET_BEGIN` 이 오거나 barrier 안에서 `Refill` 이 끝나면 홈에 닿지 않은 채 결과를 내고,
  같은 epoch 의 `RESET_DONE` 을 처음 받으면 `home_s` 뒤 홈에 닿는다(실물 `on_reset_begin`·`on_reset` 과 같다).
  결과 `lot_id` 는 지어내지 않는다. goal 에 lot 이 없으면 빈 값이고 `REFILL_DONE` detail 에 ` lot …` 이 붙지 않는다(실물 #99 와 같다).
  `serve_refill=false`(`use_stub_m0609:=false`)면 이 토픽을 내지 않는다. 작성자는 실물 하나다. `stub_sim` 은 M0609 를 흉내 내도 이 토픽을 내지 않는다.
  실물은 `/sim/reset` 이 관절을 홈으로 옮기면 `RESET_DONE` 전에도 true 가 될 수 있다. 스텁은 관절을 모르므로 `RESET_DONE` 을 기다린다.

흉내 내는 것은 물리와 시각이다. 스텁은 볼 수 없어서 주문 풀 파일과 `/events` 로 대신한다.

- `stub_sim` 은 `POUCH_PLACED` 를 보고 그 주문의 침상 보관함에서 봉투를 관측한 것으로
  `/evaluator/cabinet` 을 낸다. 어느 보관함인지는 주문 풀의 `bed` 로 안다.
- `stub_detector` 는 `POUCH_LOADED` 로 상판 봉투를 세고, `ARRIVED` 로 인식표를 보고,
  `AUTH_OK` 뒤부터 봉투를 검출한 것으로 본다.
- `stub_sim` 은 `/clock` 을 되감지 않는다. 리셋 때 씬 상태만 지운다. sim time 되감기는 Isaac 것이고 L3 에서 본다.
- `stub_sim` 은 브릿지가 M0609 를 아직 안 낼 때 `m0609_arm` 의 닫힌 루프를 닫는다(노드 파라미터 `emulate_m0609`, 기본 `true`).
  - `/m0609/joint_states` 를 S 30 Hz 로 낸다. 시작은 전부 0(홈)이고, `/m0609/arm/joint_command` 의 position 을 다음 발행부터 그대로 되돌린다. 보간·지연·관절 한계가 없다.
  - `/m0609/gripper/holding` 을 H 10 Hz 로 낸다. `/m0609/gripper/command` 가 true 면 `m0609_settle_s`(기본 0.2 s) 뒤 true, false 면 바로 false 다. 캐니스터가 그 자리에 있는지는 보지 않는다.
  - 관절 이름은 `m0609_joint_names`(기본 `joint_1`-`joint_6`, `m0609_arm` 기본값과 같다). USD 의 실제 이름은 마스터에서 확인한다. 모르는 이름이 섞인 명령은 통째로 버린다.
  - `/sim/reset` 이면 관절 0, 그리퍼 열림(`holding` false). 계약 6절 2 가 M0609 홈·그리퍼·캐니스터를 isaac 리셋 범위에 둔다(PR `docs/contract-v1-reset-m0609-dispense` 기준).
    `m0609_reset_homes:=false`(기본 `true`)면 관절은 그대로 두고 그리퍼만 연다. `m0609_arm` 이 `RESET_DONE` 뒤 스스로 홈으로 가는 경로를 L2 에서 보기 위한 것이다.
  - 브릿지가 M0609 를 내면 `emulate_m0609:=false`. 안 그러면 `/m0609/joint_states` 작성자가 둘이 된다.

## 스텁 노드 파라미터

launch 인자로 올라가지 않은 것은 `ros2 run rokey_p3_bringup <스텁> --ros-args -p 이름:=값` 이나 테스트의 `parameter_overrides` 로 준다.
표는 각 스텁 파일과 `isaac_adapter` 의 `declare_parameter` 전부다.

| 노드 | 파라미터 | 기본값 | 무엇 | launch 가 넘기나 |
| --- | --- | --- | --- | --- |
| `stub_sim` | `order_pool_file` | 빈 값 | 주문 풀. 봉투가 어느 보관함 것인지 안다 | `order_pool_file` |
| `stub_sim` | `belt_travel_s` | `1.0` | `DISPENSED` 부터 `POUCH_AT_END` 까지(wall) | 아니오 |
| `stub_sim` | `clock_rate_hz` | `60.0` | `/clock` 발행 주기 | 아니오 |
| `stub_sim` | `publish_clock` | `true` | `/clock` 을 낸다. false 면 `use_sim_time` 으로 브릿지 시계를 따른다 | `publish_clock` |
| `stub_sim` | `emulate_m0609` | `true` | `/m0609/joint_states`·`/m0609/gripper/holding` 흉내 | `emulate_m0609` |
| `stub_sim` | `m0609_joint_names` | `joint_1`-`joint_6` | 흉내 내는 M0609 관절 이름 | 아니오 |
| `stub_sim` | `m0609_settle_s` | `0.2` | 그리퍼 닫기 명령에서 `holding` true 까지 | 아니오 |
| `stub_sim` | `m0609_reset_homes` | `true` | `/sim/reset` 때 M0609 관절을 0 으로. false 면 관절은 두고 그리퍼만 연다 | 아니오 |
| `stub_sim` | `reset_fail` | `false` | 검증용 실패 주입. true 면 씬을 건드리지 않고 `/sim/reset` 에 `ok=false` 로 답한다 | 아니오 |
| `stub_sim` | `reset_delay_s` | `0.0` | 검증용 실패 주입. `/sim/reset` 응답 전 wall 대기. orchestrator `reset_timeout_s`(기본 30 s)보다 길면 무응답과 같고, 응답은 결국 늦게 간다 | 아니오 |
| `stub_sim` | `publish_cabinet` | `true` | `/evaluator/cabinet`(`CabinetObservation`)을 낸다 | `publish_cabinet` |
| `stub_sim` | `serve_dispense` | `true` | `/pharmacy/dispense` 서버. false 면 `DISPENSED`·`POUCH_AT_END` 도 내지 않는다 | `use_isaac_adapter` 의 반대 |
| `stub_sim` | `serve_reset` | `true` | `/sim/reset` 서버. false 면 새 epoch 의 `RESET_DONE` 에 스텁 씬 상태를 비운다 | `use_isaac_adapter` 의 반대 |
| `stub_sim` | `publish_belt` | `true` | `/pharmacy/belt` 를 낸다 | `use_isaac_adapter` 의 반대 |
| `stub_arm` | `order_pool_file` | 빈 값 | 주문 풀. 인식표 QR 내용을 안다 | `order_pool_file` |
| `stub_arm` | `motion_s` | `0.3` | 픽 동작 한 단계(`PICK_ATTEMPT` 부터 `POUCH_PICKED`, 거기서 `POUCH_LOADED`·`POUCH_PLACED`)와 Refill 동작 시간 | 아니오 |
| `stub_arm` | `home_s` | `0.3` | 픽 결과를 돌려준 뒤 `ARM_HOME` 까지. Refill 은 결과 전 홈 복귀 시간(취소면 결과 뒤) | 아니오 |
| `stub_arm` | `detection_wait_s` | `5.0` | 상판(DECK) 픽에서 `pouches` 검출을 기다리는 시간 | 아니오 |
| `stub_arm` | `tag_wait_s` | `5.0` | `ScanTag` 에서 `tag_reads` 를 기다리는 시간 | 아니오 |
| `stub_arm` | `serve_refill` | `true` | `/m0609/refill` 서버를 열고 `/m0609/arm/at_home` 을 낸다 | `use_stub_m0609` |
| `stub_fleet` | `travel_s` | `1.0` | `GoToZone` 한 번의 주행 시간(wall) | 아니오 |
| `stub_fleet` | `start_distance_m` | `6.0` | feedback `distance_remaining` 의 시작값 | 아니오 |
| `stub_detector` | `order_pool_file` | 빈 값 | 주문 풀. 정거장 인식표를 안다 | `order_pool_file` |
| `stub_detector` | `rate_hz` | `5.0` | `tag_reads`·`pouches` 발행 주기 | 아니오 |
| `isaac_adapter` | `dispense_timeout_s` | `2.0` | `Dispense` 응답 시한(wall) | `dispense_timeout_s` |
| `isaac_adapter` | `reset_timeout_s` | `30.0` | `/sim/reset` 응답 시한(wall) | 아니오 |
| `isaac_adapter` | `pick_notice` | `true` | 적재 픽을 `/isaac/pharmacy/pick_notice` 로 알린다 | `pick_notice` |
| `isaac_adapter` | `belt_observation` | `false` | `BeltObservation` 변환(계약 11.6)을 켠다 | `belt_observation` |
| `isaac_adapter` | `gripper_command_seq` | `false` | `GripperState`·`GripperCommand` 변환(계약 11.6)을 켠다 | `gripper_command_seq` |
| `isaac_adapter` | `sim_pouches` | `false` | 시뮬 봉투 센서를 `/amr_1/sim/pouches` 로 옮긴다. **구독 QoS 는 H(reliable·volatile·depth 1)** — 스테이지가 best effort 로 내면 한 건도 못 받는다 | `sim_pouches` |
| `isaac_adapter` | `sim_tag_reads` | `false` | 시뮬 인식표 센서를 `/amr_1/sim/tag_reads` 로 옮긴다 | `sim_tag_reads` |
| `isaac_adapter` | `sim_cabinet` | `false` | `/isaac/evaluator/cabinet`(JSON)을 `/evaluator/cabinet` 으로 옮긴다(K5b) | `sim_cabinet` |
| `isaac_adapter` | `isaac_missing_after_s` | `5.0` | 요청 토픽 구독자 0 이고 belt 무소식이 이만큼(wall) 넘으면 Isaac 이 안 보인다고 본다 | 아니오 |
| `isaac_adapter` | `isaac_missing_warn_every_s` | `10.0` | 안 보이는 동안 WARN 간격(wall) | 아니오 |

모든 스텁은 launch 에서 `use_sim_time` 을 받는다(`stub_sim` 만 `publish_clock` 의 반대).
`reset_fail`·`reset_delay_s` 는 `/sim/reset` 마다 다시 읽으므로 `ros2 param set /stub_sim reset_fail true` 처럼 띄운 채로 켜고 끈다.

## 테스트

```bash
colcon test --packages-select rokey_p3_bringup
```

`test_*.py` 열여섯 파일 모두 `colcon test` 가 pytest 로 돈다(v1.1.0). `fake_isaac.py`·`l2_discovery.py`·`l2_teardown.py` 는 테스트가 쓰는 노드·도우미다(아래 "L2 테스트 구조").
루트 `tests/` 의 unittest 와는 따로다([tests/README](../../tests/README.md)).

### `test_skeleton.py` — launch 파일을 읽기만 한다

`launch_ros` 가 없으면 건너뛴다(`importorskip`). 노드를 띄우지 않는다.

- `test_skeleton_launch_lists_four_nodes` — `skeleton.launch.py` 가 노드 4개를 나열한다.
- `test_stub_loop_launch_declares_every_argument_with_its_default` — `stub_loop.launch.py` 의 `DeclareLaunchArgument` 45개의 이름과 기본값이 테스트의 `STUB_LOOP_ARGUMENTS` 와 같다.
  이름·기본값이 하나라도 더해지거나 빠지거나 바뀌면 실패한다. 인자를 고칠 때는 테스트의 `STUB_LOOP_ARGUMENTS` 와 인자 표를 같이 고친다.
- `test_stub_loop_launch_runs_the_three_orchestration_nodes_four_stubs_and_the_isaac_adapter` — `stub_loop.launch.py` 의 Node 가 11개다(`isaac_adapter`·`arm`·`pouch_detector`·`m0609_detector` 는 조건부).
- `test_stub_loop_warns_when_the_isaac_adapter_runs_with_stub_clock_or_m0609[…]` — `use_isaac_adapter:=true` 인데 `publish_clock`·`emulate_m0609` 중 하나라도 true 인 조합에만 경고 `LogInfo` 의 조건이 참이다(5가지).

### `test_stub_loop.py` — L2, 스텁 한 바퀴

`rclpy` 가 없으면 건너뛴다. 한 프로세스에서 노드 일곱(스텁 넷, `orchestrator`·`order_generator`·`event_logger`)을 띄워 요청 1건을 돌린다.
네 케이스가 그 한 바퀴를 같이 쓴다.

- `test_deliver_result_is_success` — `Deliver` 결과 `success=true`, 주문 `ord-0001` 이 `DELIVERED`.
- `test_event_order_matches_the_contract` — `events.jsonl` 의 이름 순서가 계약 2.6절 1인 배송 한 바퀴와 같고, stale 이 없고 epoch 가 1 뿐이다.
- `test_run_record_writes_success_from_the_evaluator_observation` — `orders.jsonl` 이 주장 `DELIVERED`, 관측 있음, `bed_a1/cabinet`, 판정 `SUCCESS`.
- `test_cabinet_observation_is_recorded` — `cabinet.jsonl` 의 관측이 모두 `ord-0001`, `present=true`.

### `test_m0609_loop.py` — L2, M0609 닫힌 루프

건너뛰지 않는다. `stub_sim`(M0609 흉내)과 실물 `m0609_arm`(`open_loop=false`, 0 이 아닌 waypoint)을 한 프로세스에서 띄운다.

- `test_refill_succeeds_on_the_loop_closed_by_stub_sim` — `Refill` 이 SUCCEEDED·`success=true`·`lot_id` 빈 값, `REFILL_DONE`(m0609) 1건, `joint_states` 가 waypoint(0.65 rad)까지 간다.
- `test_without_emulation_the_same_refill_fails` — `emulate_m0609=false` 면 `joint_states` 가 없어서 같은 goal 이 ABORTED 이고 `REFILL_DONE` 이 없다.
- `test_arm_homes_itself_after_reset_when_the_sim_does_not` — goal 도중 cancel 하고, 이어진 복귀를 끊어 홈 밖에서 멈춘 상태를 만든다.
  그 뒤 `/sim/reset`(e2)(`m0609_reset_homes=false` 라 관절이 그대로), `RESET_DONE`(e2). `m0609_arm` 이 스스로 홈으로 가 `at_home` true 가 된다.
- `test_reset_begin_fences_m0609_commands_until_reset_done` — 울타리(계약 6절 0). cancel 뒤 복귀 명령이 나가는 중에 실물 `orchestrator` 의 `/orchestrator/reset`(e2) 로 리셋한다.
  `RESET_BEGIN` 은 orchestrator 가 내고, `stub_sim` `reset_delay_s` 1 s 로 울타리를 1 s 넘게 닫아 둔다.
  울타리 구간의 `/m0609/arm/joint_command`·`/m0609/gripper/command` 가 0건이고, 그동안 관절이 홈 밖에 머물며, `RESET_DONE` 뒤 복귀해 홈에 닿는다.
  joint_command 구간은 `header.stamp`(sim time)가 울타리 확인 뒤인 것부터, 울타리가 열리기 전에 받은 것까지다(sim 시계 60 Hz 라 끝은 받은 시각으로 자른다).
- `test_reset_begin_fences_m0609_gripper_right_after_grasp` — grasp 의 `gripper/command` true 직후 같은 경로로 리셋한다(`reset_delay_s` 4 s).
  울타리 구간 명령 0건, `Refill` ABORTED·`success=false`, `REFILL_DONE` 없음.

### `test_reset_barrier_loop.py` — L2, 리셋 barrier v2(계약 6절)

`test_stub_loop` 와 같은 한 바퀴(스텁 넷, 실물 `orchestrator`·`order_generator`·`event_logger`)에서 리셋을 건다. 스텁을 감싼 하위 클래스가 goal 시작·종결과 `/sim/reset` 호출 시각을 기록한다. 스텁 동작은 바꾸지 않는다.
집계기와 protocol 을 저장소 루트에서 읽으므로 저장소 전체 checkout 에서 돈다.

- `test_reset_barrier_cancel_races[pick|drive|return]` — 벨트 픽·침상 주행·복귀 주행 도중 리셋.
  `/sim/reset` 이 끊긴 goal 의 종결보다 먼저 불리지 않고, 끊긴 주문의 `ORDER_DONE` 이 이전 run 에 `RESET_BEGIN` 과 같은 stamp 로 남고, 새 run 은 `r002-0001` `SUCCESS` 하나다.
- `test_pharmacy_reset_three_laps` — `pharmacy_only` 로 (리셋, 트립)×3. epoch 2·3·4 run 마다 `RESET_BEGIN` 시작, epoch 섞임·stale 없음, 첫 요청 수락, 집계기 `lap_success 1`.
- `test_reset_failure_stops_and_a_new_reset_recovers[fail|hang]` — `reset_fail` 또는 `reset_delay_s` 4 s(시한 2 s). 실패 epoch 에 `RESET_DONE` 없음, `Deliver` 거부, 그 run 에 관측만으로 `SUCCESS` 없음. 새 리셋으로 다음 트립이 끝난다.
- 회귀 셋:
  - `test_generator_sends_after_a_reset_that_interrupted_a_trip` — 트립을 끊은 리셋 뒤에도 발행기가 새 epoch 요청을 보낸다(#84).
  - `test_interrupted_order_is_closed_in_the_previous_epoch_run` — 주행 중 리셋으로 끊긴 주문의 `ABORT`(`reset_interrupted`)가 이전 run 에만 있다(#87).
  - `test_observation_before_reset_done_is_not_judged_in_the_new_run` — 느린 리셋(`reset_delay_s` 3 s)의 `RESET_DONE` 전 보관함 관측이 새 run 에 `pre_reset` 으로만 남고 판정에 쓰이지 않는다(#87).

### `test_stub_arm_m0609.py` — L2, 스텁 팔의 `/m0609/arm/at_home`

`stub_sim`(M0609 흉내)과 `stub_arm` 을 한 프로세스에서 띄운다(`motion_s`·`home_s` 1.0).

- `test_stub_arm_publishes_m0609_at_home_around_a_refill` — 쉬는 동안 2 s 에 8건에서 12건(5 Hz), 모두 true. `Refill` 실행 중 false, 결과는 `motion_s + home_s` 뒤에 오고 그때 곧 true.
- `test_cancelled_refill_answers_first_and_homes_after` — 취소 결과(canceled)가 먼저 오고 `REFILL_DONE` 없이 `home_s` 뒤 true.
- `test_m0609_at_home_waits_for_reset_done` — `REFILL_DONE` 직후(결과 전 홈 복귀 중) `RESET_BEGIN`(e2). 결과가 곧 오고 `home_s` 가 지나도 false 이고, `RESET_DONE`(e2) 뒤 `home_s` 에 true. `lot_id` 는 리셋 앞뒤 모두 빈 값이다.
- `test_refill_that_ends_inside_the_barrier_homes_only_after_reset_done` — `Refill` 실행 중 `RESET_BEGIN`(e2). barrier 안에서 결과가 나도 `home_s` 가 지나도록 false 이고, `RESET_DONE`(e2) 뒤 `home_s` 에 true.
- `test_one_writer_for_m0609_at_home[stub|real]` — 작성자가 하나다. 기본 구성은 `stub_arm`, `serve_refill=false` 와 실물 `m0609_arm` 구성은 `m0609_arm`.

### 그 밖의 테스트 다섯

- `test_container_check_loop.py`(L2) — 실물 orchestrator(`pharmacy_db` 켬)가 `Refill` 결과를 기다리는 중에도 `/orchestrator/check_container` 에 2 s 안에 답한다. 만료 약통은 `expired`, 허용 약통은 `ok` 다.
- `test_conveyor_contract_vectors.py`(L1) — [컨베이어↔팔 계약 벡터](../rokey_p3_interfaces/contract_vectors/conveyor_arm/v1/README.md)의 형식과 기준 판정기(`conveyor_contract.py`)의 기대값.
- `test_m0609_defaults.py`(L2) — 실제 ROS 파라미터로 띄운 `m0609_arm` 이 `v2_guarded_module_path` 기본값을 조건대로 고른다. 명시한 값은 그대로 둔다.
- `test_stub_sim_cabinet.py`(L2) — `/evaluator/cabinet` 작성자가 하나다. `publish_cabinet:=false` 면 `stub_sim` 이 내지 않는다.
- `test_stub_station_scan.py`(L2) — 병동 묶음(mode 3)의 스테이션 인증과 스캔 실패 뒤 스텁 팔의 홈 복귀(#576).

### `test_isaac_json.py` — L1, Isaac JSON 형식

sim/README 표의 예시 11개(5ac8628)와 `pick_notice` 예시 2개(415e4ae)를 글자 그대로 옮겨, 만들기가 예시와 바이트까지 같고 읽기가 예시를 읽는지 본다. 형식 오류 예시(`request_id` 빈 값)는 보내지 않는다.
필드 빠짐·정의 밖 필드·`v`·bool·uint32·stamp·거부 message·이벤트 이름과 `robot_id` 가 틀린 메시지 21종을 거부한다. 계약 밖 거부 message 는 형식 오류가 아니다. `pool_exhausted` 는 9/24 부터 계약 안이다.

### `test_isaac_adapter.py` — L2, 어댑터 하나

`isaac_adapter` 와 Isaac 자리(probe)만 띄운다(시한 `Dispense` 0.6 s, `Reset` 0.8 s).
fixture 는 테스트 전에 probe 와 어댑터의 토픽이 양방향으로 **매칭**됐는지 rclpy 매칭 수로 본다(`matching_checks`, #171).
토픽이 RELIABLE+VOLATILE 이라 매칭 전에 한 번 낸 메시지는 사라지고, `count_subscribers` 는 probe 자신의 엔티티로도 참이 되어 확인이 되지 않았다.
belt 는 depth 1 이라 epoch 테스트는 belt 하나씩 결과(버림·옮김)를 보고 다음을 보낸다.
응답 전달, 무응답·형식 오류·다른 `request_id` 는 시한에 `not_ready`, 다른 `order_id` 는 바로 거부, Isaac 구독자 없음, 빈 `request_id` 는 안 보냄,
`Reset` 의 ok·실패·다른 epoch·무응답, belt·event 의 stamp 와 epoch 옮김, epoch 0 을 현재 epoch 로 바꿈,
거부 message(계약의 `pool_exhausted`·계약 밖 값) 즉시 전달, 이전 epoch belt 버림, `/isaac/events` 재수신 중복 버림,
`pick_notice` 를 적재 픽에만 한 번 보냄(켜기·끄기),
Isaac 이 안 보이면 WARN 을 되풀이하고 구독자가 생기면 INFO 한 번, belt 만 와도 보이는 것으로 치고 끊기면 다시 WARN, 구독자가 있으면 WARN 없음
(`isaac_missing_after_s` 0.5, `isaac_missing_warn_every_s` 2.0).

### `test_isaac_adapter_loop.py` — L2, 가짜 Isaac 으로 조제실 한 바퀴

`pharmacy_only` 한 바퀴, `/orchestrator/reset`(e2), 한 바퀴를 두 구성으로 돈다. adapter 구성은 `stub_sim`(`serve_dispense`·`serve_reset`·`publish_belt` false) + `isaac_adapter` + `fake_isaac`,
stub 구성은 `stub_sim` 기본값. epoch 마다 `events.jsonl` 이름 순서, `Deliver` 결과, dispenser 이벤트의 `request_id` 가 같고, adapter 구성의 `/pharmacy/belt` 작성자와 두 서버가 `isaac_adapter` 하나다.
`fake_isaac` 은 표대로만 말하고 계약 토픽을 구독하지 않는다. 봉투가 집힌 것은 `pick_notice` 로만 안다.
`test_second_dispense_in_one_epoch_needs_the_pick_notice[True|False]` 는 주문 둘을 한 epoch 에 보낸다. 켜져 있으면 두 번째 `Dispense` 가 바로 수락되고 두 트립이 끝나며, 꺼져 있으면 두 번째 배출 요청이 가지 않는다.

### `test_shutdown.py` — L1, 종료 도우미

`shutdown.spin_until_interrupted`(스텁·`isaac_adapter`·`bringup_check` 의 `main()`)가 첫 인터럽트(`KeyboardInterrupt`·`ExternalShutdownException`)에서 조용히 멈추고,
`destroy_node` 안의 두 번째 인터럽트(그룹 SIGINT 의 이중 신호)를 삼키면서도 `try_shutdown` 은 부르고, 그 밖의 예외는 숨기지 않는지 본다(4건, #126).

### L2 테스트 구조

노드를 띄우는 L2 는 한 pytest 프로세스 안에서 테스트마다 `rclpy.init` → 노드·executor → 확인 → 내림을 되풀이한다. 도우미 둘을 같이 쓴다.

| 도우미 | 쓰는 곳 | 무엇 |
| --- | --- | --- |
| `l2_discovery.wait_for_discovery` | `test_stub_loop`·`test_reset_barrier_loop`·`test_isaac_adapter_loop`(트립 전), `test_stub_arm_m0609`·`test_isaac_adapter`(fixture) | 클라이언트가 서버를 보는지(또는 넘긴 매칭 확인)를 20 s 까지 기다리고, 못 보면 빠진 것과 노드·액션·서비스 그래프를 싣고 실패한다(#123) |
| `l2_discovery.ReadyWatch`·`missing_server_report` | `test_stub_loop`, `test_stub_arm_m0609` | 발견 확인 뒤 서버를 놓쳤을 때: 스레드별 `server_is_ready` 표본, 그 액션의 status·feedback 발행자 수와 send_goal 서비스, 그래프, `/dev/shm` Fast DDS 세그먼트 수, 이 프로세스의 앞선 L2(#136·#142) |
| `l2_teardown.assert_no_leftovers` | L2 fixture 전부(`rclpy.init` 전) | 이 프로세스에 handle 이 살아 있는 액션 서버·클라이언트가 있으면(gc 전에 먼저 센다) 목록을 싣고 실패한다(#181·#189) |
| `l2_teardown.teardown_nodes` | L2 fixture 전부(내림) | 협력 종료(`close()` 가 있는 노드) → 진행 중 goal 대기(5 s) → executor 멈춤과 spin·작업 스레드 join(살아 있으면 노드를 내리지 않고 실패) → 액션 엔티티 destroy → `destroy_node` → `try_shutdown` → gc. 끝나지 않은 goal 이 있었으면 다 내린 뒤 실패한다 |
| `fake_isaac.FakeIsaac` | `test_isaac_adapter_loop` | 표대로만 말하는 가짜 Isaac. `publish_clock=True` 면 실물 스테이지처럼 `/clock` 도 낸다(#140) |

왜 이렇게 됐나(CI 관측)
- 9/17: 노드가 다 떠 있는데 `order_generator` 가 `/deliver` 를 90 s 동안 못 봤다. 트립 전 발견 확인과 진단을 넣었다(#123·#136).
- 9/18 #168: `test_stub_arm_m0609` 에 `/m0609/refill` 서버가 10개 보였다. rclpy `destroy_node` 는 액션 서버·클라이언트를 없애지 않아, 앞 테스트들의 노드·participant 가
  같은 프로세스에 남아 있었다(docker 재현: `/dev/shm` 세그먼트가 L2 테스트마다 8 씩 늘어 88). `teardown_nodes` 뒤로는 모든 테스트가 끝날 때 0 이다(#181·#189 측정).
- rclpy 7.1.11(Jazzy 이미지)의 `Executor.shutdown` 은 진행 중 callback 을 기다리지 않는다(`_is_shutdown` 을 켠 뒤 `if not self._is_shutdown` 으로 대기를 건너뜀).
  `MultiThreadedExecutor` 의 작업 스레드가 spin 스레드가 끝난 뒤에도 돌아서, `teardown_nodes` 가 작업 스레드를 직접 join 한다(비공개 속성, #189).
- "그래프에는 서버가 보이는데 `wait_for_server` 가 거짓" 인 기전은 미확인이다. 외부 검토(#185 A3): rcl 은 서비스마다 그래프끼리·매칭끼리만 수를 비교한다.
  그래서 "그래프 수와 매칭 수가 같아야 한다" 는 우리 가설은 틀렸다.

자가 테스트
- `test_l2_discovery.py`: 서버가 없으면 시한에 실패하는지, 클라이언트 목록 이름, 보고 형식.
- `test_l2_teardown.py`: `destroy_node` 만 하면 남음, 도우미면 0, 실행 중 goal 이 close 로 빠져나옴, close 를 무시하는 goal 은 다 내린 뒤 실패.

CI 의 `colcon test` step 은 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST`, run 마다 다른 `ROS_DOMAIN_ID`, `--executor sequential`(패키지 테스트를 동시에 돌리지 않음)로 돈다(`ci.yml`). 마스터 PC 의 launch 에는 적용하지 않는다.

## 내리기

- **SIGINT 로 내린다.** 호스트 tmux 에서는 launch 창에서 Ctrl-C, 컨테이너는 `docker kill -s INT <이름>`. 그래야 `event_logger` 가 `orders.jsonl`·`meta.json` 을 닫는다.
- **이름으로만 내린다.** 자기가 띄운 셸 작업(`kill -INT %N`), tmux 세션 이름, docker 컨테이너 이름(`p3v-*`)만 쓴다.
  `ps`·`pgrep` 으로 모은 PID 목록을 kill 에 넘기지 않고, 부모 PID 를 따라 올라가지 않는다. `pkill`·`killall`·`kill -9` 는 쓰지 않는다.
  9/17 에 docker 프로세스의 부모 PID 를 따라 kill 하다 `systemd --user` 를 내려 그 사용자의 세션이 모두 끊겼다.
- 안 내려가는 것이 있으면 더 세게 죽이지 말고 무엇이 남았는지 적어 알린다.
- `ros2 launch` 는 SIGTERM 을 자식 노드에 넘기지 않았다(main 7ac85b7 관측: launch 만 죽고 노드 7개가 남음, 아래 종료 신호 표). `docker stop`(SIGTERM 뒤 10 s SIGKILL)도 run 기록을 닫지 못한다.

## 검증 방법

개발 노트북(macOS)에는 ROS 가 없어서 L1·L2·launch 검증을 docker 로 돌린다. CI(`ci.yml`)와 같은 이미지·명령·환경 변수다.

- 이미지 `ros:jazzy-ros-base-noble`. CI 의 colcon job 도 이 이미지 컨테이너에서 돈다(#129). 컨테이너 안에 저장소를 복사해 `colcon build --symlink-install`, `colcon test --executor sequential`, `colcon test-result --verbose`.
- CI 와 같이 `ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST` 와 쓰지 않는 `ROS_DOMAIN_ID` 를 준다.
- 노트북에서 다른 작업이 같이 돌면 `--cpus`·`--memory` 로 줄이고 컨테이너는 한 번에 하나만 돌린다(9/18, 가용 메모리 부족으로 대기 명령이 멈춘 일이 있다).
- `--network none`. 검증 노드가 팀 DDS 도메인에 나가지 않는다.
- 케이스마다 새 컨테이너(`--rm`). 한 컨테이너에서 이어 돌리면 내린 노드가 discovery 캐시에 남아 `ros2 topic info` 의 발행자 수가 틀리게 나왔다.
- 컨테이너 이름은 `p3v-<케이스>` 이고 이름으로만 내린다(위 "내리기").
- 컨테이너 안 셸에서 노드를 띄울 때는 `set -m` 을 켠다. 안 켜면 백그라운드 작업이 SIGINT 를 무시한다.
  `kill -INT %N` 은 작업의 프로세스 그룹 전체에 가서 터미널 Ctrl-C 와 같다. `ros2 run` 래퍼 PID 하나에만 보내면 노드에 넘어가지 않았다.
- 아래 명령은 `src/` 의 패키지 일곱을 모두 빌드한다. 저장소 전체를 복사하는 이유는 `test_reset_barrier_loop` 가 루트의 `tools/aggregate_runs.py` 를 읽기 때문이다.

```bash
docker run --rm --name p3v-colcon --network none --cpus 3 --memory 2500m --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST -e ROS_DOMAIN_ID=77 \
  -v "$PWD":/repo:ro ros:jazzy-ros-base-noble bash -c '
    mkdir -p /tmp/ws && cd /repo && tar --exclude=.git -cf - . | tar -xf - -C /tmp/ws && cd /tmp/ws
    source /opt/ros/jazzy/setup.bash
    colcon build --symlink-install
    source install/setup.bash
    colcon test --executor sequential && colcon test-result --verbose'
```

- 최근 기준: main edde51f 에서 위 명령(`--cpus 3 --memory 2500m`, 순차): `Summary: 480 tests, 0 errors, 0 failures, 0 skipped`
  (build `7 packages finished`, bringup 95, manipulation 122, navigation 42, orchestrator 208, perception 13).
- rclpy 를 가짜 모듈로 바꿔 통과한 노드 테스트가 진짜 rclpy 에서 깨진 적이 있다. #92 의 `test_status_monitor_node` 는 테스트 도우미가 `node.timers` 에 값을 넣었는데,
  실제 rclpy `Node.timers` 는 읽기 전용 property 라 docker Jazzy 에서 2건 `AttributeError` 였다(832c2c3 에서 고침). 노드를 건드린 PR 은 docker 로 한 번은 돌린다.

## 알려진 문제·9/21 뒤 과제

시연(9/21) 전에는 실행 노드를 바꾸지 않기로 해서(9/18) 미뤄 둔 것이다. 9/21 뒤 처리 여부는 이 README 에서 추적하지 않았다(미확인).

- **스텁 heartbeat 흔들림.** `stub_arm`·`stub_fleet` 의 5 Hz heartbeat 발행 간격이 `MultiThreadedExecutor` 에서 관찰자 기준 최대 0.6-1.0 s 까지 흔들린다(팔 측정 9/18).
  stale 판정 1.0 s 에 가깝다. GoToZone 거부(`arm/at_home` stale)·`goto_rejected` 불안정과의 관계는 미확인이다.
- **노드가 자기 액션 엔티티를 내리지 않는다.** `stub_arm`·`stub_fleet` 은 만든 `ActionServer` 를 보관하지도 `destroy_node` 에서 없애지도 않는다.
  테스트는 `teardown_nodes` 가 대신 치운다. 노드 쪽 수정은 handle 이 살아 있을 때만 destroy 하게 한다(도우미와 겹치지 않게).
  orchestrator·order_generator·arm·m0609_arm(다른 레인)도 같은 구조다(외부 검토 #185 A3 Q3-1).
- **rclpy 7.1.11 `Executor.shutdown` 이 진행 중 callback 을 기다리지 않는다**(위 L2 테스트 구조). 실행 노드의 `main()` 종료 경로(spin → destroy)에도 해당한다.
  테스트 밖 영향은 미확인이고, 다른 레인에도 전달했다.
- **`wait_for_server` 거짓의 기전 미확인.** 실패 순간 기존 클라이언트의 서비스별 그래프·매칭 수가 필요하다(#185 A3 확인 실험 2).

### 9/17 에 돌린 기준선

출처: 9/17 docker 검증 보고. 명령·출력 원문은 PR #54·#55·#66·#74·#79 본문에 있다. 트리 SHA 는 각 행에 적었다.

| 항목 | 트리 | 결과 |
| --- | --- | --- |
| colcon build·test | main 7ac85b7 | `Summary: 225 tests, 0 errors, 0 failures, 0 skipped` |
| 기본 스텁 한 바퀴 | main 7ac85b7 | `Deliver` `success=True [ord-0002=DELIVERED]`, `orders.jsonl` `SUCCESS`, 이벤트 22건 |
| `pharmacy_only` 한 바퀴 | main 7ac85b7 | 이벤트 12건, `LOAD_DONE` → `ORDER_DONE` → `ARM_HOME` → `RETURNED` → `DOCKED`, 마지막 상태 `HOLD_RETURN`(`pharmacy_only`), `success=False`. 당시 launch 인자가 없어 wrapper 로 넘겼다(#74 에서 인자 추가) |
| 보충, `stub_arm` Refill | main 7ac85b7 | `DISPENSER_PAUSED`·`REFILL_REQUESTED` → `REFILL_DONE`(m0609) → `DISPENSER_RESUMED`, 트립 `SUCCESS`, 이벤트 26건 |
| 보충, `use_stub_m0609:=false` + `m0609_arm` | main 7ac85b7 | 같은 순서, 트립 `SUCCESS`, 이벤트 26건 |
| 집계기 | main 7ac85b7 | epoch 2 트립 `counted`, `lap_success 1`. `pharmacy_only`+보충 유도에서 `refill_s 0.499957145` |
| 서버 지연 N=6 s(#67) | main bdbd4d1 | 대기 WARN 1줄, 거부 0, `success=True` |
| 서버 지연 N=15 s(#67) | main bdbd4d1 | 10 s 에 "거부로 본다" 1회, 5 s 뒤 재시도 성공, `success=True` |
| 서버 지연 N=35 s(#67) | main bdbd4d1 | 거부 2회, 주문 `ABORT`(`goto_rejected`), `success=False` |
| 리셋 뒤 요청 대기(#72) | 22f9d88(#74+#72 로컬 merge) | barrier 거부 0건(수정 전 3건), `r002-0001`(긴급 `ord-0002`) 수락, `lap_success 1`, `refill_s 0.233569537` |
| tmux 창 닫기(#73) | 2d352f5 대 main bdbd4d1 | `event_logger` 0.45 s 에 종료·`orders.jsonl`·`meta.json` 있음 대 30 s 안에 안 끝남·없음 |
| 리셋 울타리(#78·#79) | 0bbd317 | `RESET_BEGIN` 있음: 구간 joint_command 0건 ×8. 없음: 16·16·15(같은 코드), 16·16·16(main 79b9d38) |

종료 신호별 run 기록(main 7ac85b7, 기본 launch, `Deliver` 결과 뒤 신호):

| 내린 방법 | 노드 | `orders.jsonl`·`meta.json` |
| --- | --- | --- |
| launch 에 SIGINT | 모두 정상 종료 | 있음 |
| launch 에 SIGTERM | launch 만 죽고 노드 7개가 남음 | 없음 |
| `docker stop`(PID 1 이 launch) | 10 s 뒤 SIGKILL, exit 137 | 없음 |
| `docker kill -s INT` | 정상, exit 0 | 있음 |
| tmux 창 닫기 | `event_logger` 만 남아 멈춤 | 없음(#73 이후 0.45 s 에 닫힘, 위 표) |
