# rokey_p3_manipulation

v1.1.0 병원 한 바퀴에서 `m0609_arm` 은 orchestrator 가 `/m0609/refill` 을 부르면 3축 레일 위 M0609 로 선반 약통을 조제기에 넣는다(`scene_version:=2`, `v2_rail_select:=preferred_first`, `container_check:=true`).
UR5 `arm`(AMR 합본)은 A1 탁자에서 봉투를 손 카메라 QR 로 확인해 집고, 병상 인식표 QR 을 읽은 뒤 보관함에 놓는다(`ur5_arm.amr-combined.camera-receiver.yaml`, #796).
두 노드 모두 `tools/demo_v2.sh` 가 띄운다. 레일 선택 기본값의 차이는 [아래 절](#레일-후보-선택-노드-기본과-시연-기본)에 있다.

M0609 캐니스터 보충, UR5 의 벨트 끝 픽과 침상·스테이션 플레이스. **manipulation 담당**의 단독 영역이다.
같은 담당이 `rokey_p3_perception` 도 소유한다.

## 현재 팔 제어 방식

| 팔·실행 경로 | 목표를 관절 명령으로 바꾸는 방법 | 확인 범위 |
| --- | --- | --- |
| UR5 `arm` | 목표 손끝 자세를 `ur5_kinematics.solve_ik()` 로 풀고, 현재 관절값에서 해까지 관절 공간으로 보간 | 수치 IK 안에서 FK 로 예상 손끝 자세와 목표의 오차를 계산한다. FK 로 팔을 제어하는 경로는 아니다 |
| M0609 ROS `m0609_arm` v0·v1 (`scene_version:=1`) | 파라미터(v0) 또는 레일 teach 파일(v1, `rail_enabled`)의 관절 waypoint 를 순서대로 보간 | 기본값은 `joint_states` 로 각 waypoint 도착을 확인한다. 실행 중 IK·충돌 검사는 없다. v1 은 TCP 최고 속도만 FK 로 본다(#165) |
| M0609 ROS `m0609_arm` v2 (`scene_version:=2`) | 모듈은 전체 경로 제약을 통과한 유한 후보의 예상 이동시간을 비교한다(#229). 원통은 기존 IK·여유 거리 계획을 쓴다(#177·#186) | 모듈은 수평 운반·충돌 검사·정지와 파지 관측을 기본 적용한다. guarded 경로의 Isaac L3는 미실행이다. master02 실습7-a4·7-a5·7-b·8은 기존 경로의 기록이다 |
| M0609 Isaac `selfdemo` | Lula IK 로 목표 TCP 자세를 풀고 도달한 관절값을 `teach` 후보로 기록 | 별도 Isaac 실행이다. ROS `m0609_arm` 이 Lula 를 호출하지는 않는다 |

M0609 의 USD·URDF·Lula robot description YAML 은 [sim README 의 9/17 자산 확인](../../sim/README.md#배치--임시-시나리오-자리)에 기록된 현장 파일이다. 이 저장소에는 없다. DH 를 직접 확인하지 않았다는 사실은 **자체 DH 모델의 미확인 상태**이며, Lula IK 에 필요한 모델 파일이 없다는 뜻은 아니다.
`m0609_arm` 은 세 모드가 있다. 기본(v0)은 레일 없는 고정 스테이지의 관절 waypoint 다. `rail_enabled:=true`(v1, #154·#165)는 2축 레일 teach 파일, `scene_version:=2`(v2, #177·#186·#190)는 3축 레일과 실행 중 IK 계획이다. 9/21 시연과 v1.1.0 병원 한 바퀴는 v2 다(아래 [레일 보충 v2](#레일-보충-v2-scene_version2), `tools/demo_v2.sh` 의 `arm_cmd`). Lula(Isaac `selfdemo`)는 여전히 이 노드의 실행 경로에 없다. v2 는 저장소의 명목 기구학(#144)을 쓴다(TCP 대조는 아래 `m0609_kinematics` 항목).

- 노드: `ros2 run rokey_p3_manipulation arm`
  - 내는 것: `/<robot>/arm/joint_command` (UR5 6개만 position), `/<robot>/gripper/command`,
    `/<robot>/arm/at_home` (5 Hz, 홈 0.05 rad 이내 + 활성 goal 없음), `/events`
  - 받는 것: `/<robot>/joint_states`, `/<robot>/gripper/holding`, `/<robot>/base/stopped`,
    `/<robot>/hand_camera/pouches`, `/<robot>/hand_camera/tag_reads`, `/pharmacy/belt`, `/events`.
    `pouch_source`·`scan_tag_source` 가 `sim` 이면 `/<robot>/sim/pouches`·`/<robot>/sim/tag_reads` 를 대신 받는다
  - 파라미터(기본값). 프레임 이름·오프셋·거리는 **마스터에서 확인**하고 덮는다.
    - `robot_id`(`amr_1`), `joint_names`(`shoulder_pan_joint` 등 UR5 표준 6개), `home_joint_positions`(0 × 6), `home_tolerance_rad`(`0.05`)
    - `joint_limits_low/high`(**Isaac 자산 한계**: elbow 만 ±π, 나머지 ±2π). 파라미터가 자산보다 넓으면 좁힌다
      (`ur5_kinematics.intersect_limits`, 넓히는 방향으로는 안 덮인다). 자산 한계는 9/20 L3 의 `dof` 줄·`ur5.urdf` 에서 왔다.
      제원(±2π)만 믿고 푼 해는 PhysX 가 조용히 잘라 관절이 목표에 영영 못 간다. M0609 의 `URDF_LIMITS_RAD` 와 같은 규칙이다.
    - `command_rate_hz`(`20.0`), `max_joint_speed`(`0.5`)
    - `arm_base_frame`, `deck_slot_frame_prefix`, `cabinet_frame`, `tool_frame`, `hand_camera_frame`(모두 빈 값)
    - `pick_timeout_s`(`60.0`, 계약 7절), `detection_timeout_s`(`5.0`), `detection_max_age_s`(`1.0`, 계약 2.4절), `approach_height_m`(`0.10`)
    - `grasp_z_offset_m`·`place_z_offset_m`(`0.0`), `grasp_settle_s`(`0.5`), `release_settle_s`(`0.3`)
    - `scan_timeout_s`(`30.0`, 계약 7절), `tag_standoff_m`(`0.0`. 0 이면 `ScanTag` 를 시도하지 않고 `UNREADABLE`)
    - `via_joint_positions`(형만 선언, 비면 끔. 홈↔작업 사이 경유 관절 자세 6개), `arrival_check_enabled`(`true`), `arrival_tolerance_rad`(`0.05`), `arrival_timeout_s`(`2.0`)
    - `arm_base_frame_convention`(`base`), `arm_base_frame_check`(`true`, 기동 때 FK 와 손목 TF 로 프레임 축을 확인하고 다르면 기동 거부), `arm_base_frame_check_tries`(`40`), `wrist_link_frame`(빈 값)
    - `deck_slot_frame_base`(`0`. Isaac 칸 프레임은 1 부터라 합본 파일은 1), `deck_pick_from_frame`(`false`), `pouch_height_m`(`0.01`), `grasp_hold_timeout_s`(`2.0`)
    - `pouch_source`·`scan_tag_source`(`camera` | `sim`). launch 인자가 params 파일보다 우선한다([bringup README](../rokey_p3_bringup/README.md))
    - `vision_check`(`false`), `vision_check_timeout_s`(`1.0`), `vision_check_tolerance_m`(`0.05`), `vision_check_lookback_s`(`3.0`). 참값으로 집을 때 검출과 대조한다
    - `belt_pick_lock_wrist`(`false`), `belt_pick_contact_drop_m`(`0.0`, 0–0.06 m). 켜면 카메라 벨트(탁자) 픽에서 손목(J6)을 관측 직후 값으로 고정하고 이 거리만큼 더 내려 접촉 흡착한다.
      v1.1.0 병원 카메라 파일은 `true`·`0.05` 다(#796, 실측 보정이고 근본 수정이 아니다)
  - 선택(opt-in) `arm_clear_of_belt`(계약 11.6): `arm_clearance_enabled`(`false`). 켜면 `/<robot>/arm/clear_of_belt`(`ArmClearance`,
    `arm_clearance_rate_hz` 10 Hz)를 내고 `/<robot>/gripper/state`(`GripperState`)를 받는다. 끄면 토픽·구독을 만들지 않는다.
    - 판정은 `belt_lane_clearance.judge`: 실측 `joint_states` FK 의 링크 6 + 공구 + 파지물 vs 통로 상자 → UNKNOWN/CLEAR/INTRUDING.
    - 기하 파라미터는 **기본값이 없다**(비었거나 음수 = 미설정 → UNKNOWN): `arm_clearance_lane_frame`, `arm_clearance_lane_lower/upper`(3),
      `arm_clearance_link_radii`(6), `arm_clearance_tool_length_m`, `arm_clearance_tool_radius_m`, `arm_clearance_payload_size/center`(3).
      `arm_clearance_region` 은 로그용 이름이다.
    - epoch = 마지막 `RESET_DONE`(리셋 전 1). 이벤트를 하나도 못 받았으면 내지 않고, barrier 중에는 UNKNOWN. seq 는 joint_states stamp 가 앞으로 갔을 때만 +1.
    - 파지 여부는 `GripperState` 로만 본다(Bool `holding` 은 쓰지 않는다). 모르면 링크·공구가 이미 닿을 때만 INTRUDING, 아니면 UNKNOWN.
    - **L3 에서 FK↔TCP 대조 전에는 CLEAR 를 다음 배출 허가의 근거로 쓰지 않는다.**
  - 선택(opt-in) 흡착 관측 `gripper_observation`(`bool` 기본 | `state`, 계약 11.6). `state` 면:
    - 명령을 기존 `gripper/command`(Bool)와 `/<robot>/gripper/command_seq`(`GripperCommand`)에 같은 값으로 낸다.
      `command_seq` 는 epoch(마지막 `RESET_DONE`, 리셋 전 1)마다 1 부터 명령마다 +1. epoch 를 모르면 내지 않는다.
    - 흡착 확인 = `GripperState` HELD ∧ `last_applied_command_seq ≥ 닫기 seq`. 명령 전의 HELD 는 파지가 아니다.
      해제 확인 = RELEASED ∧ `last_applied ≥ 열기 seq` 뒤에만 `POUCH_LOADED/PLACED` 를 낸다.
    - 닫기 적용 뒤 RELEASED 는 `dropped`(이송 중) 또는 `grasp_failed`(파지 중). 관측이 없거나 오래됐거나 다른 epoch 면
      **관측 소실**이라 멈추고 `timeout` + detail 로 닫는다(계약 outcome 에 관측 소실 값이 아직 없다).
    - 기존 Bool `holding` 으로는 판정하지 않는다. `bool`(기본)은 이전과 같다.
  - 선택(opt-in) 칸 안착 확인 `placement_check_enabled`(`false`, 계약 11.4 제안). `gripper_observation: state` 가 필요하다(아니면 기동 거부).
    - 해제 확인 뒤 손 카메라를 놓을 곳 프레임(`deck_slot_N` 또는 보관함, 원점 = 물체가 놓이는 윗면의 중심) 위
      `placement_view_standoff_m` 로 옮겨, `placement_timeout_s`(sim) 동안 "해제 명령 뒤 stamp ∧ QR = goal 주문 ∧ 위치가
      `placement_slot_box_m`/`placement_cabinet_box_m` 상자 안(가장자리는 밖)"인 검출을 기다린다. 있을 때만 `POUCH_LOADED/PLACED`.
    - 확인하지 못하면 outcome `dropped`(detail `placement_unconfirmed: …`)로 닫는다. trip_fsm 이 재시도하지 않는 유일한 기존 값이라서다
      (즉시 ABORT). 결정 16번 전 임시 매핑이고, 이 경로를 켠 run 의 "낙하" 집계에는 안착 미확인이 섞인다(detail 로 나눠 센다).
    - 치수·거리·시한은 **기본값이 없다**(미설정이면 모든 픽이 안착 미확인). `tool_frame` 도 필요하다.
    - **관측 자세 이동은 충돌 검증이 없다. L3 에서 촬영 자세를 확인하기 전에는 켜지 않는다.**
  - 흡착점 오프셋 `tcp_offset_m`(기본 `[0, 0, 0]` = 지금 동작). 공구(IK 끝점) 기준 흡착점이다.
    파지·놓기 목표만 흡착점 자세다. IK 에 넘길 때는 공구 자세로 되돌린다. 관측 자세(인식표·안착 확인·벨트)는 공구 자세만 쓴다.
    합본 + 흡착 그리퍼 자산 값은 `[0, 0, 0.1555]` 다(`config/ur5_arm.amr-combined.camera.yaml`). 스테이지 가상 흡착과 같은 점이다.
  - 선택(opt-in) 벨트 관측 자세 `belt_view_standoff_m`(`0.0` = 끔). `pouch_source: camera` 의 벨트 픽에서만 쓴다.
    - 검출을 기다리기 전에 손을 옮긴다. 기준 프레임은 `belt_view_frame`(`pharmacy/belt_end`, +z 위)이다.
      x(진행 방향)로 `belt_view_offset_m` 만큼 옮긴 점의 +z `belt_view_standoff_m` 위에 카메라를 두고 내려다본다.
      그 뒤에 온 검출만 쓴다(기존 max_age 규칙). 피드백 이름은 `view` 다(관측 자세 이동).
    - 순서: 인터락(계약 5절) → `PICK_ATTEMPT` → 관측 이동(`view`) → 검출 대기. 이벤트 순서는 바뀌지 않는다.
    - 프레임이 없으면 팔을 안 움직이고 `not_detected` 로 닫는다. QR 이 주문과 다르면 `qr_mismatch` 다(계약 2.3).
      이동 실패는 기존 이동 실패와 같게 닫는다. `tool_frame` 이 필요하다.
    - 관측 자세에서 검출은 **광선 ∩ 봉투 윗면**(관측 프레임 z + `pouch_height_m`)으로 놓는다. 검출기의 고정 거리는 광선 방향에만 쓴다.
  - 선택(opt-in) 상판 관측 자세 `deck_view_standoff_m`(`0.0` = 끔). 침상 상판 픽 전에 집을 칸 프레임 위에서 내려다본다.
    `deck_pick_from_frame` 이 켜져 있으면 쓰지 않는다.
  - 선택(opt-in) 재관측 `refine_view_standoff_m`(`0.0` = 끔). 관측 자세의 첫 검출(QR 을 못 읽어도 봉투 상자)로 자리를 잡고,
    그 위 이 거리에서 봉투 방향으로 다시 내려다본 뒤 QR 로 고른다(피드백 `refine`). 첫 검출이 없으면 재관측 없이 기다린다.
    - 홈 자세의 손 카메라가 벨트 끝을 못 보는 구성에서 카메라 검출(`pouch_detector`)을 쓰려고 둔다. **충돌 검증은 없다. L3 미확인.**
- M0609 선택(opt-in) 보충 전 약통 확인 `container_check`(`false`, QR·DB·카메라 계약 2.3). 켜면 잡기 직전(`grasp_pose` 도착 뒤, 닫기 전)
  `/m0609/hand_camera/tag_reads` 의 약통 QR(`cn-NNNN`, 도착 뒤 stamp)을 `container_read_timeout_s`(2 s sim) 기다리고
  `/orchestrator/check_container` 에 묻는다(`container_check_timeout_s` 2 s wall).
  - 못 읽음(`unreadable`)·시한 초과·서비스 없음(`check_timeout`)·거부(`expired` 등)면 **닫지 않고** `success=false` 로 끝낸다. 결과 `lot_id` 는 읽은 약통 ID 다.
  - 거부한 칸은 같은 epoch 에서 다시 고르지 않는다. orchestrator 의 보충 재시도가 다른 칸으로 이어진다.
  - 가드 모듈 경로(`v2_guarded_module_path` 의 module 칸)는 아직 이 확인을 거치지 않는다.
- **종료(`destroy_node`·SIGINT)는 리셋이 아니다**(orchestrator #111 과 같은 규칙). `arm`·`m0609_arm` 둘 다 `destroy_node` 가 먼저 `close()` 를 부른다.
  실행 중 `PickPouch`·`ScanTag`·`Refill` 은 대기·이동이 곧바로 끝나 abort 로 닫고(PickPouch outcome 은 `timeout`), 홈 복귀도 멈춘다.
  그 뒤로는 관절·그리퍼 명령과 이벤트를 내지 않는다. **그리퍼는 그대로 둔다** — M0609 는 캐니스터를 쥔 채 멈출 수 있고 로그 한 줄에 남긴다.
  재기동 때도 자동으로 열지 않는다(쥔 물체를 떨어뜨린다). 첫 `gripper/holding` 이 true 면 경고 한 줄을 남기고, 다음 보충이 시작에 그리퍼를 연다.
  전에는 `destroy_node` 만으로는 안 풀려 rclpy 종료·취소·sim 시한(60·90 s)·`/clock` 정지를 기다렸다.
- 순수 로직: `pick_permission.py` — 벨트 정지, 봉투 정지, AMR 도킹 완료 셋이 모두 참일 때만 픽.
- 순수 로직: `reset_fence.py` — 리셋 barrier 울타리(`ResetFence`)와 sim 정지 감시(`ClockWatch`). 두 팔 노드가 같이 쓴다.
- **리셋 barrier 울타리(계약 6절 0):** `RESET_BEGIN`(새 epoch)부터 같은 epoch 의 `RESET_DONE` 까지 관절·그리퍼 명령을 내지 않는다.
  실행 중 goal 은 멈추고(abort), 홈 복귀는 접고, finally 의 복귀도 시작하지 않고, 새 goal 은 거부한다. 초기 자세는 isaac 리셋이 되돌린다.
  `RESET_DONE` 에서 캐시를 버리고 `ClockWatch` 기준을 다시 잡는다(sim time 이 작아져도 멈춤으로 안 본다). 중복·이전 epoch 신호는 무시한다.
  명시적 cancel 이면 원래부터 홈 복귀를 시작하지 않는다(M0609 는 시작한다). `RESET_BEGIN` 없이 `RESET_DONE` 만 오면 기존 동작 그대로다.
- 순수 로직: `ur5_kinematics.py` — UR5 표준 DH 정기구학, 감쇠 최소자승 수치 역기구학, 관절 한계·해 선택 규칙.
  DH·관절 이름·관절 한계는 표준값이고 USD 자산과 다를 수 있다. **마스터에서 확인**한다. 현재 노드는 관절 이름·한계만 파라미터로 받으며, DH 는 `UR5_DH` 기본값을 쓴다. USD 와 다르면 DH 를 노드에 전달하는 코드 변경이 필요하다.
- 서버: `/<robot>/pick_pouch` (`PickPouch`, 60 s sim)
  - guard 는 계약 5절: `base/stopped` true 이고 1.0 s 이내, `source=BELT` 면 `belt.at_end` true 이고
    `belt.order_id == goal.order_id`. unknown 은 허가가 아니다
  - `hand_camera/pouches` 에서 QR 이 `order_id` 인 봉투를 고르고, optical frame → 팔 베이스 프레임
    변환은 `header.stamp` 의 TF 로 한다(계약 3절)
  - `outcome` 은 계약 2.3절의 일곱 값 중 하나. 인터락 위반은 수락 후 abort + `rejected_interlock` 이다
    (거부한 goal 에는 result 를 못 싣는다. 스텁 팔도 같다)
  - **결과를 돌려준 뒤에** 홈으로 간다. 콜백 안에서 복귀를 끝내면 `ARM_HOME` 이 `LOAD_DONE`·
    `ORDER_DONE` 을 앞질러 계약 2.6절 순서가 어긋난다. 복귀가 끝날 때까지 `at_home` 은 false 다
  - 내는 이벤트: `PICK_ATTEMPT`, `POUCH_PICKED`, `POUCH_LOADED`(상판) 또는 `POUCH_PLACED`(보관함), `ARM_HOME`
- 서버: `/<robot>/scan_tag` (`ScanTag`, 30 s sim)
  - 손 카메라를 `<zone>/tag` 에 대고 `tag_reads` 를 기다린다. 시한 안에 못 읽으면 `STATUS_UNREADABLE`
  - 인터락 위반은 abort + `UNREADABLE`, 못 읽은 것은 succeed + `UNREADABLE`. 스텁 팔과 같은 규칙이다
  - **끝나고 홈으로 가지 않는다.** 계약 2.6절에서 `AUTH_OK` 와 `POUCH_DETECTED` 사이에 `ARM_HOME` 이 없다

## 칸별 계획 캐시 파일 (`plan_cache_dir`)

`m0609_arm` 은 inventory 를 받으면 칸마다 보충 계획을 미리 푼다. 병원 18칸이 **73.6 s** 였다(9/23 측정,
기동 1분 52초 중). 장면·계획 입력·계획 코드가 같으면 답이 같으므로, 다 푼 뒤 파일 하나로 저장하고 다음
기동에서 읽는다. 순수 로직은 `plan_cache_file.py` 다(ROS 를 import 하지 않는다).

- **키**는 sha256 하나다. 답을 바꾸는 것만 넣는다. `scene_signature(scene)` 이다. `rail_select` 다. 칸마다 `cell_key` 다. 계획 입력도 넣는다. seeds, params, tcp, link_boxes, home, home_rail, module_limits, 관절 한계다. 계획 코드 네 파일의 sha 도 넣는다. 파일은 `scene_v2`, `module_path`, `m0609_kinematics`, `pick_plan` 이다. 워크셀 sha 와 씬 sha 는 inventory 를 거쳐 `scene_signature` 에 이미 들어 있다. 칸 고르기 `v2_seed` 는 넣지 않는다. 어느 칸을 고를지만 정한다.
  칸의 계획은 바꾸지 않는다.
- **자리**: `~/.cache/rokey_p3/plan_cache/<key>.pkl`. 파라미터 `plan_cache_dir` 이고 **빈 값이면 끈다**
  (그때 동작은 이 기능이 없던 때와 글자 그대로 같다). 저장소 밖이다 — 기계마다 다시 만들 수 있는 값이다.
  임시 파일에 쓰고 `os.replace` 한다.
- **무효화**: 키가 다르면 **읽지 않을 뿐 지우지 않는다**. 못 푼 칸(`steps` 가 None)은 저장하지 않아 다음
  기동에서 다시 푼다. 읽은 칸도 `PlanCache.load_plans` 가 `cell_key` 를 한 번 더 대조해 맞는 것만 넣는다.
  inventory 가 중간에 바뀌면 `refresh()` 가 하던 대로 메모리에서 비운다(파일은 그대로다).
  읽기·쓰기 실패는 회차를 멈추지 않는다 — 캐시가 없는 것과 같다.
- **로그**: `v2 계획 캐시 파일: 읽음 N/M key=<앞 12자>`(없으면 `없음`, 저장 뒤에는 `저장 N칸`).
  파일에서 칸을 전부 읽어 풀 것이 없어도 요약 두 줄과 latched `plan_cache` payload 는 그대로 나간다 —
  기다리는 쪽(`demo_v2` 의 `P3_ARM_READY`)이 그 줄을 본다.
- 파일은 pickle 이다. 사용자 홈 아래 우리 캐시에만 쓰고 읽으며, 키에 계획 코드의 sha 가 들어 있어 코드가
  바뀐 파일은 애초에 읽지 않는다.

L1 은 `test/test_plan_cache_file.py` 다("풀기 → 저장 → 읽기" 의 `steps` 가 새로 푼 것과 같은지 포함).

## m0609_arm

M0609 보충 팔. `ros2 run rokey_p3_manipulation m0609_arm`. 계약 2.1절 M0609 항목과 2.3절 `/m0609/refill`.

- 내는 것: `/m0609/arm/joint_command` (6개 position), `/m0609/gripper/command`, `/m0609/arm/at_home` (5 Hz), `/m0609/arm/plan_cache` (장면 v2 latched JSON), `/events` (`REFILL_DONE`)
- 받는 것: `/m0609/joint_states`, `/m0609/gripper/holding`, `/events` (`RESET_BEGIN` 이면 울타리를 닫고, `RESET_DONE` 이면 캐시를 버리고 goal 로 홈을 떠났으면 다시 복귀한다)
- 리셋 barrier 울타리는 UR5 와 같다(`RESET_BEGIN` 부터 같은 epoch 의 `RESET_DONE` 까지 명령 0건). 다른 점: barrier 를 지난 goal 은 finally 에서
  복귀하지 않고, `RESET_DONE` 뒤 새 `joint_states` 로 홈 밖이면 기존대로 스스로 복귀한다.
- 서버: `/m0609/refill` (`Refill`, 90 s sim). 인터락은 없다. M0609 는 고정이라 베이스가 없다. 조제실 스테이지의 레일 위 M0609 는 `rail_enabled` 로 켠다(아래 [레일 위 M0609](#레일-위-m0609-rail_enabled)).
- 순수 로직: `refill_sequence.py` — 슬롯별 waypoint 순서(선반 접근 → 잡기 → 들기 → 슬롯 접근 → 삽입 → 후퇴), 보간, 도착 판정. `test/test_refill_sequence.py` 가 L1 이다.
- v0 는 레일 없는 고정 스테이지의 **관절 waypoint 티칭**이다. 운영 노드는 목표 TCP 자세를 만들거나 IK 를 호출하지 않는다. Isaac `selfdemo` 의 Lula IK 로 waypoint 후보를 뽑을 수 있지만, 그 솔버는 이 ROS 노드의 실행 경로에 없다.
- 순수 로직: `clearance.py` — 팔·그리퍼와 장애물 사이 여유 거리. v1 teach 경로는 오프라인 표로(#168), v2 는 실행 중 계획의 해 고르기에 쓴다(`worst_clearance`, #177·#186). #144 FK 로 링크 collision bbox(`config/m0609_collision.yaml`, master02 자산에서 읽음)를
  월드 OBB 로 놓고 조제실 스테이지 박스(선반·조제기·투입구, layout.py 값을 옮김)까지 최소 거리를 잰다. bbox 가 convexHull 을 감싸서 표의 값은 실제 여유보다 작거나 같다.
  `python3 -m rokey_p3_manipulation.clearance config/m0609_rail_teach.yaml config/m0609_collision.yaml` 로 슬롯마다 표를 낸다. `test/test_clearance.py` 가 L1 이다(실습3 접촉 재현 포함).
- 순수 로직: `m0609_kinematics.py` — M0609 **명목** 기구학(정기구학, 야코비안, 감쇠 Newton 역기구학, 관절 한계·손목 특이점 검사).
  P2(`ROKEY_P2_B2` `56d8246`)에서 옮겼다(#144). v0·v1 에서는 노드가 실행 중에 IK 를 쓰지 않는다(v1 teach 의 IK 점은 오프라인으로 풀었고, 실행 중에는 TCP 속도 상한용 FK 만). v2 는 실행 중 계획에 IK·FK 를 쓴다.
  기본값은 blue URDF 명목값이다. TCP 오프셋은 그리퍼가 달라 기본값이 없다. 9/18 에 TCP = `link_6` z 0.19671 m 로 두고
  조제실 스테이지 selfdemo 실측 자세 9개의 FK 를 스테이지 TCP 목표와 대조했더니 1 mm 안이었다. `m0609_isaac_sim.urdf` 와 파일을 직접 대조하지는 않았다.
  `test/test_m0609_kinematics.py` 가 L1 이다.
  파라미터 `shelf_approach_joints`, `shelf_grasp_joints`, `slot_a_approach_joints`, `slot_a_insert_joints`, `slot_b_approach_joints`, `slot_b_insert_joints`, `home_joint_positions` (각 6개, 기본 0 = 아직 안 쟀다).
- 나머지 파라미터(기본값): `robot_id`(`m0609`), `joint_names`(`joint_1` 에서 `joint_6`), `home_tolerance_rad`(`0.05`), `waypoint_tolerance_rad`(`0.05`),
  `waypoint_timeout_s`(`10.0`), `joint_limits_low/high`(M0609 자산 한계: `joint_3` ±2.618 rad(±150°), 나머지 ±2π(±360°). sim README·master02 자산), `command_rate_hz`(`20.0`), `max_joint_speed`(`0.5`), `refill_timeout_s`(`90.0`, 계약 7절),
  `grasp_settle_s`(`0.5`), `release_settle_s`(`0.3`), `hold_timeout_s`(`2.0`), `open_loop`(`false`),
  `state_gap_grace_s`(`0.2`. 상태 수신 공백만큼 waypoint 시한을 뒤로 민다. 0 이면 예전처럼 공백도 시한에 센다).
- 결과 `lot_id` 는 지어내지 않는다. goal 에 lot 이 있으면 그대로 되돌리고, 없으면(지금 `Refill` goal 에는 없다) 빈 값이다. `REFILL_DONE` detail 도 lot 없이 `<item_id> slot <a|b>` 다.
  로트·유통기한 데이터는 orchestrator 재고 모듈 것이다(계약 2.1절 끝, 재고는 `dispenser.yaml` 선반 값). 그래서 orchestrator 의 "다르다" 경고가 정상 경로에서 나오지 않는다.
- 관절 한계: 보충을 시작하기 전에 이 슬롯이 갈 자세 넷(`shelf_approach`, `shelf_grasp`, `slot_<a|b>_approach`, `slot_<a|b>_insert`)과 `home_joint_positions` 를 한계와 비교한다.
  하나라도 밖이면 한 관절도 움직이지 않고 `success=false` 다. 로그 한 줄에 파라미터·관절·값·한계를 적는다(예: `slot_a_insert_joints joint_3=2.8000 가 한계 [-2.6180, 2.6180] 밖이다`).
  홈 복귀 목표가 한계 밖이어도 보내지 않는다. 경계값은 안이다. teach 값의 `joint_6` 이 실행마다 2π 갈리는 것(3.7457, -2.5352, -3.7749)은 모두 ±2π 안이라 통과한다.
  다른 자산이면 `joint_limits_low/high` 로 덮는다.
- 실패: 잡은 뒤 `hold_timeout_s` 안에 `holding` 이 true 가 안 되면, 이송 중(들기·슬롯 접근·삽입 자세에서 열기 전) `holding` 이 false 가 되면(낙하), waypoint 에 `waypoint_timeout_s` 안에 못 가면, 90 s 를 넘기면 `success=false`. 취소는 `canceled`.
- 홈 복귀: **성공·실패는 홈에 돌아온 뒤 결과를 낸다.** 결과 직후 `at_home` 이 true 라 orchestrator 의 다음 goal 은 홈에서 시작한다.
  돌아오는 동안은 goal 이 활성이라 `at_home` 이 false 다. 복귀가 시한 안에 안 끝나도 보충 결과는 바꾸지 않고(장착은 끝났다) 결과 뒤 다시 복귀한다.
  **취소는 결과를 곧바로 낸 뒤 간다.** orchestrator 의 drain·대체 goal 이 종결을 `cancel_wait_s`(10 s wall)까지만 기다리기 때문이다.
  복귀 시간은 대략 (후퇴 자세와 홈의 관절 차 최댓값) ÷ `max_joint_speed` 다. 계약 6절 2 가 M0609 홈·그리퍼·캐니스터를 isaac 리셋 범위에 넣지만,
  이 노드는 그와 별개로 리셋 중 끊긴 복귀를 되살리고 취소 뒤 리셋 전까지 홈 밖에 머물지 않으려고 스스로 홈으로 간다.
  goal 로 홈을 떠난 뒤 `RESET_DONE` 이 오면 새 `joint_states` 로 복귀를 다시 시작한다. 이미 홈이면 명령을 내지 않는다. `ARM_HOME` 은 내지 않는다(계약 2.6절에서 m0609/arm 은 `REFILL_DONE` 만).
- 닫힌 루프(기본 `open_loop:=false`)는 `/m0609/joint_states` 가 1.0 s 안에 없으면 관절 명령을 내지 않는다. 그래서 **joint_states 없이 띄우면 모든 `Refill` 이 `success=false`** 로 끝난다.
- `open_loop:=true` 면 `joint_states`·`holding` 없이 시퀀스를 낸다. 도착·낙하 판정을 건너뛴다. stub_sim 의 M0609 흉내도 브릿지도 없을 때만 쓴다.
- 마스터에서 확인할 것(9/17 저녁 기준. 이 절을 쓸 때 직접 보지 않았다. 출처를 적는다):
  - USD 조인트 이름 `joint_1`-`joint_6`: 확인([sim README](../../sim/README.md) 의 9/17 dof 줄).
  - 관절 한계: USD 는 `joint_3` ±150°, 나머지 ±360°([sim README](../../sim/README.md)). #107 부터 노드 기본값이 이 값이다(위 파라미터 목록과 "관절 한계" 항목).
  - waypoint 7개: master02 에서 한 세트를 티칭해 보충 2회가 성공했다(9/17 master02 관측). 값은 저장소 밖 파라미터 파일이다.
  - 그리퍼 `holding`: master02 보충이 성공했으니 왔다고 본다(판단, 토픽 출력은 미확인).
- **기종: M0609 기준으로 모든 것을 우선 설계한다**(재범 9/18, 병원 씬의 M0617 은 끈다). 계약·코드·이 README·이름·토픽은 `m0609` 다.
  배경: 9/17 master01 Isaac 병원 씬의 매니퓰레이터 prim 경로가 `/World/manipulator/m0617/…` 였다(재범 사진).

### 보충 한 번의 순서 (#99 기준)

| 순서 | feedback `phase` | 관절 목표(파라미터) | 그리퍼 | 실패 조건 |
| --- | --- | --- | --- | --- |
| 0 | (feedback 없음) | - | **열기 명령 1회**(쥔 채 재기동 대비, 이미 열려 있으면 무해) | 관절 한계 검사가 먼저다. 밖이면 이것도 안 낸다 |
| 1 | `to_shelf` | `shelf_approach_joints` | - | `waypoint_timeout_s` 안에 못 감 |
| 2 | `grasp` | `shelf_grasp_joints` | 닫기 → `grasp_settle_s` → `holding` true 대기 | `hold_timeout_s` 안에 `holding` 이 안 옴 |
| 3 | `lift` | `shelf_approach_joints` | 쥔 채 | 이동 중 `holding` false(낙하) |
| 4 | `to_slot` | `slot_a_approach_joints` 또는 `slot_b_approach_joints` | 쥔 채 | 낙하 |
| 5 | `insert` | `slot_<a\|b>_insert_joints` | 도착 확인 뒤 열기 → `release_settle_s` | 열기 전 낙하 |
| 6 | `retreat` | 4 와 같은 접근 자세 | - | 못 감 |
| - | (`REFILL_DONE` 발행) | - | - | - |
| 7 | (feedback 없음) | `home_joint_positions` | - | 못 가도 결과는 그대로, 결과 뒤 다시 복귀 |
| 끝 | 결과 `succeed`/`abort` | - | - | - |

- 성공·실패는 7(홈 복귀)을 마친 뒤 결과를 낸다. **취소는 그 자리에서 결과를 곧바로 내고 그 뒤 홈으로 간다.**
- 전체 시한 `refill_timeout_s`(90 s sim)는 1 부터 센다. 리셋 울타리(`RESET_BEGIN` 부터 같은 epoch 의 `RESET_DONE` 까지)에 걸리면 그 자리에서 멈추고 `abort` 하며 홈으로 가지 않는다. `RESET_DONE` 뒤 홈 밖이면 스스로 복귀한다.

### `at_home` 은 goal 수락 조건이 아니다

`/m0609/refill` 은 item_id·slot 값·활성 goal·리셋 울타리만 보고 수락한다. 계약 5절에 M0609 인터락이 없고, orchestrator 도 `/m0609/arm/at_home` 을 구독하지 않는다.
#99 로 "결과 뒤 복귀 중에 다음 goal 이 오는" 경로는 없어졌다(결과 = 홈 도착 뒤). `at_home=false` 인 채로 수락되는 경로는 둘 남는다.

- ② 홈 복귀가 `waypoint_timeout_s` 안에 못 닿아 홈 밖에 남은 경우. 다음 goal 은 그 자리에서 선반 접근을 시작한다.
- ③ `RESET_DONE` 뒤 스스로 복귀하는 중. 새 goal 이 그 복귀를 멈추고 그 자리에서 시작한다.

수락 조건으로 넣을지는 계약 결정이다(재범). 넣지 않은 이유: 홈이 티칭 전이거나 닿지 못하면 보충이 영영 거부된다.

### 실물 Isaac 에 붙이기

launch 는 이 노드를 띄우지 않는다. `ros2 run` 에 파라미터 파일을 준다. Isaac 쪽 띄우기·티칭 절차는 [sim README](../../sim/README.md) 의 M0609 보충 스테이지 절(4 티칭, 5 `Refill` 반복)을 따른다.

```bash
ros2 run rokey_p3_manipulation m0609_arm --ros-args --params-file /absolute/path/to/m0609_waypoints.yaml
```

```yaml
# 예시 파일이다. 관절값 0.0 은 자리표시다(노드 기본값 0 = "아직 안 쟀다"). master 에서 티칭한 값으로 바꾼다.
# 값은 저장소에 넣지 않는다. 실행 기록에 파일 경로와 sha256 을 남긴다.
m0609_arm:
  ros__parameters:
    use_sim_time: true
    max_joint_speed: 0.3          # master02 9/17 실행 값. 기본 0.5
    waypoint_timeout_s: 10.0      # 기본값
    home_joint_positions: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    shelf_approach_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    shelf_grasp_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    slot_a_approach_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    slot_a_insert_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    slot_b_approach_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    slot_b_insert_joints: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
```

- **teach 값 7개는 한 실행에서 나온 한 세트만 쓴다.** `joint_6` 은 실행마다 2π 만큼 다르게 나올 수 있다(9/17 master02 관측). 다른 실행의 값을 섞으면 waypoint 사이에서 `joint_6` 이 한 바퀴 돈다. 관절 공간 직선 보간이라 2π 를 줄여 주지 않는다.
- `use_sim_time: true` — 대기(`grasp_settle_s` 등)·시한은 sim time 이다(계약 4절). false 면 시작 때 경고가 나온다. `/clock` 이 멈추면 대기는 wall 상한(sim 초 + 4 s)에서 빠져나와 실패한다.
- `max_joint_speed`(rad/s, 기본 0.5) — 보간 한 점의 크기다(÷ `command_rate_hz`). 줄이면 느리고 부드럽다. 복귀 시간은 (후퇴 자세와 홈의 관절 차 최댓값) ÷ 이 값에 추종 지연을 더한 만큼이다.
- `waypoint_timeout_s`(sim, 기본 10) — 마지막 점을 낸 뒤 `waypoint_tolerance_rad`(0.05) 이내로 닿기를 기다리는 상한이다. 드라이브가 느리면(sim README: 강성이 낮다) 늘린다.
- master02 실측(9/17): 5d6a10b install, `max_joint_speed` 0.3 에서 orchestrator 보충 2회가 성공했다. `REFILL_REQUESTED` → `REFILL_DONE` 28.3 s, 27.35 s sim. #99 전 코드라 결과 뒤 복귀였고 lot_id 를 지어냈다.

- 스텁 한 바퀴에서 이 노드로 바꾸려면 `stub_loop.launch.py use_stub_m0609:=false` 로 stub_arm 의 `/m0609/refill` 을 끄고 이 노드를 따로 띄운다. launch 는 이 노드를 띄우지 않는다.
  stub_sim 이 `emulate_m0609`(기본 true)로 `/m0609/joint_states`·`/m0609/gripper/holding` 을 흉내 내므로 `open_loop` 없이 닫힌 루프로 돈다:
  `ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true`
- 검증: L1 은 `test/test_refill_sequence.py`(순서·보간), `test/test_m0609_refill_finish.py`(결과 전 홈 복귀·취소·lot_id), `test/test_reset_fence.py`(울타리). L2 는 `rokey_p3_bringup/test/test_m0609_loop.py` 다. stub_sim 흉내와 이 노드(`open_loop=false`)를 띄워
  `Refill` 성공과 `REFILL_DONE` 1건을 보고, 흉내를 끄면 같은 goal 이 실패하는지도 본다.
  orchestrator 의 `Refill` 클라이언트(#58)는 재고에 보충 요청이 있으면 `/m0609/refill` 을 부른다(orchestrator README 보충 절).

### 레일 위 M0609 (`rail_enabled`)

재범 결정(9/18): 9/21 시연의 보충은 조제실 스테이지(`sim/standalone/pharmacy_stage.py --preset demo-ros-refill`)의 2축 레일 위 M0609 를
orchestrator 가 `/m0609/refill` 로 구동한다. **레일은 `/m0609/refill` 안에 숨긴다.** orchestrator·계약 v1·액션 타입은 그대로다.

- 켜기: `rail_enabled:=true`. 끄면(기본) 레일 토픽을 만들지 않고 동작이 이전과 같다(아래 검증).
- 레일 토픽(**계약 v1 밖**, 스테이지 제안 이름, 9/18 표): 내는 것 `/m0609/rail/joint_command`(reliable, `rail_x`·`rail_y` m), 받는 것 `/m0609/rail/joint_states`(best effort, 30 Hz).
  스테이지는 명령을 드라이브 목표로 바로 넣고 보간하지 않는다. 이 노드가 궤적 점을 `rail_command_rate_hz`(50 Hz)로 낸다.
- 속도(재범 9/18, 실습1 "너무 느리다" → M0609 최고 속도의 80%. 재범 9/24 → 팔 관절·TCP 는 **90%**, 레일 축은 80% 그대로). 레일 모드에서만 쓰고, 레일 끔(v0)은 `max_joint_speed` 등속 그대로다.

  | 파라미터 | 기본값 | 출처 |
  | --- | --- | --- |
  | `rail_joint_max_speed` | 2.356, 2.356, 2.827, 3.534, 3.534, 3.534 rad/s | 최고 150/150/180/225/225/225 °/s 의 90%(9/24, 전 80%). USD `max_velocity`(실습1 로그 `demo18_stage.log` 485-490행)와 두산 M0609 사양이 같다(9/18) |
  | `rail_joint_max_accel` | 4, 4, 4, 6, 6, 6 rad/s² | 스테이지 쪽 제안(사양 근거 없음, 흔들림을 줄이려고 낮게, 판단) |
  | `rail_tcp_max_speed` | 0.9 m/s | 두산 TCP 1.0 m/s 의 90%(9/24, 전 80%). 관절 사다리꼴의 TCP 최고 속도(FK, `rail_tcp_offset_m` = link_6 z 0.19671)가 넘으면 속도 f·가속 f² 로 줄인다 |
  | `rail_max_speed`, `rail_max_accel` | 0.8, 0.8 m/s · 1.0, 1.0 m/s² | 레일 실물 없음, USD 무제한. 스테이지 쪽 제안 1.0 m/s 의 80%, 가속은 제안값 |
  | `rail_command_rate_hz` | 50 | 80% 속도에서 20 Hz 면 점 간격이 TCP 4.3 cm(스테이지는 점을 바로 드라이브 목표로 넣는다), 50 Hz 면 1.7 cm |

  - 궤적은 **동기화 사다리꼴**이다(`refill_sequence.trapezoid_points`). 모든 관절이 같이 출발·도착하고, 축마다 속도·가속을 넘지 않는다. 짧은 이동은 삼각형이다.
  - **점은 흐른 sim 시간에 맞춰 낸다**(`_stream`, 레일 모드 v1·v2). 점 i 는 시작 뒤 i × 주기에 낼 차례이고, `/clock` 이 한 번 오를 때마다 차례가 된 점 중 마지막 것을 낸다.
    예전에는 점마다 주기(0.02 s)를 기다렸다. Isaac `/clock` 은 계단으로 올라(physics_dt 1/60) 점 하나에 2틱(0.0333 s)이 들었다.
    실습7-a4 명령 stamp 간격 중앙값이 0.0333 s 였다(master02). 궤적이 설계의 1.67배였고, 설정 80% 가 실제로는 설정의 약 60%(최고 속도의 약 48%)였다.
    지금은 시계가 30·60 Hz 어느 쪽이어도 설계 시간이다(L1 `test_a_stream_takes_the_designed_time_on_a_stepped_clock`).
    상태가 끊겼다가 이어 가면 그 점부터 시간을 다시 센다(건너뛰어 튀지 않게). 레일 끔(v0)은 예전 그대로 점마다 기다린다.
  - 가감속 없이 속도만 올리지 않는다. `rail_joint_max_speed` 를 주고 `rail_joint_max_accel` 을 비우면(`[0.0]`) 기동하지 않는다. 둘 다 `[0.0]` 이면 `max_joint_speed` 등속이다.
- 상태 끊김(레일 모드): `joint_states`·`rail/joint_states` 가 stale(1.0 s, 계약 4절)이면 명령을 멈추고 `stale_grace_s`(3 s wall) 동안 다시 오기를 기다렸다가 이어 간다. 안 오면 실패다.
  Isaac 창 모드는 한 틱이 느리거나 timeline 복구 중에 세 상태 토픽이 같이 끊길 수 있다(9/18, 9/17 로그에 0.7 s 공백).
- 상태 구독 스레드(레일 모드): `joint_states`·`rail/joint_states`·`gripper/holding` 구독은 `m0609_arm_states` 노드에 있고 전용
  SingleThreadedExecutor 스레드가 돈다. 이 노드의 MultiThreadedExecutor 는 30 Hz 구독 콜백을 0.2-4 s 씩 늦게 한꺼번에 처리했다
  (9/18 docker: 발행은 30 Hz 그대로, 최소 rclpy 노드로도 재현, MultiThreaded 2·4·16 스레드 모두, SingleThreaded 0건).
  레일 끔은 이전처럼 이 노드에서 구독한다. 수신 간격이 `state_gap_warn_s`(0.2 s)보다 길면 `… 수신 공백 N s(wall)` WARN 한 줄을 남긴다(L3 에서 시한 근거를 모으려고).
- teach: `config/m0609_rail_teach.yaml`(설치 경로 `share/rokey_p3_manipulation/config/`, `rail_teach_file` 로 덮는다). 슬롯 a·b 마다 단계 목록이다.
  단계는 레일만(`rail`), 팔만(`joints`, 선택 `tolerance_rad`), 그리퍼만(`gripper`) 셋 중 하나다. 홈(`home.joints`·`home.rail`)도 이 파일 것을 쓴다(`home_joint_positions` 는 쓰지 않는다).
  값의 출처(실측·IK)는 파일 머리에 적었다. 기동 때 검사하고 틀리면 노드가 뜨지 않는다.
- 순서 규칙
  - 레일은 팔이 **접힌 자세**(홈 또는 `rail_safe_phases` = `raise`·`retreat`, 허용오차 안)일 때만 명령한다. teach 검사가 한 번, 명령 직전에 실제 관절값으로 한 번 더 본다.
  - 레일이 `rail_tolerance_m`(0.01 m) 안에 든 뒤에 팔이 움직인다. `rail_timeout_s`(10 s sim) 안에 못 가면 `success=false`(기존 실패 결과)다.
  - 도착·holding 확인은 sim 한 틱마다 본다(예전 0.05 s = 3틱). 레일 끔은 예전 그대로다.
  - 레일 단계는 앞 단계가 허용오차 안에 들었으면 그 목표에서 시작한다. 실제 값에서 시작하면 남은 오차(≤ 1 cm)가 섞여 x·y 단계에서 z 가 같이 움직였다(9/18 L2 5건 → 0건).
  - 그리퍼 없이 팔 이동이 이어지면 중간 자세에서 도착을 기다리지 않는다(예: `pull_out`, `inlet_front`, `retreat`). 다음 이동은 실제 관절값이 아니라 그 목표에서 시작해, 명령 경로는 계획의 꺾은선 그대로다.
    기다리는 곳: 잡기·놓기 앞, 레일 이동 앞(접힌 자세 검사), 단계의 마지막, 자기 허용오차가 있는 점(v1 투입구 0.0025 rad).
  - 결과 전 복귀까지 끝나면 단계별 sim 시간 한 줄을 남긴다: `Refill <item> 단계 시간(sim s, …): plan 0.00, rail_to_shelf_z 0.95, … 합 N`.
    마지막 단계 값에는 결과 전 홈 복귀가 들어 있다. 실습7-a4·7-b 에는 단계 시각 기록이 없어 시간을 나누지 못했다.
  - 팔이 도착했을 때 레일이 목표에서 밀려 있으면 WARN 한 줄(`<phase>: 레일이 밀려 있다 …`). 실패로 보지는 않는다. selfdemo 에서 insert 동안 레일이 `rail_y` 하한까지 밀렸다.
  - 잡기 뒤 놓기 전까지는 매 단계 뒤 낙하(`holding` false)를 본다.
- 홈 복귀: 팔이 접힌 자세면 레일 홈 → 팔 홈(스테이지 selfdemo 순서). 단계 중간에 끊겼으면 지나온 팔 자세를 거꾸로 되짚어 접힌 자세로 간 뒤 같은 순서다.
  레일이 선반 앞에 있을 때 홈 자세로 곧장 가면 팔이 선반에 닿을 수 있어서다(selfdemo: 홈 자세로 레일이 선반 쪽에 가다 막혔다, 판단). 성공·실패는 결과 전, 취소는 결과 뒤인 것은 같다.
- 시간(v1, 9/18 계산): 그때 기본(80%)에서 팔 11.4 s + 레일 4.9-5.3 s ≈ 17 s 에 settle 0.8 s·도착 대기가 더해진다(9/18 첫 판 0.3 rad/s 등속은 ≈ 44 s). `refill_timeout_s` 90 s 안이다. v2 실측은 아래 v2 절.
- 띄우기(스테이지는 [sim README](../../sim/README.md) 의 `demo-ros-refill` 절):

```bash
ros2 run rokey_p3_manipulation m0609_arm --ros-args -p use_sim_time:=true -p rail_enabled:=true
```

  기동 줄 `rail on. teach=… joints=['rail_x', 'rail_y'] home_rail=[0.0, 0.0] safe=['raise', 'retreat']` 로 확인한다.
- 검증: L1 `test/test_m0609_rail.py`(teach 검사, 접힌 자세에서만 레일, 레일 도착 대기, 레일 시한 초과 abort, 되짚기 복귀, 밀림 WARN, insert 허용오차, 레일 끔 회귀,
  사다리꼴 속도·가속·동기화, TCP 상한, 속도만 주면 거부, 상태 끊김 유예·수신 공백 WARN). Isaac 은 미실행이다.

### 레일 보충 v2 (`scene_version:=2`)

**모듈 기본 경로:** `v2_guarded_module_path`는 `scene_version:=2`, `use_sim_time:=true`,
`open_loop:=false`인 지원 환경에서 기본 **true**다.
모듈 파지 후 수평 운반, 전체 레일 경로 충돌 검사와 예상 이동시간 비교, LIN 진입/후퇴,
정지·파지·해제 관측을 사용한다. wall-clock 또는 open-loop의 기존 v2 실행은 기본 false로 유지한다.
지원 환경 밖에서 guarded true를 명시하면 노드 기동을 거부한다.
`tools/demo_v2.sh`는 기존 시연 경로를 명시적으로 선택한다(false).
새 경로를 시연 스크립트로 검증할 때만 `P3_V2_GUARDED_MODULE_PATH=true`로 선택한다.
`-p v2_guarded_module_path:=false`를 명시하면 기존 v2 경로로 돌아간다.
v0·v1에서는 기본 false이고 명시적인 true는 기동 오류다. `scene_version` 자체의 기본값은 계속 1이다.
기본값 변경 범위·복귀 명령은 [기본 활성화 검토](../../docs/analysis/2026-09-18-jaebeom-module-default-code-review.md)에 있다.
이 경로의 Isaac L3는 미실행이며 아래 기존 v2 실측 결과를 이 모드의 검증으로 사용하면 안 된다.
계산 예제·동작 차이·제조사 문서 검토·L3 절차는
[모듈 경로 검토](../../docs/analysis/2026-09-18-jaebeom-module-path-code-review.md)에 있다.
실기 순응 제어나 힘/토크 E-Stop은 구현하지 않았다. 실패하면 hold를 요청하고 RESET_DONE 전 자동 홈 복귀를 막는다.

**아래 기존 계획·단계·실측 설명의 범위:** 원통과 `v2_guarded_module_path:=false`로 실행하는 모듈.
기본 guarded 모듈의 자세·단계·시간은 위 모듈 경로 검토를 따른다.

재범 9/18: 레일 3축(x·y·z), 약통 2종(원통 `cylinder`·모듈 `module`), 선반 4개 16칸, 수납 2종(원형 수납통·조제기 모듈 구멍),
5분 연속 투입, 선반 칸 랜덤 파지. 스테이지는 `--preset demo-ros-refill-v2`(#170). **새 파라미터로만 켜진다.** 기본값(`1`)·#165 레일 모드·레일 끔은 그대로다.

- 기하는 스테이지가 준다: `/m0609/shelf/inventory`(std_msgs/String JSON, reliable + transient_local, depth 1, 계약 v1 밖).
  칸(약통 중심·종류·있음), `items`(item → 종류), 수납 자세, 장애물 박스, 레일 이름·한계·원점. 치수는 하드코딩하지 않는다(박세준 실제 USD 로 옮기면 바뀐다).
- goal 하나: item → 종류 → 칸 시드 랜덤(`v2_seed`, 매 선택을 로그: seed·draw·kind·cell·후보 수) → 계획 → 레일 단계 실행(#154·#165 의 안전 규칙·속도·되짚기 그대로).
  slot 은 수납 위치를 정하지 않는다(종류가 정한다, 스테이지 쪽과 합의). 결과·로그에만 남는다.
- 계획(`scene_v2.py`, 순수): 잡기·넣기 자세를 teach 대신 #144 IK 로 실행 중 푼다.
  - 모두 **앞 접근**(공구 +y, 손가락 x 로 닫힘). 위에서 잡은 모듈은 +y 구멍에 못 넣는다(닫힌 손가락 ±0.053 > 구멍 ±0.04).
  - 원통은 윗면 2 cm 아래를 앞에서 잡아 원형 수납통에 중심이 테두리 1 cm 아래로 들어간 곳에서 놓는다(손가락은 테두리 1.5 cm 위).
  - 모듈은 중심 4 cm 앞을 잡아 중심이 앞면을 2 cm 넘은 곳에서 놓는다(손가락 끝은 앞면 2 cm 밖).
  - **레일 자세는 구간(잡기·넣기)마다 한 번 정한다**(재범 실습7-a: "레일이 먼저 집을 수 있는 최적 위치로"). 후보를 **어깨 → 목표 거리가 짧은 순**으로 시험해
    처음 제약을 모두 만족한 것을 쓴다. 제약: 레일 한계에서 5 cm 안쪽(자르지 않고 뺀다), IK, 여유 거리 1 cm 이상(레일 부품 포함), 도달 0.40 m 이상.
    후보(`rail_pick`·`rail_round`·`rail_module`)는 오프라인 전수 탐색에서 칸 종류·수납마다 처음 통과한 자세들이다. 베이스가 약통보다 30-35 cm 낮다.
  - **레일은 접힌 자세(홈 = `fold`·`fold_back`)에서만** 움직이고, 구간이 끝날 때까지 다시 움직이지 않는다. 레일 이동은 단계로 나뉜다: 오를 땐 z 먼저 → x·y,
    내릴 땐 x·y 먼저 → z(`rail_to_shelf_z`·`rail_to_shelf_xy` 등). 결과 뒤 복귀도 같다.
  - **레일 부품**(재고 JSON `rail.parts`: 트랙·Y 빔·받침·Y 캐리지·승강판·승강 기둥)을 레일 자세만큼 옮겨 여유 장애물에 넣는다(바닥 아래는 자른다). 스테이지에서
    대부분 collision 이 없어 Isaac 이 막지 않는다(실습7-a "M0609 가 레일을 관통"). base_link 만 뺀다(승강판 위에 붙어 있다).
  - IK 시드 여러 개의 해 중 여유가 가장 큰 것을 쓴다. 넣기 구간은 칸 위치와 무관해 종류마다 한 번만 푼다.
  - 잡은 약통↔자기 수납(RoundBin*·DispenserFront*)은 여유에서 빼고 치수(지름 < 안지름, 단면 < 열림)로 본다.
  - 계획은 `refill_sequence.validate_plan` 으로 teach 와 같은 규칙을 다시 검사한다.
  - 바닥 선반 받침 0.30 이던 장면(`6543ec4`)에서는 아랫단 4칸(약통 z 0.36)이 통과 자세가 없었다(link_2 ↔ 승강판·선반 옆판·윗판).
    재범 결정으로 받침을 0.55 로 올렸다(`c40c3f3`, 약통 z 0.61/0.91/1.24/1.54). 이제 16칸 모두 통과한다. 계획 없는 칸이 생기면 처음부터 고르지 않는다.
- **기동 캐시**: inventory 를 받으면 별도 스레드가 칸마다 계획을 미리 풀어 둔다(`PlanCache`, #186).
  - 장면(장애물·수납·레일)이 바뀌면 전부 버린다. 칸의 종류·중심·크기가 바뀌면 그 칸만 다시 푼다.
  - 넣기 구간은 종류마다 한 번 풀어 칸끼리 같이 쓴다.
  - 못 푼 칸도 이유와 함께 넣어 두고, goal 에서 처음부터 고르지 않는다(`v2_max_skips` 를 쓰지 않는다).
  - 끝나면 한 줄: `v2 계획 캐시: 16/16칸 풀림, 전체 N s, 칸당 a-b s. 못 푼 칸 {}`.
  - master02 실측: 67.8 s(실습7-a4), 75.7 s(7-a5), 83.7 s(실습8), 모두 16/16.
  - goal 이 캐시 전에 오면 그 칸을 그 자리에서 푼다. 로그에 `계산 N s` 로 남는다.
- 칸: 16칸이다. 바닥 선반 둘(`floor_left`·`floor_right`, 2×2)에 원통 8, 위 선반 둘(`upper_left`·`upper_right`, 2×2)에 모듈 8.
  수납은 원통 → 원형 수납통(`round`, 안지름 0.12 m, #198. 이전 0.10), 모듈 → 조제기 앞면 구멍(`module`).
- feedback 에 `plan cell=<칸> kind=<종류> seed=<n> draw=<n>` 한 줄을 낸 뒤 단계 이름이 이어진다.
  원통 16단계: `rail_to_shelf_z`·`rail_to_shelf_xy` → `shelf_front`·`grasp_pose`·`grasp`·`lift`·`pull_out`·`fold` → `rail_to_inlet_z`·`rail_to_inlet_xy` →
  `inlet_front`·`above_inlet`·`insert`·`release`·`retreat`·`fold_back`. 모듈은 `above_inlet` 이 없는 15단계다. 레일 단계는 오를 땐 z 먼저, 내릴 땐 xy 먼저라 순서가 바뀐다(예: 위 선반 → 구멍은 `rail_to_inlet_xy` → `rail_to_inlet_z`).
- `REFILL_DONE` detail(v2): compact JSON 한 줄(`scene_v2.refill_done_detail`, 9/18, 계약 2.6절의 판정에 안 쓰는 메모).

  | 필드 | 뜻 |
  | --- | --- |
  | `item` | goal 의 item_id |
  | `slot` | `a`·`b`(goal 의 slot, 수납 위치는 정하지 않는다) |
  | `kind` | `cylinder`·`module` |
  | `cell` | 고른 칸(예: `floor_left/r0c0`) |
  | `target` | `round`·`module` |
  | `seed`·`draw` | 칸 랜덤 시드와 몇 번째 뽑기 |
  | `clearance` | 계획의 최소 여유(m, 소수 넷째 자리) |
  | `lot` | goal 에 lot 이 있을 때만 |

  예(실습8): `{"item":"drug-amox","slot":"a","kind":"cylinder","cell":"floor_left/r0c0","target":"round","seed":7,"draw":4,"clearance":0.0108}`.
  웹 백엔드가 이 줄을 읽어 "마지막 보충" 을 보여 준다(#176).
- 연속 구동기 `refill_soak`: `/m0609/refill` goal 을 `duration_s` 동안 연달아 보낸다.
  - item·slot 은 시드 랜덤이다.
  - 줄마다 시각·item·slot·종류·칸·결과·소요 s 를 적고, 끝에 요약을 낸다(`out_file` 이면 JSONL).
  - 종류·칸은 팔 feedback 의 `plan …` 줄에서 읽는다(`soak_report.py`, 순수).
  - orchestrator 와 같이 띄우지 않는다(같은 액션을 두 클라이언트가 부른다).
  - 파라미터(기본값): `duration_s`(300.0 wall), `item_ids`(`['drug-ibu']`), `slots`(`[0, 1]`), `seed`(0), `goal_timeout_s`(120.0 wall, 넘으면 cancel 하고 실패로 센다), `server_wait_s`(30.0), `out_file`(빈 값).
  - 실습7-b 명령:

  ```bash
  ros2 run rokey_p3_manipulation refill_soak --ros-args -p use_sim_time:=false -p duration_s:=300.0 \
    -p "item_ids:=['drug-amox','drug-ibu']" -p seed:=3 -p goal_timeout_s:=120.0 -p out_file:=$HOME/markle_tmp/soak_v2.jsonl
  ```

- 파라미터(기본값): `scene_version`(1), `inventory_topic`(`/m0609/shelf/inventory`), `v2_rail_joint_names`(rail_x·rail_y·rail_z), `v2_rail_max_speed`(0.8 ×3), `v2_rail_max_accel`(1.0 ×3),
  `v2_seed`(0), `v2_ik_seeds`(12), `v2_min_clearance`(0.01), `v2_max_skips`(3), `v2_collision_file`(설치된 `config/m0609_collision.yaml`),
  `v2_guarded_module_path`(v2·sim time·closed-loop에서는 true, 그 외 기본 false; 시연 스크립트는 false를 명시),
  `v2_rail_select`(`first_feasible`, 아래 [레일 후보 선택](#레일-후보-선택-노드-기본과-시연-기본)), `plan_cache_dir`(`~/.cache/rokey_p3/plan_cache`, 빈 값이면 끔),
  `container_check`(`false`), `container_tag_topic`(`/m0609/hand_camera/tag_reads`), `container_read_timeout_s`(`2.0`, sim), `container_check_timeout_s`(`2.0`, wall).
  팔 관절 속도·가속·TCP 상한·명령 주기·settle 은 v1 레일 표와 같은 파라미터다. 계획 제약(`scene_v2.DEFAULT_PARAMS`)은 파라미터가 아니고 코드 값이다.

  | 계획 값 | 기본 | 뜻 |
  | --- | --- | --- |
  | `min_reach` | 0.40 m | 어깨 → 목표 거리가 이보다 짧은 레일 자세는 쓰지 않는다 |
  | `rail_limit_margin` | 0.05 m | 레일 한계에서 이만큼 안쪽이어야 한다(자르지 않고 후보에서 뺀다) |
  | `min_clearance` | 0.01 m | 경로 최소 여유. 노드는 `v2_min_clearance` 로 덮는다 |
  | `max_rail_tries` | 8 | 구간마다 시험할 레일 후보 수 |
  | `cylinder_grip`·`module_grip` | 0.02·0.04 m | 원통 윗면 아래·모듈 중심 앞 잡는 곳 |
  | `round_sink`·`module_push` | 0.01·0.02 m | 원형 수납통 테두리 아래·구멍 앞면을 넘는 넣기 깊이 |
  | `approach`·`lift`·`hover`·`retreat` | 0.20·0.03·0.04·0.12 m | 접근·들기·넣기 위·후퇴 거리 |

- 실측(master02, 저장소 밖 로그):

  | 실습 | 트리 | 결과 |
  | --- | --- | --- |
  | 7-a4 | `801ee52`(main `96158eb` + #188 + #190) | goal 4/4, `rail_overlap` 0, "레일이 밀려" 0, 팔 동작 중 레일 명령 0 |
  | 7-a5 | `a39546f`(main `9f7ed04` + #195) | goal 4/4(카메라 세 뷰), `rail_overlap` 0, 로봇↔`Room` touch 0. 원통 넣기 때 원형 수납통 벽 접촉(0.10 시절) → #198 |
  | 7-b | `a94f06e`(main `1f2fabb` + #197 + #198) | `refill_soak` 300 s: 7/7 성공, 평균 46.37 s·최대 50.68 s(wall), 원통 39.3-43.0 s·모듈 49.2-50.7 s. `rail_overlap` 0, "레일이 밀려" 0, 수신 공백 최대 0.32 s |
  | 8 | 7-b 와 같다 | orchestrator 보충 3회 완주. `REFILL_REQUESTED` → `REFILL_DONE` 46.4-52.4 s, → `DISPENSER_RESUMED` 7.5-9.4 s 더(sim). 원통↔`RoundBin` touch 0.0076·0.0046 뿐 |
  | 9 | `10c8e83`(#228 **전**) | 보충 45.5 s. 위 7-b·8 과 같은 범위다 |
  | 10 | `419b20b`(#228 **포함**, master01) | `REFILL_REQUESTED` → `REFILL_DONE` 18.60-21.27 s(다른 한 건 29.70 s 는 앞 보충을 기다린 시간이 들어 있다). 단계 시간 합 21.47(원통 16단계)·23.68(모듈 15단계)·25.02 s. 수신 공백 0.20-0.23 s |
  | 11 | `2c68b73` | 증거 실행 보충 21.33-23.05 s, 확정 대본 18.70-21.35 s |

- 보충 한 번의 시간(#228 앞뒤)
  - #228 전: 원통 약 40-46 s, 모듈 약 46-52 s(실습7-b·8·9). 원인은 명령 점 간격이 시계 계단에 묶인 것이었다(위 레일 절 "점은 흐른 sim 시간에 맞춰 낸다").
  - #228 뒤: `REFILL_REQUESTED` → `REFILL_DONE` 18.6-21.4 s(실습10·11). 계획 기준 이론값(계산, 현재 테스트 장면, 80% 속도 사다리꼴)은 이동만 원통 16-18 s, 모듈 19-22 s 에 그리퍼 대기 0.8 s 다.
  - **단계 시간 로그의 합은 `REFILL_REQUESTED` → `REFILL_DONE` 보다 크다.** `REFILL_DONE` 은 마지막 단계 끝(`_run_refill`)에서 나가고, 결과 전 홈 복귀는 그 뒤에 돈다.
    복귀가 마지막 단계 값에 들어가 실습10 에서 약 3.7 s 차이였다(예: 꼬리 `insert 0.85, release 0.30, retreat 0.87, fold_back 6.10` 의 `fold_back` 은 fold_back 이동 + 복귀다).
  - `DISPENSER_RESUMED` 는 `Refill` 결과 뒤에 나오고, 결과는 홈 복귀 뒤에 나온다(위 홈 복귀 규칙).
- 알려진 문제
  - 레일 부품 대부분에 스테이지 collision 이 없다. 그래서 겹침은 계획의 여유와 스테이지의 `rail_overlap` 기록으로만 본다(실습7 P15).
  - 계획 값의 근거는 조제실 스테이지 장면(받침 0.55, 원형 수납통 0.12)이다. 병원은 스테이지가 워크셀 실측 JSON(`P3_WORKCELL_LAYOUT`, 18칸)으로 inventory 를 낸다. 박세준 실제 USD 로 옮기면 후보(`rail_pick` 등)를 다시 찾아야 할 수 있다.
  - 보충 중 리셋이면 goal 을 취소한다(실습8: `Refill drug-amox: 취소됨. grasp_pose: 이동 실패`). 잡은 약통은 스테이지 리셋이 되돌린다.
- 9/21 뒤 과제(9/18 에 적은 순서 그대로. 처리 여부는 이 README 에서 추적하지 않았다)
  1. orchestrator 상태 구독 분리(`feat/orchestrator-state-subscriptions`, PR 없음)를 #185 A2 기준으로 다듬는다.
     수신 노드는 monotonic 수신 시각과 짧은 lock 아래 snapshot 교체만 한다. EventsExecutor 로 바꾸지 않는다. 이 노드의 v2 L2 수신 공백 표본(0-0.59 s)을 근거로 붙인다.
  2. orchestrator·`arm`·`m0609_arm` `main()` 종료 경로 점검. rclpy 7.1.11 `Executor.shutdown` 이 진행 중 callback 을 기다리지 않는다(#189). 지금은 `close()` 가 먼저 돈다(#111·#113·#121).
- 검증: L1 `test/test_scene_v2.py`(같은 시드 같은 순서, 종류·있음 필터, IK 해 고르기·여유 부족 거부, 계획의 레일 z 안전 순서, 건너뛰기, 캐시, 16칸 모두 계획, 레일 한계 5 cm, detail 왕복, 구동기 요약). 장면은 `test/data/pharmacy_v2.json`(`3f20086` 의 `pharmacy_layout_json.py --scene v2`, 받침 0.55·원형 수납통 안지름 0.12, #200). Isaac 은 위 실측 표.

### 레일 후보 선택: 노드 기본과 시연 기본

기본값이 두 곳에서 다르다.

| 어디 | 기본값 | 근거 |
| --- | --- | --- |
| `m0609_arm` 노드 파라미터 `v2_rail_select` | `first_feasible` | `m0609_arm_node.py`. `ros2 run` 으로 값 없이 띄우면 이 값이다 |
| `tools/demo_v2.sh` 의 `P3_V2_RAIL_SELECT` | `preferred_first` | #797(v1.1.0)에서 기본으로 켰다(재범 9/29 "디폴트로 켜서"). 되돌리려면 `P3_V2_RAIL_SELECT=first_feasible` |

- `preferred_first` 는 #391(9/21 머지, `914d23d`)이 넣은 모드다. M0609 가 선반 앞에 바짝 붙어 팔을 깊게 접고 비틀어 집던 자세를 피하려고 넣었다(#391 본문).
- 9/21 이 모드는 opt-in 이었다. v1.0.0(`a5d1107`)의 `demo_v2.sh` 에는 `P3_V2_RAIL_SELECT` 가 없어 노드 기본 `first_feasible` 로 돌았다. 9/29 영상의 비틀기는 그 구성에서 나왔다.
- 근거는 실습21(9/21, 빈월드, master01, `6246bde` + `v2_rail_select:=preferred_first`)이다. 보충 79회(module 40·cylinder 39) 중 ok 78 이다.
  실패 1건은 Isaac 창이 닫힌 0.942 s 뒤에 났다. 놓은 뒤 약통 낙하가 2건(둘 다 module) 있었다(#240 5754620387).
- v1.1.0 커밋으로 돌린 acceptance 회전은 없다. 병원 워크셀에서 이 모드로 돈 보충 수는 이 README 에서 확인하지 않았다(미확인).

`preferred_first`는 오프라인 선호 후보를 먼저 검사한다. open-loop로 켤 수 없다. `mission_cost`는 지원하지 않는 값이다.

- `first_feasible`은 extra 후보와 `min_elbow_sin`을 읽지 않는다. guarded module 계획기도 기존 경로를 쓴다.
- `preferred_first`의 팔꿈치 기준은 IK 해마다 여유 순위를 매기기 전에 적용한다.
  여유가 가장 큰 해 하나를 먼저 고른 뒤 탈락시켜 같은 레일의 유효한 해까지 버리지 않는다.
- 새 모드는 홈→선반(빈 손), 선반→수납(파지), 수납→홈(빈 손)의 레일 이동을 1 cm 간격으로 검사한다.
  레일 부품 위치도 표본마다 갱신한다. 운반 중 약통에는 삽입 때의 접촉 예외를 적용하지 않으며,
  최소 여유는 `max(canister_min, min_clearance)`다.
- 직행이 막히면 양 끝보다 높은 z 경유점을 10 cm씩 올려 시도한다(축 상한의 기존 여유 안쪽까지).
  각 우회 구간 전체가 검사에 통과해야 선택한다. 유효한 경로가 없으면 다음 후보를 검사하거나 계획을 거부한다.
  넣기 캐시는 검사한 출발 레일 위치와 홈 위치를 포함한다. 검사한 복귀 단계도 계획에 넣으므로
  이 모드의 `REFILL_DONE`은 레일 복귀 뒤다. 기본 모드의 이벤트 순서는 그대로다.
- 실행 전에는 빈 손과 팔·레일 홈의 신선한 관측을 확인한다. 레일 명령을 내는 동안과 도착 대기 중에도
  팔이 접혀 있는지 계속 확인한다. 이탈·상태 소실·시한 초과 등 실행 실패 시 관측한 위치로 hold 명령을 내고,
  그리퍼 상태를 유지하며 새 보충과 자동 되짚기·홈 복귀를 막는다. `RESET_DONE`이 fault를 해제한다.
  hold 명령 발행은 물리 정지의 증거가 아니다.

`test_preferred_safety.py`는 실습20-B 좌표의 직행 충돌과 검사한 우회, 팔꿈치 해 선택, 캐시 출발점 구분,
이동·도착 대기 중 자세 이탈과 상태 소실, 실패 시 파지 유지·재시도 금지·리셋 경계를 검증한다.
장면 모델의 오프라인 검사이며 Isaac L3 성공을 뜻하지 않는다. 실습20-B에서 y가 멈춘 직접 원인과
접촉 전후 관절 시계열은 여전히 현장 확인 대상이다. 배포 전 같은 조건의 A/B 보충 12회 이상 전부 성공과
사람의 승인이 필요하다(#391 에 적은 조건). #797 은 임재범 결정(9/29)으로 시연 기본을 켰다. 이 조건의 A/B 12회 기록은 이 README 에서 확인하지 않았다(미확인). 기존 PR의 성능 표는 이 우회·복귀 경로를 포함하지 않으므로 새 모드의 수치로 재사용하지 않는다.
