# 계약 v1 구현 현황 (11절·3절)

이 문서는 계약 11절·3절의 조항별 PR 지도다. 지금 한 바퀴 구성은 [시스템 그림](system-overview.md)과 [ROS 2 통합 표](ros2-integration-table.md)에 있다.

- 대상: [배송 한 바퀴 계약 v1](delivery-contract-v1.md)의 11절(컨베이어↔팔 경계)과 3절(놓는 곳 프레임, 경유 zone·토폴로지, 병원 zones).
- 기준: main `f316197`(v1.1.0). 2026-09-30 에 파일·시험 이름, launch 기본값, `tools/demo_v2.sh` 가 켜는지를 코드에서 다시 대조했다. 처음 판은 `d3a1fda`(2026-09-20)였다.
- 이 문서는 조항마다 어느 PR 이 무엇을 구현했는지만 모은다. 계약 본문의 조항은 여기서 바꾸지 않는다.
- 상태: 현황 기록이다. 계약의 결정이 아니다. 계약 상태는 그대로 `proposed` 다.
- 켜는 인자와 짝은 [L3 스택 기동 조합](../runbooks/l3-stack-combos.md) 3절과 같다.
- v1.1.0 에서도 11절 opt-in 인자는 전부 기본 꺼짐이다(launch·노드 기본값). `tools/demo_v2.sh` 는 하나도 켜지 않는다.
- 예외 둘은 인자 대신 preset·기동 기본이 켠다.
  - 11.1 (a) 의 `--ur5` 는 스테이지 preset `hospital`·`emptyworld-loop` 이 켠다(`pharmacy_stage.py` PRESETS).
  - 11.1 의 점유 유지(fail-closed 일부)는 병원 탁자 정착 모드가 켠다. 그 모드가 v1.1.0 병원 카메라 기본이다.

## 읽는 법

| 칸 | 뜻 |
| --- | --- |
| 생산자 | 관측이나 동작을 만드는 쪽의 PR |
| 전달 | Isaac JSON ↔ ROS 변환(isaac_adapter) 같은 중간 PR. 필요 없으면 "—" |
| 소비자 | 그 관측으로 판정하는 쪽의 PR. 없으면 "없음" |
| 켜는 인자 | "기본"은 인자 없이 도는 동작이다. 나머지는 전부 기본 꺼짐(opt-in)이다 |
| L1·L2 | 시험 파일. CI 에서 돈다 |
| L3 | 마스터 Isaac 에서 켜 본 기록. #240 댓글 ID 가 있는 것만 적는다. 없으면 "미실행"이다. 11절 opt-in 가운데 L3 기록이 있는 것은 벨트 관측의 생산·전달뿐이다(실습15b, 11.6). 2026-09-30 에 #240 을 opt-in 이름으로 다시 찾았다 |
| 근거 | "코드" = 코드로 확인했다. "본문" = PR 본문의 설명만 옮겼다. 인자·파일 이름은 v1.1.0 코드에서 다시 찾았다 |

## 11절 컨베이어↔팔 경계

### 11.1 `/pharmacy/belt` 의 뜻과 한계

| 조항 | 생산자 | 전달 | 소비자 | 켜는 인자 | L1·L2 | L3 | 근거 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `at_end` 래치, sim_sensor 모드(현재) | 기존 stage. 특성 고정 #241·#248 | 기존 adapter | 기존 orchestrator | 기본 | `sim/tests/test_pharmacy_belt_characterization.py` | 기본 경로는 9/20 L3-1 에서 돌았다. 병원 경로 벨트(끝 롤러)는 회전 7 의 장면 ③ 으로 돌았다(#771 5867873681, protocol v4 §4(a)③). 이 조항만 따로 잰 기록은 없다 | 본문 |
| 병원 탁자 정착 모드의 `at_end`(A1 모듈 탁자 윗면, 정착 1 s) | #796 stage(`--hospital-receiver-prim`) | 기존 adapter | 기존 orchestrator | 병원 카메라 기본(`P3_HOSPITAL_RECEIVER_PRIM`, `tools/demo_v2.sh`, #797). 빈 값을 주면 끈다 | `sim/tests/test_route_belt.py`(receiver 모델), `sim/tests/test_hospital_nav.py`(receiver 자리) | 원 회차 05b8e28 bed_a1 1건([실습 45](../practice/simworld/practice-45.md)). 7860b4c·f316197 통합본은 미실행(#772 5891599172) | 코드 |
| 속도 미수신은 정착 표본이 아니다(목표) | #252 | — | — | 스테이지 `--belt-fail-closed` | `test_pharmacy_belt_fail_closed.py`, 벡터 옵션 `speed_missing_resets_settle`(`test_pharmacy_contract_vectors.py`) | 미실행. 실습15b 에서 켜졌지만 발동 상황이 없었다(#240 5746557646) | 본문 |
| 점유 해제 (a) 실제 팔이 쥐고 벨트 밖 | #251 | — | — | 스테이지 `--ur5`. preset `hospital`·`emptyworld-loop` 은 기본으로 켠다 | `test_pharmacy_ur5_held.py` | 조항만 따로 잰 기록 없음(미실행) | 본문 |
| 점유 해제 (b) 스텁 `pick_notice`·stand-in | 기존 stage. `--ur5` 에서는 stand-in 기동 거부·`pick_notice` 는 세기만(#244) | 기존 adapter | — | launch `pick_notice` 기본 true. 병원·빈월드 기동은 `pick_notice:=false` 를 준다(`tools/demo_v2.sh`) | `test_pharmacy_ur5_guard.py` | 기본 경로는 L3-1 에서 돌았다 | 본문 |
| 점유 해제 (c) 리셋 barrier 회수 | 기존 stage | 기존 adapter | 기존 orchestrator | 기본 | 기존 시험 | 기본 경로는 L3-1 에서 돌았다 | 본문 |
| 소실·이탈 때 점유 유지(fail-closed, 목표) | #252. 병원 탁자 정착 모드는 #796 이 켠다(`pharmacy_stage.py` 1988행) | — | — | 스테이지 `--belt-fail-closed`, 또는 `--hospital-receiver-prim`(병원 카메라 기본) | `test_pharmacy_belt_fail_closed.py` | 미실행. 실습15b 는 켰지만 소실이 없었다(`pouch_lost` 0줄, #240 5746506532) | 본문, 코드(receiver) |

### 11.2 `/pharmacy/dispense` 재전송

| 조항 | 생산자 | 전달 | 소비자 | 켜는 인자 | L1·L2 | L3 | 근거 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 같은 재전송은 `accepted=true`, `DISPENSED` 재발행 없음 | #264(기본 변경) | #247(기본 변경) | 기존 orchestrator | 기본 | `test_pharmacy_dispense_resend.py` | 재전송 관측 없음(미실행) | #247 코드, #264 본문 |
| 해제 뒤 늦은 재전송 구별 | 범위 밖(9/21 뒤 메시지 변경) | — | — | — | — | — | 계약 본문 |

### 11.3 다음 배출 허가

| 조건 | 생산자 | 전달 | 소비자 | 켜는 인자 | L1·L2 | L3 | 근거 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `occupied=false`(신선). 현재 기본은 이것만 본다 | 기존 stage | 기존 adapter | 기존 orchestrator | 기본 | 기존 시험 | 기본 경로는 L3-1 에서 돌았다 | 코드 |
| 새 관측으로 조합한 허가(guard) | 벨트 관측 #276, 팔 통로 #282 | #279 | #290 orchestrator `observation_guard` | launch `observation_guard:=true`(**시험용**, 기본 false) + 벨트 관측 짝 + `arm_clearance_enabled`. `tools/demo_v2.sh` 는 켜지 않는다 | `test_trip_fsm.py`, 벡터 `next_dispense.json`·`pick.json`(#261) + 트립 FSM 러너 | 미실행 | 코드 |
| 이전 `PickPouch` 가 `ok` 로 종결 | 기존 arm | — | #290(guard 가 마지막 벨트 픽 결과를 본다) | 위와 같음 | 위와 같음 | 미실행 | 코드 |
| 상판 칸 안착 확인(11.4) | #296 arm | — | **guard 는 보지 않는다** | 팔 `placement_check_enabled`(기본 false). 저장소 팔 params 파일 넷은 켜지 않는다 | N09 xfail(strict, `test_contract_vectors_trip_fsm.py`) | 미실행 | 코드(러너), #296 본문 |
| `arm_clear_of_belt=CLEAR`(신선) | #282 arm | — | #290 | 팔 `arm_clearance_enabled`(기본 false) + 기하 파라미터(기본값 없음) | `test_arm_clearance_node.py`·`test_arm_clearance_state.py` | 미실행. CLEAR 는 FK↔TCP 대조 전에는 믿지 않는다 | #290 코드, #282 본문 |

### 11.4 `PickPouch` `ok` 와 새 outcome

| 조항 | 생산자 | 전달 | 소비자 | 켜는 인자 | L1·L2 | L3 | 근거 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 현재 `ok` = 놓기 명령 + 정해진 대기 | 기존 arm. 특성 고정 #246 | — | 기존 orchestrator | 기본 | `test_ur5_pick_characterization.py` | 조항만 따로 잰 기록 없음. 합본 UR5 집기는 회전 7 장면 ④ 로 돌았다(#771 5867873681) | 본문 |
| 칸 안착 확인(해제 확인 뒤 손 카메라 검출, 놓는 곳 프레임의 칸 상자 안, QR = goal `order_id`) | #296 arm. 해제 확인은 #291 | — | orchestrator 는 기존 `dropped` 처리(즉시 ABORT)를 쓴다 | 팔 `placement_check_enabled` + `gripper_observation:=state`(기본 `bool`). 기하·시한 기본값 없음 | `test_placement_check.py`, `test_ur5_pick_placement.py` | 미실행. 관측 자세 이동에 충돌 검증이 없어 L3 확인 전에는 켜지 않는다 | 본문 |
| 시뮬 칸 센서를 운영 판정에 쓸지 | 구현 없음 | — | — | — | — | — | 계약 본문(제안·미확정) |
| 새 outcome 값(`placement_unconfirmed`, `cancelled`) | 쓰지 않는다. #296 은 `dropped` + detail `placement_unconfirmed: …` 로 낸다 | — | — | — | — | — | 본문 |

### 11.5 이벤트 이름 (v2 뒤로 보류)

| 조항 | 상태 |
| --- | --- |
| `POUCH_LOST`, `BELT_AT_END_TIMEOUT` | 구현 없음. v1.1.0 `src/`·`sim/standalone/` 코드에 두 이름이 없다. 재범 결정 9/24 로 관측 이벤트만 두고 구현은 v2 뒤로 보류했다(계약 11.5). #252 의 소실은 로그 note(`pouch_lost`)뿐이다 |

### 11.6 병행 관측 토픽

타입 다섯 개는 #268 이 넣었다(추가만, wire 호환).

| 토픽 | 생산자 | 전달 | 소비자 | 켜는 인자 | L1·L2 | L3 | 근거 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/pharmacy/belt/observation` (`BeltObservation`) | #276 stage | #279 adapter | #290 orchestrator | 스테이지 `--belt-observation` + launch `belt_observation:=true`(기본 false) | `test_pharmacy_belt_observation.py`, `test_isaac_adapter.py`·`test_isaac_json.py` | 생산·전달만 L3: 실습15 RC-3a(유휴, #240 5746434485)와 실습15b 회차 A(master02 `eba5351`, 스텁 팔·조제실만, 트립 중 전이 관측, #240 5746506532·5746557646). 소비자(`observation_guard`)는 미실행 | #279·#290 코드, #276 본문 |
| `/amr_1/gripper/state` (`GripperState`) | #278 stage | #286 adapter | #291 arm | 스테이지 `--gripper-command-seq`(`--ur5 --mode ros`) + launch `gripper_command_seq:=true`(기본 false) + 팔 `gripper_observation:=state`(기본 `bool`) | `test_pharmacy_gripper_seq.py`, `test_isaac_adapter.py`, `test_ur5_pick_gripper_state.py` | 미실행(#240 L3-3 계획. 실습15b 기록도 "3b 그리퍼 command_seq 미확인", #240 5746557646) | #286 코드, #278·#291 본문 |
| `/amr_1/gripper/command_seq` (`GripperCommand`) | #291 arm(기존 Bool 에도 같은 값) | #286 adapter | #278 stage | 위와 같음 | 위와 같음 | 미실행 | #286 코드, #278·#291 본문 |
| `/amr_1/arm/clear_of_belt` (`ArmClearance`) | #282 arm. 판정 로직 #266, 통로 상자 순수 함수 #281(sim) | — (ROS 직접) | #290 orchestrator | 팔 `arm_clearance_enabled`(기본 false) + 기하 파라미터(기본값 없음) | `test_arm_clearance_node.py`·`test_arm_clearance_state.py`·`test_belt_lane_clearance.py`·`test_clearance.py` | 미실행 | #290 코드, 나머지 본문 |
| `/amr_1/base/docked` (`DockingState`) | #300 fleet. 판정은 `docking_state.judge` | — | 없음 | fleet `publish_docking_state`(기본 false) | `test_docking_state.py` | 미실행 | 코드(import), 나머지 본문 |

- `DockingState`: `amcl_max_age_s` 기본값이 0(미정)이라 `publish_docking_state` 를 켜도 L3 에서 값을 정하기 전에는 늘 UNKNOWN 이다(#300 본문). fleet L2 시험은 `test_fleet_nav2_l2.py` 다.
  - **odom 모드에서는 쓰지 않는다(재범 결정 9/24, #576 G6 ③).** 병원 회차는 AMCL 없이 odom 으로 돈다(`publish_docking_state` 끔). AMCL 로 바꿀 때 `amcl_max_age_s` 와 이 토픽을 다시 정한다. 기본값 0 은 그대로 두고 채우지 않는다.
  - v1.1.0 대조: `publish_docking_state` 기본 false, `amcl_max_age_s` 기본 0.0 그대로다(`fleet_node.py`). 병원 기동은 `localization:=odom` 이다(`tools/demo_v2.sh`).

### 11.7 모드별 증거와 시험 벡터

| 항목 | PR | 위치 | 근거 |
| --- | --- | --- | --- |
| 배출 벡터 + 기준 판정기 | #253 | `src/rokey_p3_interfaces/contract_vectors/conveyor_arm/v1/dispense.json`, 판정기는 bringup `conveyor_contract.py` `BeltReference` | 코드 |
| 피킹·다음 배출 벡터 + 트립 FSM 러너 | #261 | `pick.json`, `next_dispense.json`, `src/rokey_p3_orchestrator/test/test_contract_vectors_trip_fsm.py` | 코드 |
| 시뮬 벨트 러너 | #262 | `sim/tests/test_pharmacy_contract_vectors.py`. v1.1.0 에서도 xfail 없음(`EXPECTED_FAILURES = {}`. 재전송 D03 은 #264 가 풀었다, 11.2) | 본문, xfail 목록은 코드 |

- 러너의 규칙: 러너에 없는 opt-in 을 요구하는 사례는 skip 한다(이유에 opt-in 이름). 지원하는 사례 중 지금 못 맞추는 것은 xfail(strict)이다. 고치는 PR 에서 뺀다.
- 벡터는 물리(정지 거리·흡착)를 대신하지 않는다. 그래서 L3 칸이 없다.

## 3절 프레임과 경로

### 놓는 곳 프레임의 기준점(결정 23, #284)

| 프레임 | 작성자 | 구현 | 값 | 소비자 | 근거 |
| --- | --- | --- | --- | --- | --- |
| `deck_slot_N` | isaac TF 발행기 | #287: `--ur5` 스테이지의 TF 원점을 칸 바닥 윗면 중심으로 0.004 m 올렸다. `--ur5` 없는 실행은 그대로. 합본 AMR(병원·빈월드)은 `amr_base.build_tray_on_base` 가 `layout.TRAY["slots"]` 세 자리로 `amr_1/deck_slot_1..3` 을 낸다(계약 3절 번호 표) | 스테이지 기하에서 나온다 | #296 칸 안착 확인(놓는 곳 프레임의 칸 상자) | 본문, 코드(합본) |
| `pharmacy/belt_end` | `zones_tf` | 기준점 정의만 있다 | `zones.yaml` 은 **미측정**(0 은 빈 자리). 병원 두 파일은 잰 값이다: `zones.hospital.yaml` A1 끝 롤러 윗면, `zones.hospital-receiver.yaml` A1 모듈 탁자 정착점(#796) | 카메라 집기의 벨트 관측 자세(launch `belt_view_frame` 기본 `pharmacy/belt_end`) | 계약 본문, 코드(zones 파일) |
| `<zone>/cabinet` | `zones_tf` | 기준점 정의만 있다 | `zones.yaml` 은 **미측정**. 병원 파일은 앵커 JSON 의 협탁·테이블 윗면에서 만든 값이다(`sim/standalone/p3sim/hospital_nav.py`) | 팔의 보관함 놓기(`{zone_id}/cabinet`, 계약 10.1), #296(보관함 칸 상자 파라미터) | 계약 본문, #296 본문, 코드(zones 파일) |

- 지지 평면 투영(#271 perception `plane_projection.py`)은 새 파일이고 노드에 연결되지 않았다.
- 놓기 목표(칸 바깥 상자의 중심)는 아직 TF 원점과 약 2 cm 어긋난다(계약 3절, 시뮬 정적 확인).

### 경유 zone 과 경로 토폴로지(F3, 제안)

| 조항 | 구현 PR | 노드에 연결됐나 | L1·L2 | L3 | 근거 |
| --- | --- | --- | --- | --- | --- |
| 새 zone id `door_xN`·`cp_x` | `zones.py` 정규식(#273) | 예(zones 로드) | `test_topology.py`(정규식 사례는 여기 있다. `test_zones.py` 에는 없다) | 미실행 | 코드(정규식) |
| 경유 전용 zone 은 `GoToZone` 목적지가 아니다 | #285 fleet 이 `topology.is_terminal` 로 거부 | 예(실물 fleet). 스텁 fleet 은 구역 ID 모양만 본다 | `test_fleet_nav2_l2.py`, `test_topology.py` | 미실행 | 코드(fleet_node) |
| 토폴로지 로드 검증과 두 정거장 사이 경로 | #273 `topology.py` | **아니오.** fleet 은 `is_terminal` 만 쓴다 | `test_topology.py` | 미실행 | 코드 |
| `hospital_topology.yaml` | 없음 | — | — | — | 코드(v1.1.0 `rokey_p3_description/config/` 에는 `zones.*.yaml`·`routes.*.yaml` 만 있다) |
| 문·통로 통과 판정 | #263 `passage.py` | 아니오(새 파일만) | `test_passage.py` | 미실행 | 코드 |
| zones readiness(공차·유한값·필수 zone) | #242 `readiness.py` | `publish_docking_state` 를 켤 때만 #300 이 `zone_reasons` 를 쓴다. 끄면 쓰지 않는다 | `test_readiness.py` | 미실행 | 코드 |
| 하위 goal token·epoch·종결 판정 | #250 `goal_guard.py`, #258 이 fleet 에 연결 | 예(실물 fleet) | `test_goal_guard.py` | 미실행 | 코드(fleet_node import) |
| 병동 주행 계층 경로 연결 | RFC 0001(#304, proposed) | — | — | — | 본문 |

- 웹 백엔드의 구역 ID 정규식(`web/backend/app/zones.py`)에는 `door_xN`·`cp_x` 가 없다. 주행 쪽 정규식과 다르다(v1.1.0 코드 읽기).

### 병원 zones·도크 = 적재 (3절, v1.1.0)

| 조항 | 구현 PR | 기본인가 | L1·L2 | L3 | 근거 |
| --- | --- | --- | --- | --- | --- |
| 병원 zones·routes 는 생성물(`hospital_nav_files.py`) | 9/24 확정값(계약 3절 표, 접근점 재선정 #639) | 예 | `sim/tests/test_hospital_nav.py`(저장본 = 생성기) | aca8840 · #240 5801268218·5801363458(계약 3절) | 코드 |
| A1 도크 = 적재 자리(`dock_1` = `load`) | #790 | 예. 두 벌(`zones.hospital.yaml`·`zones.hospital-receiver.yaml`) 모두 | `test_hospital_nav.py`(`test_the_a1_dock_is_the_load_pose_and_leaves_room_to_turn`) | 미실행(#772 5891599172) | 코드 |
| 도크 = 적재면 `GoToZone(load)` 생략 | #790 orchestrator `load_is_dock` | 예. zones 파일에서 두 자세가 같으면 켜진다 | `test_trip_fsm.py` | 미실행 | 코드 |
| dock_2–4 도 모듈 왼쪽 | #795 | 예 | `test_hospital_nav.py`(`test_docks_stand_left_of_their_module_like_the_a1_dock`) | 미실행(#772 5891599172) | 코드, PR 제목 |
| 탁자 정착 벌(receiver): 적재 자리·`belt_end` 를 9/29 실측값으로 | #796(생성기 `--receiver`), 기본 전환 #797 | 병원 카메라 기본(`P3_CAMERA_POUCHES=1`)일 때 `tools/demo_v2.sh` 가 고른다 | `test_hospital_nav.py`(receiver 두 시험) | 원 회차 05b8e28 bed_a1 1건([실습 45](../practice/simworld/practice-45.md)). 그 회차는 도크 = 적재가 아니었다. 통합본은 미실행 | 코드 |
| 적재 이동 중 첫 조제(`dispense_while_dispatching`) | #796 | 노드 기본 false. 병원 카메라 기본은 true. 도크 = 적재면 쓰이지 않는다 | `test_trip_fsm.py`, `tests/test_demo_v2.py` | 원 회차에서 켜졌다(실습 45). 통합본은 미실행 | 코드 |

## 이 표를 고칠 때

- 조항을 구현하거나 L3 에서 켠 PR 이 이 표의 칸도 고친다.
- L3 칸에는 #240 의 관측 댓글 링크를 적는다. 관측이 없으면 "미실행"으로 둔다.
- 계약 본문(`delivery-contract-v1.md`)의 상태 표시(**제안·미확정** 등)는 이 표가 아니라 계약 PR 에서 바꾼다.
