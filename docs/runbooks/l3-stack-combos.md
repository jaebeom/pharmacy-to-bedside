# L3 스택 기동 조합과 opt-in 짝

> **상태: 지난 기록 (2026-09-20 기준).** 지금은 [병원 데모 런북](hospital-demo.md)을 따른다.

- 대상: 마스터(`master01`·`master02`)에서 Isaac 스테이지·스택·팔을 같이 띄우는 사람.
- 기준: `main` `e271081`(#296 머지 뒤). `tools/demo_v2.sh`, `src/rokey_p3_bringup/launch/stub_loop.launch.py`, 패키지 README, [계약 v1](../architecture/delivery-contract-v1.md).
- 상태: 코드와 README 에서 읽은 것이다. 이 조합을 Isaac 에서 켜 본 것은 1절(시연 경로)뿐이고, 3절의 opt-in 은 **L3 미실행**이다.
- 증거 run 을 돌리는 순서는 [증거 실행 runbook](evidence-run-pharmacy-lap.md)에 있다.

## 1. 시연 경로(`demo_v2.sh`)의 조합

`tools/demo_v2.sh` 의 `stack_cmd` 가 치는 명령:

```
ros2 launch rokey_p3_bringup stub_loop.launch.py use_isaac_adapter:=true pharmacy_only:=true \
  publish_clock:=false emulate_m0609:=false use_stub_m0609:=false \
  dispenser_file:=… order_pool_file:=… run_host:=…
```

토픽·서비스마다 작성자가 하나여야 한다. 인자마다 이유는 다음과 같다.

| 인자 | 값 | 이유 |
| --- | --- | --- |
| `use_isaac_adapter` | true | Isaac 스테이지가 `/pharmacy/dispense`·`/sim/reset`·`/pharmacy/belt` 를 맡는다. stub_sim 의 같은 기능은 꺼진다 |
| `publish_clock` | false | `/clock` 작성자는 Isaac 하나다(계약 4절). true 면 작성자가 둘이 된다. launch 는 경고만 하고 막지 않는다 |
| `emulate_m0609` | false | `/m0609/joint_states`·`gripper/holding` 을 Isaac 이 낸다. true 면 작성자가 둘이 된다(같은 경고) |
| `use_stub_m0609` | false | 실물 `m0609_arm` 이 `/m0609/refill` 을 맡는다. true 면 refill 서버가 둘이다 |
| `pharmacy_only` | true | 1차 시연은 조제실 구간만 돈다. 주문은 침상에 가지 않고 복귀한다. 그때 마지막 상태는 `HOLD_RETURN` 이다 |
| `use_stub_arm`·`use_stub_fleet`·`use_stub_detector` | 기본 true | UR5·주행·검출은 스텁이다. 실물로 바꾸면 그 인자를 false 로 하고 실물 노드를 따로 띄운다 |
| `pick_notice` | 기본 true | 스텁 팔은 봉투를 실제로 집지 않는다. adapter 가 Isaac 에 알려 봉투를 치우게 한다 |

## 2. 섞이면 안 되는 조합

- **stub_sim 의 벨트·배출과 isaac_adapter 를 같이 켜지 않는다.** launch 는 `use_isaac_adapter` 하나로 둘을 바꾼다. adapter 를 launch 밖에서 따로 띄우면 작성자가 둘이 된다.
- **실물 UR5(`--ur5`)와 스텁 회수를 같이 쓰지 않는다.**
  - 스테이지는 `--ur5` 에 stand-in(`ros_pick_stand_in_s>0`)을 주면 기동을 거부한다(#244).
  - `--ur5` 스테이지는 `pick_notice` 를 받아도 세기만 하고 적용하지 않는다.
  - 실물 팔 구성에서는 launch 에 `pick_notice:=false`, `use_stub_arm:=false` 를 준다.
- **ROS 도메인:** 스테이지·팔·스택·웹이 같은 `ROS_DOMAIN_ID` 여야 한다(`demo_v2.sh` 는 `P3_DOMAIN`). 다르면 adapter 가 기동 5 s 뒤부터 10 s 마다 "Isaac 스테이지가 안 보인다" WARN 을 낸다.

## 3. opt-in 인자와 짝

시연에는 켜지 않는다. 전부 기본 꺼짐이고 `main` 에 들어가 있다. 짝이 맞아야 의미가 있다. 기본값은 시험이 고정한다(launch 는 `test_skeleton`, 스테이지는 sim 시험).

| 켜는 곳 | 인자 | 짝(같이 켜야 하는 것) | 짝이 없으면 |
| --- | --- | --- | --- |
| 스테이지 | `--belt-fail-closed`(#252) | — | 해당 없음. 켜면 속도 미수신·봉투 소실 때 점유를 유지한다(리셋으로 복구) |
| 스테이지 + launch | `--belt-observation`(#276) + `belt_observation:=true`(#279) | 둘 다 | 한쪽만 켜면 `/pharmacy/belt/observation` 이 비어 있다. 다른 동작은 그대로다 |
| 스테이지 + launch + 팔 | `--gripper-command-seq` + `gripper_command_seq:=true` + arm_node `gripper_observation:=state`(아래 첫 줄) | 셋 다 | 스테이지만 켜면 Bool 흡착 명령이 무시된다. 스테이지를 끄면 `GripperState` 가 없어 팔이 파지를 확인하지 못한다 |
| 팔 | arm_node `arm_clearance_enabled:=true`(#282) | 통로 기하 파라미터 전부(`arm_clearance_lane_frame`·`_lane_lower`·`_lane_upper`·`_link_radii`·`_tool_length_m`·`_tool_radius_m`, 파지물 `_payload_*`). **기본값이 없다** | 파라미터가 비면 `ArmClearance` 가 UNKNOWN 이고 `detail` 에 이유를 적는다 |
| 팔 | arm_node `placement_check_enabled:=true`(#296) | `gripper_observation:=state`(#291). 기하·시한(`placement_view_standoff_m`·`placement_slot_box_m`·`placement_cabinet_box_m`·`placement_timeout_s`)은 **기본값이 없다** | `gripper_observation` 이 `state` 가 아니면 기동을 거부한다. 기하·시한이 비면 오류 로그를 남기고, 모든 픽이 안착 미확인(`dropped`)으로 닫힌다 |
| launch | `observation_guard:=true`(#290, **시험용**) | 벨트 관측(둘째 줄) + `ArmClearance`(넷째 줄, 기하 채움) | **fail-closed 라 첫 피킹이나 다음 배출에서 트립이 멈춘다.** orchestrator 가 5 s 마다 WARN 으로 이유("벨트 관측 없음", "팔 통로 관측이 CLEAR…")를 남긴다 |

- 그리퍼 짝: 스테이지 `--gripper-command-seq`(#278)는 `--ur5 --mode ros` 가 필요하다. launch 는 #286, 팔은 #291 이다.
- 시연 스택은 UR5 가 스텁(`use_stub_arm` 기본 true)이다. 그래서 arm_node 파라미터(#282·#291·#296)는 실물 팔을 띄울 때만 의미가 있다.
- `ArmClearance` 의 CLEAR 는 L3 에서 FK 와 실제 TCP 를 대조하기 전에는 믿지 않는다(계약 11.6). `observation_guard` 를 켠 run 은 시험 run 으로 기록한다.
- `observation_guard` 는 칸 안착을 보지 않는다. 안착 확인(계약 11.4)은 팔의 `placement_check_enabled` 가 한다.
  - 관측 자세 이동에 충돌 검증이 없다(#296 본문). L3 에서 촬영 자세를 확인하기 전에는 켜지 않는다.

## 3.1 시연 스크립트로는 opt-in 짝을 못 켠다

- `tools/demo_v2.sh` 에는 launch 인자를 넘기는 통로가 없다. 바꾸려면 `P3_STACK_CMD` 로 스택 명령을 **통째로** 갈아야 한다. 스크립트는 시연 보호로 고치지 않는다.
- 그래서 opt-in 짝은 **셸을 직접 띄워** 본다. 웹 venv 가 없는 호스트(예: `master02`)에서는 `demo_v2.sh` 자체가 뜨지 않으므로 이 방법뿐이다.
- 웹이 없어도 트립은 돈다. `order_generator` 가 epoch 마다 자동 요청 1건을 보낸다(웹은 리셋·요청 화면일 뿐이다).

```bash
# 스테이지는 따로 띄운다(L3 런카드 RC-3a). 아래는 스택만. 스테이지와 같은 워크트리·도메인이어야 한다.
export P3_REPO=${P3_REPO:?워크트리 절대경로}
export P3_DOMAIN=${P3_DOMAIN:?스테이지와 같은 값}
source /opt/ros/jazzy/setup.bash
source "$P3_REPO/install/setup.bash"
export ROS_DOMAIN_ID="$P3_DOMAIN"
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp

ros2 launch rokey_p3_bringup stub_loop.launch.py \
  use_isaac_adapter:=true pharmacy_only:=true \
  publish_clock:=false emulate_m0609:=false use_stub_m0609:=true \
  belt_observation:=true \
  dispenser_file:="$P3_REPO/src/rokey_p3_orchestrator/config/dispenser.yaml" \
  order_pool_file:="$P3_REPO/src/rokey_p3_orchestrator/config/order_pool.yaml" \
  run_host:=master02 2>&1 | tee -i /tmp/p3-stack.log
```

- 재고 파일: 저장소 기본(`config/dispenser.yaml`, 약품마다 5개)이면 한 트립에서 보충이 나오지 않는다. 보충까지 보려면 슬롯 a 1·b 0 파일을 만든다([보충 장면 runbook 5](master02-m0609-refill-stage.md#5-조제기-설정-파일)).
- 스텁 보충은 **물리 성공으로 세지 않는다.** orchestrator 재고만 되돌리고 Isaac 의 캐니스터는 움직이지 않는다.
- 팔 노드 없이 돌릴 때만 `use_stub_m0609:=true` 로 둔다. 스텁이 `/m0609/refill` 을 받는다.
- 볼 것: `ros2 topic hz /pharmacy/belt/observation`(약 5 Hz), `echo` 의 `pouch_zone`·`pouch_motion`·`belt_command_applied` 전이와 `seq` 증가, adapter 종료 로그의 `dropped` 줄.
- **트립이 한 번뿐이다.** launch 기본 `max_requests` 가 1 이라 스택 기동당 자동 요청 1건이다. **`ros2 topic echo` 를 스택보다 먼저 붙인다.** 늦게 붙이면 전이를 놓치고 스택을 다시 띄워야 한다(실습15b 1차에서 그랬다).
- 스택 셸에 `set -u` 를 걸지 않는다. `/opt/ros/jazzy/setup.bash` 가 `AMENT_TRACE_SETUP_FILES: unbound variable` 로 죽는다.
- 상태: **실습15b 회차 A 통과**(`master02`, tree `eba5351`, 도메인 118, 웹 없음).
  - `/pharmacy/belt/observation` 전이: `pouch_zone=1 pouch_motion=1 belt_command_applied=1` → 종단 `pouch_zone=2`(sim 202.966) → `pouch_motion=2`·`belt_command_applied=2`(203.350) → 스텁 회수 뒤 `mode=1`·`occupancy=1`(203.716). `seq` 11891 → 14744 로 단조 증가.
  - `REQUEST_ACCEPTED` → `DOCKED` 12.483 s. 주문 마지막 상태 `HOLD_RETURN`. adapter `dropped`·`observation_*` 0건, `pouch_lost` 0건, `belt note=stop_belt` 는 트립당 한 줄.
  - 시연 조합과 다른 점 둘: `use_stub_m0609:=true`(스텁 보충), 저장소 기본 재고 파일(약품마다 5개라 보충이 안 나온다). 그래서 이 회차는 **벨트 관측 전이**만 확인한 것이다.

## 3.2 녹화·캡처 (재범 규칙, 9/20)

- **창 모드로 돌리면 녹화를 켠다. 대본 단계마다 캡처를 남긴다.** headless 라 불가능하면 그 이유를 실습 문서에 한 줄 적고 대체 증거(로그·토픽 echo·집계 출력)를 남긴다. **"없음"만 적고 닫지 않는다.**
- 파일마다 이름·크기·sha256 을 실습 문서에 적는다. 원본은 저장소에 넣지 않는다.
- 녹화: `master01` 은 ffmpeg `x11grab` 이다. GStreamer 에 `h264parse` 가 없어 다시 시도하지 않는다. `master02` 는 `gst-launch-1.0 ximagesrc` 다.
- 주기 캡처는 `P3_CAPTURE_EVERY`(초)로만 켠다. 기본은 꺼짐이다. 도구가 없거나 `DISPLAY` 가 없으면 `demo_v2.sh` 가 스스로 끈다.

## 4. 어긋났을 때 보이는 것

- adapter
  - `Isaac 스테이지가 안 보인다(…)` WARN: 도메인과 스테이지 기동을 확인한다.
  - `dropped` 카운터: 종료 로그에 남는다. `stale_belt`·`observation_*`·`gripper_*` 가 늘면 epoch 나 seq 가 어긋난 것이다.
- orchestrator: 트립이 guard 로 멈추면 5 s 마다 `wait_report` WARN 한 줄에 이유(어느 토픽이 unknown 인지)를 남긴다.
- `/clock` 작성자가 둘이면 시간이 튀거나 되감긴다. launch 시작 로그의 경고 줄("use_isaac_adapter:=true 인데 publish_clock…")을 먼저 본다.

## 5. run 에 남길 것

- 실행 SHA
- `stub_loop.launch.py` 인자 전부
- 스테이지 인자(`P3_STAGE_ARGS` 포함)
- `ROS_DOMAIN_ID`
- adapter·orchestrator 종료 로그의 `dropped` 줄과 wait 줄
