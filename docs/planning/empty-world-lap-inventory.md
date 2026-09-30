# 빈월드 전 구간 한 바퀴 — 단계별로 지금 가진 것

2026-09-21. 기준 `914d23d`.
카드 K0-b. **계획 문서다.** 여기 적힌 것은 결정이 아니라 지금 저장소에 있는 것의 목록이다.

두 가지를 섞지 않는다.

- **코드에서 확인**: 파일·줄을 달았다. 그 줄을 열면 같은 말이 있다.
- **문서 인용**: 런북·이슈 댓글에서 옮긴 것이다. 내가 다시 돌려 본 것이 아니다.

형식은 [계약 v1 구현 현황](../architecture/delivery-contract-v1-status.md)과 같다.

---

## 1. 단계별 목록

단계 이름은 계약 2.6절의 이벤트 순서를 그대로 쓴다. 그 순서는
`src/rokey_p3_bringup/test/test_stub_loop.py:29-35` 의 `CONTRACT_ORDER` 가 시험으로 고정하고 있다.
**이벤트를 내는 것은 전부 orchestrator 의 `trip_fsm` 하나다.** 아래 "누가 한다" 는 그 단계의 일을
실제로 하는 액션 서버·노드를 말한다.

| # | 단계(이벤트) | 누가 한다 | 스텁 | 실물 | 켜는 인자 | 시험 |
| --- | --- | --- | --- | --- | --- | --- |
| ① | 주문 접수 `REQUEST_ACCEPTED` | `order_generator` 또는 웹 백엔드 → `orchestrator` | 주문 풀 파일 | 웹 주문 | `max_requests`, `order_pool_file` | `test_lap_order.py`, 웹 `tests/` |
| ② | 적재 위치 도킹 `AMR_DOCKED_LOAD` | `GoToZone load` | `stub_fleet` | `fleet_node`(Nav2) | `use_stub_fleet` | `test_fleet_nav2_l2.py`(F1·F2) |
| ③ | 조제 `DISPENSED` | `Dispense` 액션 | `stub_sim`(`serve_dispense`) | Isaac 디스펜서 ← `isaac_adapter` | `use_isaac_adapter` | `test_isaac_adapter_loop.py` |
| ④ | 벨트 끝 `POUCH_AT_END` | `/pharmacy/belt` | `stub_sim`(`publish_belt`) | Isaac 벨트 ← 어댑터 | `use_isaac_adapter` | `test_isaac_json.py` |
| ⑤ | 적재 픽 `PICK_ATTEMPT`→`LOAD_DONE`→`ARM_HOME` | `PickPouch` 액션 | `stub_arm` | **UR5 `arm` 노드** | `use_stub_arm`, **`use_ur5_arm`(PR #403)** | `test_ur5_pick_*.py`(L1) |
| ⑥ | 출발·병동 도착 `DEPARTED`→`ARRIVED` | `GoToZone bed_*` | `stub_fleet`(1 s 고정) | `fleet_node`(Nav2) | `use_stub_fleet` | `test_zones.py`, `test_passage.py` |
| ⑦ | 환자 인증 `AUTH_OK` | `ScanTag` 액션 + 인식표 | `stub_arm`+`stub_detector` | `arm` 노드 + `perception` | `use_stub_arm`, `use_stub_detector` | `test_tag_*`(perception) |
| ⑧ | 수령·안착 `POUCH_DETECTED`→`CABINET_LOCKED`→`ORDER_DONE` | 검출 + `PickPouch` + 보관함 관측 | `stub_detector`·`stub_arm`·`stub_sim` | `pouch_detector_node` + `arm` 노드 | `use_stub_detector`, `use_stub_arm` | `test_stub_loop.py`(L2) |
| ⑨ | 복귀 `ARM_HOME`→`RETURNED` | `GoToZone dock_*` | `stub_fleet` | `fleet_node` | `use_stub_fleet` | `test_trip_fsm.py` |
| ⑩ | 도킹·리셋 `DOCKED` / `RESET_DONE` | 도킹 판정 + `/sim/reset` | `stub_sim`(`serve_reset`) | `docking_state.py` + Isaac 리셋 | `use_isaac_adapter`, `publish_docking_state` | `test_docking_state.py`, `test_reset_barrier_loop.py` |
| 곁 | 보충 `/m0609/refill` | M0609 레일 팔 | `stub_arm`(`serve_refill`) | `m0609_arm` + Isaac 레일 | `use_stub_m0609`, `emulate_m0609` | `test_stub_arm_m0609.py`, `test_m0609_loop.py` |

**지금 시연 경로에서 실물인 것은 ③·④·⑩(Isaac 조제실)과 보충뿐이다.** ⑤ 적재 픽은 스텁이고,
⑥⑦⑧ 은 전부 스텁이며 병동은 화면에 없다(`docs/runbooks/demo-0921-v2.md` 3.5절, 문서 인용).

### 빈 칸 (여기서 멈춘 것)

- **⑤ UR5 팔 노드는 한 번도 시연 스택에서 돈 적이 없다.** `arm` 진입점(`setup.py:25`)을 띄우는
  launch 가 없었다. PR #403 이 `use_ur5_arm` 을 더했지만 **L3 미실행**이고, `--mode ros` 로 UR5 가
  돈 회차도 아직 없다(비전 보고, 문서 인용 — 실습12 성공은 전부 `--mode selfdemo`).
- **⑥ 스텁 주행은 구역 파일을 보지 않는다.** 거리와 상관없이 1 s 에 도착을 내고, 구역 파일에 없는
  침상에도 도착을 낸다(`docs/runbooks/demo-0921-v2.md`, 문서 인용). 실물 `fleet_node` 는 구역 파일에
  없는 목적지를 거부한다.
- **⑦ 인증은 실물로 돌아간 적이 없다.** `tag_standoff_m` 기본값이 0 이고, 0 이면 `ScanTag` 를 시도하지
  않고 `UNREADABLE` 로 닫는다(`arm_node.py:171` 주석).
- L3 기록은 조제실 구간(실습13·14)과 스텁 전 구간 1회(실습18, `45d7fe3`)뿐이다. 문서 인용이다.

---

## 2. "한 스테이지에 전 구역" 을 막는 것

조사한 것: `sim/standalone/pharmacy_stage.py`, `p3sim/layout_v2.py`, `base_scene.py`, `ur5_cell.py`,
`aisle.py`, `hospital_assets.py`, `hospital_main.py`.

먼저 **되는 것**부터: 병원 씬 배경 위에 조제실을 올리는 길은 이미 있다. `--preset hospital-v2`
(`pharmacy_stage.py:88-92`)가 원점 A·비활성 50개·강체 off 22개를 묶어 놓았고, `--base-usd` 로 병원
USD 를 `/World/P3Base/Scene` 에 레퍼런스한다(`base_scene.py:187-189`). 그 씬에는 병상 8개와
`ridgeback_ur5` 가 들어 있다(`sim/scenes/hospital_layout.usda:69`).

막는 것은 **두 구역을 각자 원점에 짓는 것**이다.

| 막는 것 | 어디 | 무슨 뜻 |
| --- | --- | --- |
| 조제실 원점 = 월드 원점 고정 | `base_scene.py:1-10`, `:109-113`, `:182-186` | `--pharmacy-origin` 은 조제실을 옮기지 않는다. 래퍼 변환의 **역**을 병원 쪽에 걸어 병원을 움직인다. 한 프로세스에 조제실 좌표계는 하나뿐이다 |
| 방 치수가 모듈 전역 상수 | `pharmacy_stage.py:52`, `:60`, `:367-409`, `:614-621` | `room(args)` 가 방 하나만 만들고 `build_room` 도 한 번만 불린다. 둘째 구역을 만들 루프도 접두사 인자도 없다 |
| `--scene` 은 v1\|v2 택일 | `pharmacy_stage.py:106` | 한 프로세스에 두 레이아웃을 같이 못 올린다 |
| 병원 진입점이 스테이지를 통째로 교체 | `hospital_scene.py:12-16`(`open_stage`) | `hospital_main.py` 는 `pharmacy_stage` 가 쌓은 프림과 공존하지 못한다. 구조적으로 별개 프로세스다 |
| `/clock` 작성자는 하나 | `pharmacy_stage.py:539`, 계약 4절 | 조제실 프로세스와 병동 프로세스를 같이 띄우면 `/clock` 을 둘이 낸다. 코드가 막지는 않는다(**추정**) |
| AMR 을 구동하는 코드가 없다 | `sim/` 전체 | 병원 씬의 `ridgeback_ur5` 는 **보이기만 하고 스테이지가 구동하지 않는다**. 발견하면 경고만 남긴다(`pharmacy_stage.py:600-601`) |
| 병동을 짓는 코드가 없다 | — | 병동은 남의 USD 에 딸려 오는 배경이다. 우리가 만드는 구역이 아니다 |

**그래서 빈월드 한 바퀴의 실제 선택지는 둘이다**(제안이지 결정이 아니다).

1. 병원 씬 위에 조제실을 올리고(`hospital-v2`) 주행은 그 바닥 위에서 한다. 병동 가구는 배경으로 보인다.
   `hospital-v2` 는 **아직 한 번도 안 돌았다**(`docs/runbooks/l3-sim-conveyor.md:14` "RC-4 … 미실행", 문서 인용).
2. 조제실 스테이지만 띄우고 병동 구역은 구역 파일의 좌표로만 둔다. 화면에는 없고 주행은 빈 바닥을 간다.

---

## 3. 배타 인자 — 한 묶음으로 줘야 하는 것

| 묶음 | 어긋나면 | 어디서 막는가 |
| --- | --- | --- |
| 스테이지 `--ur5` + `--ros-pick-stand-in-s 0` | `ros_pick_stand_in_s > 0` 이면 기동 거부 | `pharmacy_stage.py:444-447`(#244). `demo-ros*`·`hospital-v2` preset 은 전부 기본 `5.0` 이라 `--ur5` 만 붙이면 안 뜬다 |
| launch `use_ur5_arm:=true` + `use_stub_arm:=false` + `pick_notice:=false` + `ur5_arm_params_file` | 노드를 하나도 띄우지 않고 멈춘다 | `stub_loop.launch.py` 의 `ur5_arm_problem`(PR #403) |
| `--gripper-command-seq` 는 `--ur5` + `--mode ros` 에서만 | 기동 거부 | `pharmacy_stage.py:448-449` |
| `use_isaac_adapter:=true` + `publish_clock:=false` + `emulate_m0609:=false` | **경고만** 한다. 자동으로 끄지 않는다 | `stub_loop.launch.py` 의 `LogInfo` |
| `--preset hospital-v2` 는 `--base-usd` 필수 | 기동 거부 | `pharmacy_stage.py:422-423` |

### 구역 파일 — 누가 받고 누가 안 받나

세계를 바꾸려면 구역 파일을 바꿔 끼워야 한다. 지금 그 파일을 **읽는 곳은 셋뿐**이고,
셋을 한 번에 가리키는 인자는 없다. 대신 **절대 경로를 두 군데에 같은 값으로 주면 된다.**

| 누가 | 어떻게 받나 | 어디 |
| --- | --- | --- |
| `fleet` · `zones_tf` | launch 인자 **`zones_file`** 하나가 `RewrittenYaml` 로 둘을 같이 덮어쓴다 | `navigation.launch.py:32-34`, `:46-50` |
| 웹 백엔드 | launch 가 아니라 프로세스 CLI **`--zones-file`** | `web/backend/app/main.py:596-597`, `:411-417` |
| `orchestrator` | **안 읽는다.** 구역 ID 형식만 본다(`is_zone_id`) | `orchestrator_node.py:42`, `:374-375` |
| `sim/` 스테이지 | **안 읽는다** | — |

- 환경변수는 없다. `P3_ZONES` 같은 이름은 저장소 어디에도 없다.
- 웹은 `--zones-file` 이 없으면 저장소 원문을 찾아 쓰고, 그것도 없으면 상수 두 개로 떨어진다
  (`zones.py:37`). 응답의 `source` 칸이 `file`·`repo_default`·`mock` 중 무엇인지 알려 준다.
- **그래서 세계마다 할 일은 "같은 절대 경로를 `navigation.launch.py` 의 `zones_file` 과 웹의
  `--zones-file` 에 준다" 하나다.** 새 인자를 만들 필요는 없다(제안).

### 여기가 진짜 빈 칸이다

- **구역 정의 파일은 저장소에 하나뿐이고 좌표가 전부 0 이다.** `src/rokey_p3_description/config/zones.yaml`
  에 `load`·`dock_1`·`bed_a1`·`station_a` 네 구역과 조제실 고정 프레임 넷이 있는데
  `x`·`y`·`yaw`·`tol` 이 모두 0 이다(파일 주석 6-10줄, 미측정).
- **주문 풀의 침상 넷 중 셋이 구역 파일에 없다.** 풀에는 `bed_a1`·`bed_a2`·`bed_b1`·`bed_b2` 가 있고
  (`order_pool.yaml:13-16`) 구역 파일에는 `bed_a1` 뿐이다. 웹도 orchestrator 도 형식만 보므로 통과하고,
  **실물 `fleet` 에서만 거부된다**(`fleet_node.py:147`). 스텁 주행은 그대로 도착을 낸다.
- **지도도 위상 파일도 없다.** `config/maps/` 에는 README 뿐이고 `hospital_topology.yaml` 은 존재하지
  않는다. `topology.py:222` 는 읽을 준비만 돼 있고 부르는 노드가 없다.
- 계약 문서는 `/deliver` 수락 조건을 "`destination_id` 가 `zones.yaml` 에 있음" 으로 적는데
  (`docs/architecture/delivery-contract-v1.md:332`) 코드는 형식 검사뿐이다. 문서와 코드가 갈린다.

---

## 4. 다음에 채울 것

- **구역 좌표를 잰다.** 빈월드 한 바퀴의 첫 관문이다. 파일 하나에 값이 없으면 실물 주행은 시작할 수 없다.
  침상 셋을 구역 파일에 넣을지, 주문 풀을 `bed_a1` 만 쓰도록 줄일지도 같이 정해야 한다.
- `hospital-v2` 1회 기동(smoke). 지금은 코드 경로만 있고 회차가 없다.
- `use_ur5_arm` L3 1회. 그 전에는 ⑤ 를 "실물" 칸에 넣어 말하지 않는다.
- 이 표의 "시험" 칸 중 L2 인 것과 L1 인 것을 나눠 적기.
