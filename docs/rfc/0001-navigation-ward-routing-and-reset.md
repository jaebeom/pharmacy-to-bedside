# RFC 0001 — 병동 주행(F3): 계층 경로 연결과 리셋 뒤 costmap 초기화

| 항목 | 내용 |
| --- | --- |
| 상태 | **proposed** — 승인 문서가 아니다 |
| 기준 | `main` @ `e271081`, 계약 v1 3절·6절·7절·11.6 |
| 관련 | 작업표 #239. 코드 #242 #250 #258 #263 #273 #285 #293 #295, #300(대기) |
| 담당·기한 | navigation. 기한 없음 — 이동 베이스 담당 결정(아래 차단) 뒤 |

이 문서는 저장소 밖 작업 메모(`_ops` 26·27번)에 있던 F3 설계를 옮긴 것이다. **결정된 것**과 **제안**을 나눠 적는다. 값은 하나도 채우지 않았다.

- 계층 경로는 병동에서 병실 문을 지나 침상으로, 경유 zone 을 차례로 가는 것이다.
- costmap 은 Nav2 가 장애물을 그리는 지도다. 리셋 뒤 이것을 비우는 것이 계약 6절 4단계다.

## 1. 질문

병동 구간(최종 시연 9/29)에서 fleet 이 다음 세 가지를 어떻게 하는가.

1. 목적지(침상·스테이션)까지 병동 → 병실 → 침상의 경유 zone 을 거쳐 간다.
2. 리셋 뒤 Nav2 costmap 을 비운다(계약 6절 4단계).
3. 좁은 문을 형상으로 판정한다.

## 2. 이미 결정된 것 (계약·머지된 코드)

| 내용 | 출처 |
| --- | --- |
| 경유 id 는 `door_xN`(병실 문 접근점)·`cp_x`(병동 checkpoint)다. 종단은 `load`·`dock_N`·`bed_xN`·`station_x` 다 | 계약 3절(#270) |
| `door_*`·`cp_*`·`room_*` 은 목적지가 되지 않는다 | #273·#285 |
| 토폴로지 파일은 `hospital_topology.yaml` 하나다. 좌표 없이 zone id 만 참조하고, 판본은 manifest 해시로 본다 | 계약 3절 |
| 미측정 값은 `null`(0 으로 채우지 않음)이고 그 경로는 `ready=false` 다. 좌표 0 은 유효하다 | 계약 3절 |
| 경로 계산은 차단 edge 집합(기본 빈 집합)을 인자로 받는다. 방문 순서는 트립 FSM 의 정거장 순서이고, 연속한 두 정거장 사이만 계산한다 | 계약 3절, `topology.plan`(#273) |
| 로드 거부 7항(없는 참조·중복, 역참조 불일치, 다른 병실 침상, 종단 경유, 음수·NaN·Inf, 도달 불가, manifest 해시 불일치) | 계약 3절, `topology.parse_topology`(#273) |
| 문 통과 판정: `W·abs(cos yaw) + L·abs(sin yaw) + 2×margin + 오차 예산 < 문 폭`. 경계값은 막고, inflation 은 입력으로 받지 않는다 | `passage.check_passage`(#263) |
| fleet 은 경유 전용 zone 을 GoToZone 목적지로 받지 않는다 | #285 |
| 프레임 기준점(`pharmacy/belt_end`·`<zone>/cabinet`·`deck_slot_N`)은 "물체가 놓이는 윗면의 중심"이다 | 재범 결정 23(9/20), #287 |

"종단 zone 을 경유로 쓰는 edge" 는 `load`↔`dock_1` 같은 정상 edge 와 로드 시점에 구분되지 않는다. 그래서 `topology.plan` 은 이것을 **경로 중간에 종단을 두지 않는 규칙**으로 구현했다(#273). 계약 3절도 같은 뜻으로 고쳐졌다(#277): 경로 계산에서 종단은 시작·끝에만 오고, 종단끼리 잇는 edge 는 정상이며, 로드에서 거부하는 것은 "종단 zone 을 경유 정지점으로 지정한 파일"이다.

## 3. 제안 (결정 아님)

### 3.1 fleet 이 계층 경로를 쓰는 방법

- 외부 `GoToZone` 은 zone_id 하나 그대로다.
- fleet 안에서는 `topology.plan(현재 zone, 목적지)` 로 경유 목록을 얻어 차례로 간다. 첫 버전은 경유마다 `NavigateToPose` 다.
- `ComputePathThroughPoses → FollowPath`(#232 계획 6절)는 나중 후보다. Jazzy 설치본에서 필드를 확인한 뒤에 한다.
- `arrived=true` 는 종단에서만 낸다. 경유 zone 에서는 공차·정지 판정을 하지 않는다. `stops`(문 앞 정지) zone 에서만 멈춘다.
- 제한 시간은 GoToZone 하나에 하나(계약 7절)를 쓴다. 경유마다 초기화하지 않는다.
- 현재 zone 을 정하는 방법이 필요하다(마지막 도착 zone). 리셋 뒤에는 `dock_k` 다.
- 도달 가능성 검사는 지금 `load` 에서만 한다. 목적지 → `dock_*` 복귀 경로 검사를 더할지 정해야 한다.

### 3.2 리셋 뒤 costmap 초기화 (계약 6절 4단계, 현재 미구현)

- 순서: `RESET_DONE`(새 epoch) → 진행 중 goal 닫기(#258) → `initialpose` → global·local costmap clear 를 비동기로 1회씩.
- 서비스 이름·타입은 **미확인**이다. 후보는 `/<ns>/global_costmap/clear_entirely_global_costmap`, `/<ns>/local_costmap/clear_entirely_local_costmap`, `nav2_msgs/srv/ClearEntireCostmap` 다. 마스터에서 `ros2 service list`·`ros2 interface show` 로 확인하기 전에는 코드에 넣지 않는다.
- 서비스 탐색은 계약 7절대로 10 s(wall)까지 한다. 없거나 응답이 없으면 WARN 만 남긴다(fleet 은 barrier 에 결과를 돌려줄 통로가 없다).
- L2 설계(fake 서비스): ① 한 번씩 호출되고 `initialpose` 뒤에 온다 ② 같은·이전 epoch 는 호출하지 않는다 ③ 서비스가 없어도 `base/stopped` 5 Hz 가 끊기지 않는다 ④ 응답 지연 중에도 tick 이 막히지 않는다 ⑤ 주행 중 리셋이면 goal 은 `reset`, clear 는 1회다.

| # | 결정 요청 | 제안 | 결정권 |
| --- | --- | --- | --- |
| D-F3-1 | `initialpose` 뒤 clear 전에 AMCL 수렴을 기다리는가 | 첫 버전은 기다리지 않는다. 수렴 기준이 계약에 없다 | 재범·navigation |
| D-F3-2 | clear 실패 뒤 다음 GoToZone 을 거부하는가 | 거부하지 않고 WARN. 서비스 이름 확인·L3 영향 확인 뒤 다시 본다 | 재범(계약 6절) |
| D-F3-3 | 서비스 이름을 파라미터로 받는가 | 파라미터로 받고, 확인한 이름을 기본값으로 둔다 | navigation |

### 3.3 복구 동작

Nav2 기본 BT 에는 spin·backup 이 있다(`nav2_params.yaml`). 계약 7절은 "Nav2 recovery 에 맡긴다"고 했고, 작업 지시는 "주변 공간·이동 허가를 확인하지 않은 회전·후퇴는 금지"라고 했다. 둘이 충돌하므로 F3 에서 navigation 담당과 정한다. 지금은 아무것도 바꾸지 않았고, 새 복구 동작도 더하지 않았다.

## 4. 값 — 전부 마스터 실측 전, 미정

| 값 | 무엇 | 누가 / 어디서 | 지금 |
| --- | --- | --- | --- |
| occupancy map | `hospital.yaml`·`.pgm`, origin = Isaac world | simulation 추출 / navigation | 없음 |
| zone 좌표·공차 | `zones.yaml` x·y·yaw, `tol_xy`·`tol_yaw` | simulation(좌표), manipulation+navigation(공차) | 전부 0 |
| 문·통로 유효 폭 | edge 마다 `clear_width_m` | simulation(합성 stage) | 없음 |
| 로봇 footprint | 베이스 + 수납 팔 + 상판 + 적재물, 빈·적재 두 벌 | simulation + manipulation | 없음. `robot_radius` 0.6 m 는 잠정 |
| 통과 여유 | margin, 오차 예산 | navigation L3 | 없음 |
| AMCL 신선도 문턱 | `amcl_max_age_s`(#300) | navigation L3 | 0 = 미정 → DockingState 는 늘 UNKNOWN |
| edge 비용 | 거리 또는 실측 주행 시간 | navigation | 없음 |
| Nav2 서비스·플러그인 표기 | clear costmap 서비스, Jazzy 플러그인 이름 | master observer | 미확인 |

## 5. 관측된 사실

- `rokey_p3_description/config/zones.yaml` 의 병동 쪽 zone 은 `bed_a1`·`station_a` 둘뿐이다(`load`·`dock_1` 과 함께 네 개).
- `rokey_p3_orchestrator/config/order_pool.yaml` 은 `bed_a1`·`bed_a2`·`bed_b1`·`bed_b2` 를 쓴다(13–16줄). `bed_a2`·`bed_b1`·`bed_b2` 는 `zones.yaml` 에 없다. `sim/` 쪽 제보를 받아 두 파일을 main 에서 직접 확인했다.
  - 이 주문으로 병동 구간을 돌리면 fleet 은 GoToZone 을 "모르는 구역"으로 거부한다.
  - **pharmacy_only 시연(9/21)에는 영향이 없다.** `pharmacy_only` 트립은 출발 뒤 바로 복귀하고 침상 zone 으로 가지 않는다(`trip_fsm.py` 727·872줄).
- `hospital_topology.yaml` 실제 파일은 아직 없다. 값이 없어서 만들지 않았다.

## 6. 차단

- **주행 L3 의 대상이 없다.** main 의 Isaac 합성 stage 에는 이동 베이스(dummy x/y/yaw 구동, 라이다, joint_states)가 없다. UR5 는 고정 받침 위의 대역이다.
  - "합성 stage 의 이동 베이스 담당"은 재범의 열린 결정이다(#239).
  - 장면의 `ridgeback_ur5` articulation 은 끄지 않고 WARN 으로 둔다. 끌지 말지는 이동 베이스 담당이 정해지면 다시 정한다(재범 결정 22, #239 기록).
- 그래서 경로·도킹·문 통과·costmap 초기화는 **전부 L3 미실행**이다. 지금까지의 검증은 L1(순수 로직)과 L2(fake Nav2)뿐이다.

## 7. 검증 계획

| 층 | 무엇 |
| --- | --- |
| L1 | topology 로드 거부·경로(#273), 문 통과(#263), DockingState 판정(#300) — 머지됨·대기 |
| L2 | fake Nav2 로 경유 zone 을 차례로 가는 GoToZone, 리셋·취소가 경유 중에도 10 s 안에 끝남, costmap clear 호출(3.2) |
| L3 | 적재 footprint 로 문 통과, 종단 공차·정지, 경로 차단, 리셋 뒤 유령 장애물 없음 — 이동 베이스 뒤 |

## 8. 대안

- 경유 zone 을 orchestrator 가 GoToZone 여러 번으로 보낸다: 트립 FSM 과 계약 2.2절(GoToZone 은 종단)을 바꿔야 해서 택하지 않는다.
- inflation 을 줄여 좁은 문을 통과시킨다: 형상이 아니라 비용 조정이라 금지한다(#232 계획, 작업 지시).
